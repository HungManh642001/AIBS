"""Agentic Workflow (LlamaIndex) phân rã 1 nhóm — 4 bước, mỗi bước MỘT việc:

  1. list    : liệt kê tiêu chí {nhom, ten, yeu_cau_goc, hsdt_can_kiem_tra};
               critique (chống sót) CHỈ cho nhóm nhiều bảng (vd năng lực) — free-text thì bỏ.
  2. analyze : mỗi tiêu chí -> noi_dung_can_kiem_tra; mục nguon=hsmt trống gia_tri = "chưa đủ".
  3. search  : với mục chưa đủ -> sinh query -> retrieve -> điền gia_tri (no-fab -> can_review).
  4. collect : gom.

Nội dung nguon=hsdt = dữ liệu nhà thầu -> đánh giá ở bước sau, không tra.
"""
from __future__ import annotations

import logging
from typing import Any

from llama_index.core.workflow import Context, Event, StartEvent, StopEvent, Workflow, step

from experiment.decompose.llm import LlmFn
from experiment.decompose.prompts import (
    SYS_CRITIQUE,
    SYS_LIST,
    SYS_QUERY,
    SYS_RESOLVE,
    SYS_STRUCT,
    critique_prompt,
    list_prompt,
    query_prompt,
    resolve_prompt,
    struct_prompt,
)
from experiment.decompose.retrieval import RetrieveFn
from experiment.decompose.schema import (
    Coverage,
    GroupDecomposition,
    norm_ten,
    validate_criteria_list,
    validate_criterion,
)

log = logging.getLogger("experiment.decompose")

# Step structure/resolve sinh JSON dài + Qwen3 có khối <think> -> cần budget rộng (mặc định chỉ 4096).
_STRUCT_MAX_TOKENS = 8192


def _validate_queries(d: Any) -> dict[str, Any]:
    """Chuẩn hoá output sinh sub-query: {queries:[{ten,query}]}."""
    qs = d.get("queries", []) if isinstance(d, dict) else []
    return {
        "queries": [
            {"ten": str(q.get("ten", "")), "query": str(q.get("query", ""))}
            for q in qs
            if isinstance(q, dict)
        ]
    }


class _Listed(Event):
    crits: list
    added: list
    listed_n: int


class _AnalyzeReq(Event):
    crit: dict


class _SearchReq(Event):
    crit: dict
    item: dict


class _Done(Event):
    detail: dict
    needs_review: dict | None


def _render_rows(rows: list[list[Any]]) -> str:
    return "\n".join(" | ".join(str(c) for c in (r or [])) for r in (rows or []))


class DecomposeWorkflow(Workflow):
    """Chạy 1 lần/nhóm. wf.run(group=<dict trong chuong3_groups.json>) -> GroupDecomposition."""

    def __init__(self, llm_fn: LlmFn, retrieve_fn: RetrieveFn | None = None, **kw: Any):
        super().__init__(**kw)
        self._llm = llm_fn
        self._retrieve = retrieve_fn

    # ---- nguồn nội dung nhóm (kèm lần tham chiếu Mục 3 -> Phần 4) ----
    def _build_source(self, group: dict[str, Any]) -> str:
        parts: list[str] = []
        for b in group.get("blocks", []):
            if b.get("type") == "table":
                parts.append(_render_rows(b.get("rows", [])))
            else:
                parts.append(b.get("text", "") or "")
        src = "\n".join(p for p in parts if p)
        if group.get("is_reference") and self._retrieve:
            tgt = group.get("ref_target") or {}
            q = f"{tgt.get('kind', '')} {tgt.get('number', '')} yêu cầu kỹ thuật thông số hàng hóa"
            hits = self._retrieve(q, k=5)
            if hits:
                body = "\n".join(h["text"][:500] for h in hits)
                src += f"\n\n[NỘI DUNG THAM CHIẾU PHẦN {tgt.get('number', '')}]\n{body}"
        return src

    def _assemble(
        self, group: dict, criteria: list, added: list, listed_n: int, needs: list | None = None
    ) -> GroupDecomposition:
        needs = needs or []
        return GroupDecomposition(
            group=group.get("group", ""),
            muc=group.get("muc", ""),
            is_reference=bool(group.get("is_reference")),
            ref_target=group.get("ref_target"),
            criteria=criteria,
            coverage=Coverage(
                listed_n=listed_n,
                final_n=len(criteria),
                added_by_critique=list(added),
                notes="",
            ),
            needs_review=needs,
        )

    @staticmethod
    def _has_tables(group: dict[str, Any]) -> bool:
        """Nhóm nặng bảng (vd năng lực) -> bật critique chống sót; free-text -> bỏ qua."""
        return any(b.get("type") == "table" for b in group.get("blocks", []))

    # ---- Step 1: liệt kê tiêu chí (+ critique CHỈ cho nhóm bảng lớn) ----
    @step
    async def list_criteria(self, ctx: Context, ev: StartEvent) -> _Listed | StopEvent:
        group = ev.group
        log.info("[nhóm %s] %s", group.get("group", ""), group.get("muc", ""))
        source = self._build_source(group)
        await ctx.store.set("group", group)
        await ctx.store.set("source", source)

        out = await self._llm(SYS_LIST, list_prompt(source), validate=validate_criteria_list,
                              max_tokens=_STRUCT_MAX_TOKENS)
        if out.status == "error":
            # Cả nhóm lỗi liệt kê -> không bịa, trả needs_review.
            gd = self._assemble(group, [], [], 0, [{"ten": "(toàn nhóm)", "ly_do": f"lỗi AI liệt kê: {out.error}"}])
            return StopEvent(result=gd)

        listed = list(out.data.get("criteria", []))
        listed_n = len(listed)
        added: list[str] = []

        # Critique (chống sót) chỉ cho nhóm nhiều bảng — nơi liệt kê 1 lượt dễ sót dòng.
        if self._has_tables(group):
            seen = {norm_ten(c.get("ten", "")) for c in listed}
            cout = await self._llm(SYS_CRITIQUE, critique_prompt(source, listed),
                                   validate=validate_criteria_list)
            if cout.status == "ok":
                for m in cout.data.get("criteria", []):
                    key = norm_ten(m.get("ten", ""))
                    if key and key not in seen:
                        seen.add(key)
                        listed.append(m)
                        added.append(m.get("ten", ""))
            log.info("  [list] %d tiêu chí; [critique] +%d sót", listed_n, len(added))
        else:
            log.info("  [list] %d tiêu chí (bỏ critique: nhóm free-text)", listed_n)
        return _Listed(crits=listed, added=added, listed_n=listed_n)

    # ---- fan-out: mỗi tiêu chí -> phân tích ----
    @step
    async def fan_out(self, ctx: Context, ev: _Listed) -> _AnalyzeReq | StopEvent:
        await ctx.store.set("added", ev.added)
        await ctx.store.set("listed_n", ev.listed_n)
        group = await ctx.store.get("group")
        if not ev.crits:
            return StopEvent(result=self._assemble(group, [], ev.added, ev.listed_n))
        log.info("  [fan-out] %d tiêu chí", len(ev.crits))
        await ctx.store.set("n", len(ev.crits))
        for c in ev.crits:
            ctx.send_event(_AnalyzeReq(crit=c))
        return None

    # ---- Step 2: phân tích 1 tiêu chí -> noi_dung_can_kiem_tra (mục hsmt trống = chưa đủ) ----
    @step
    async def analyze(self, ctx: Context, ev: _AnalyzeReq) -> _SearchReq | _Done:
        crit = ev.crit
        source = await ctx.store.get("source")
        ten = crit.get("ten", "")
        log.info("    [analyze] %s", ten)

        out = await self._llm(SYS_STRUCT, struct_prompt(crit, source),
                              validate=validate_criterion, max_tokens=_STRUCT_MAX_TOKENS)
        if out.status == "error":
            log.warning("    [analyze] %s -> lỗi: %s", ten, out.error)
            item = {
                "nhom": crit.get("nhom", "hop_le"),
                "ten": ten,
                "yeu_cau_goc": crit.get("yeu_cau_goc", ""),
                "hsdt_can_kiem_tra": crit.get("hsdt_can_kiem_tra", []),
                "tien_quyet": False,
                "noi_dung_can_kiem_tra": [],
                "loi_ai": out.error,
            }
            return _Done(detail=item, needs_review={"ten": ten, "ly_do": f"lỗi AI: {out.error}"})

        item = out.data
        # Bù field từ step 1 nếu structure bỏ trống (yeu_cau_goc/hsdt đã xác định ở list).
        if not item.get("yeu_cau_goc"):
            item["yeu_cau_goc"] = crit.get("yeu_cau_goc", "")
        if not item.get("hsdt_can_kiem_tra"):
            item["hsdt_can_kiem_tra"] = crit.get("hsdt_can_kiem_tra", [])
        return _SearchReq(crit=crit, item=item)

    # ---- Step 3: tìm kiếm giá trị cho nội dung chưa đủ (nguon=hsmt, gia_tri trống) ----
    @step
    async def search(self, ctx: Context, ev: _SearchReq) -> _Done:
        crit, item = ev.crit, ev.item
        ten = crit.get("ten", "")

        needs = [
            n for n in item.get("noi_dung_can_kiem_tra", [])
            if n.get("nguon", "hsmt") == "hsmt" and not (n.get("gia_tri") or "").strip()
        ]

        if needs and self._retrieve:
            log.info("    [search] %s -> %d nội dung cần tra giá trị", ten, len(needs))
            queries: dict[str, str] = {}
            qout = await self._llm(SYS_QUERY, query_prompt(crit, needs), validate=_validate_queries)
            if qout.status == "ok":
                for q in qout.data.get("queries", []):
                    queries[norm_ten(q.get("ten", ""))] = q.get("query", "")
            lines: list[str] = []
            for n in needs:
                q = queries.get(norm_ten(n.get("ten", ""))) or f"{ten} {n.get('ten', '')}"
                log.info("      [retrieve] %s", q)
                hits = self._retrieve(q, k=3)
                if hits:
                    body = "\n".join(h["text"][:300] for h in hits)
                    lines.append(f"[{n.get('ten')}]\n{body}")
            evidence_text = "\n\n".join(lines)

            # resolve — điền gia_tri từ bằng chứng (chỉ khi có bằng chứng).
            if evidence_text:
                log.info("    [search] %s -> điền giá trị từ bằng chứng", ten)
                rout = await self._llm(SYS_RESOLVE, resolve_prompt(item, evidence_text),
                                       validate=validate_criterion, max_tokens=_STRUCT_MAX_TOKENS)
                if rout.status == "ok":
                    item = rout.data
                else:
                    log.warning("    [search] %s -> lỗi resolve: %s", ten, rout.error)

        # No-fab: nội dung nguon=hsmt vẫn trống gia_tri -> can_review (KHÔNG bịa).
        flagged: list[str] = []
        for n in item.get("noi_dung_can_kiem_tra", []):
            if n.get("nguon", "hsmt") == "hsmt" and not (n.get("gia_tri") or "").strip():
                n["can_review"] = True
                flagged.append(n.get("ten", ""))
        nr = None
        if flagged:
            nr = {"ten": ten, "ly_do": f"chưa tra được giá trị HSMT cho: {', '.join(flagged)} — cần soi"}
        return _Done(detail=item, needs_review=nr)

    # ---- Step 4: gom ----
    @step
    async def collect(self, ctx: Context, ev: _Done) -> StopEvent | None:
        n = await ctx.store.get("n")
        done = ctx.collect_events(ev, [_Done] * n)
        if done is None:
            return None
        group = await ctx.store.get("group")
        added = await ctx.store.get("added")
        listed_n = await ctx.store.get("listed_n")
        criteria = [d.detail for d in done]
        needs = [d.needs_review for d in done if d.needs_review]
        log.info("  [collect] %d tiêu chí, %d cần soi", len(criteria), len(needs))
        return StopEvent(result=self._assemble(group, criteria, added, listed_n, needs))
