"""Agentic Workflow (LlamaIndex) phân rã 1 nhóm: list -> critique-coverage -> detail (fan-out).

Bước detail (mỗi tiêu chí) gồm 3 lượt: structure (3a) -> sinh sub-query + truy hồi (3b) ->
resolve (3c, chỉ khi có thong_so._need và có bằng chứng). Còn _need sót -> ép can_review.
"""
from __future__ import annotations

import logging
from typing import Any

from llama_index.core.workflow import Context, Event, StartEvent, StopEvent, Workflow, step

from services.ai_schemas import validate_criteria_list, validate_criterion_detail

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
from experiment.decompose.schema import Coverage, GroupDecomposition, norm_ten

log = logging.getLogger("experiment.decompose")


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


class _Critiqued(Event):
    crits: list
    added: list
    listed_n: int


class _DetailReq(Event):
    crit: dict


class _DetailDone(Event):
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

    # ---- bước 1: liệt kê + tự phản biện coverage ----
    @step
    async def list_and_critique(self, ctx: Context, ev: StartEvent) -> _Critiqued | StopEvent:
        group = ev.group
        log.info("[nhóm %s] %s", group.get("group", ""), group.get("muc", ""))
        source = self._build_source(group)
        await ctx.store.set("group", group)
        await ctx.store.set("source", source)

        out = await self._llm(SYS_LIST, list_prompt(source), validate=validate_criteria_list)
        if out.status == "error":
            # Cả nhóm lỗi liệt kê -> không bịa, trả needs_review.
            gd = self._assemble(group, [], [], 0, [{"ten": "(toàn nhóm)", "ly_do": f"lỗi AI liệt kê: {out.error}"}])
            return StopEvent(result=gd)

        listed = list(out.data.get("criteria", []))
        listed_n = len(listed)
        seen = {norm_ten(c.get("ten", "")) for c in listed}

        added: list[str] = []
        cout = await self._llm(SYS_CRITIQUE, critique_prompt(source, listed), validate=validate_criteria_list)
        if cout.status == "ok":
            for m in cout.data.get("criteria", []):
                key = norm_ten(m.get("ten", ""))
                if key and key not in seen:
                    seen.add(key)
                    listed.append(m)
                    added.append(m.get("ten", ""))
        log.info("  [list] %d tiêu chí; [critique] +%d sót", listed_n, len(added))
        return _Critiqued(crits=listed, added=added, listed_n=listed_n)

    # ---- bước 2: fan-out chi tiết từng tiêu chí ----
    @step
    async def fan_out(self, ctx: Context, ev: _Critiqued) -> _DetailReq | StopEvent:
        await ctx.store.set("added", ev.added)
        await ctx.store.set("listed_n", ev.listed_n)
        group = await ctx.store.get("group")
        if not ev.crits:
            return StopEvent(result=self._assemble(group, [], ev.added, ev.listed_n))
        log.info("  [fan-out] %d tiêu chí -> detail", len(ev.crits))
        await ctx.store.set("n", len(ev.crits))
        for c in ev.crits:
            ctx.send_event(_DetailReq(crit=c))
        return None

    # ---- bước 3: chi tiết 1 tiêu chí: structure -> sub-query+truy hồi -> resolve ----
    @step
    async def detail(self, ctx: Context, ev: _DetailReq) -> _DetailDone:
        crit = ev.crit
        source = await ctx.store.get("source")
        ten = crit.get("ten", "")
        log.info("    [detail] %s", ten)

        # 3a — phân rã cấu trúc (đánh dấu thong_so._need cho số còn thiếu)
        out = await self._llm(SYS_STRUCT, struct_prompt(crit, source), validate=validate_criterion_detail)
        if out.status == "error":
            log.warning("    [detail] %s -> lỗi structure: %s", ten, out.error)
            item = {
                "nhom": crit.get("nhom", "hop_le"),
                "ten": ten,
                "yeu_cau": "",
                "required_artifacts": crit.get("required_artifacts", []),
                "kieu": "pass_fail",
                "trong_so": 0.0,
                "sub_checks": [],
                "proposed_artifacts": [],
                "can_review": True,
                "loi_ai": out.error,
            }
            return _DetailDone(detail=item, needs_review={"ten": ten, "ly_do": f"lỗi AI: {out.error}"})

        item = out.data
        needs = [sc for sc in item.get("sub_checks", []) if sc.get("thong_so", {}).get("_need")]

        # 3b — sinh sub-query cho từng cái thiếu rồi truy hồi nhắm vào nó
        evidence_text = ""
        if needs and self._retrieve:
            log.info("    [detail] %s -> %d sub_check thiếu số, sinh sub-query", ten, len(needs))
            queries: dict[str, str] = {}
            qout = await self._llm(SYS_QUERY, query_prompt(crit, needs), validate=_validate_queries)
            if qout.status == "ok":
                for q in qout.data.get("queries", []):
                    queries[norm_ten(q.get("ten", ""))] = q.get("query", "")
            lines: list[str] = []
            for sc in needs:
                q = queries.get(norm_ten(sc.get("ten", ""))) or f"{ten} {sc.get('ten', '')}"
                log.info("      [retrieve] %s", q)
                hits = self._retrieve(q, k=3)
                if hits:
                    body = "\n".join(h["text"][:300] for h in hits)
                    lines.append(f"[{sc.get('ten')}]\n{body}")
            evidence_text = "\n\n".join(lines)

            # 3c — resolve CHỈ khi có bằng chứng (không có thì để _need -> ép can_review)
            if evidence_text:
                log.info("    [detail] %s -> resolve từ bằng chứng", ten)
                rout = await self._llm(
                    SYS_RESOLVE, resolve_prompt(item, evidence_text), validate=validate_criterion_detail
                )
                if rout.status == "ok":
                    item = rout.data
                else:
                    log.warning("    [detail] %s -> lỗi resolve: %s", ten, rout.error)

        # No-fabrication: _need còn sót (chưa giải quyết) -> ép can_review; gom needs_review.
        flagged: list[str] = []
        for sc in item.get("sub_checks", []):
            ts = sc.setdefault("thong_so", {})
            if ts.pop("_need", None):
                ts["can_review"] = True
            if ts.get("can_review"):
                flagged.append(sc.get("ten", ""))
        nr = None
        if flagged:
            nr = {"ten": ten, "ly_do": f"không truy được số ngưỡng (BDS) cho: {', '.join(flagged)} — cần soi"}
        return _DetailDone(detail=item, needs_review=nr)

    # ---- bước 4: gom ----
    @step
    async def collect(self, ctx: Context, ev: _DetailDone) -> StopEvent | None:
        n = await ctx.store.get("n")
        done = ctx.collect_events(ev, [_DetailDone] * n)
        if done is None:
            return None
        group = await ctx.store.get("group")
        added = await ctx.store.get("added")
        listed_n = await ctx.store.get("listed_n")
        criteria = [d.detail for d in done]
        needs = [d.needs_review for d in done if d.needs_review]
        log.info("  [collect] %d tiêu chí, %d cần soi", len(criteria), len(needs))
        return StopEvent(result=self._assemble(group, criteria, added, listed_n, needs))
