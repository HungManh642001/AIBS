"""Agentic Workflow (LlamaIndex) phân rã 1 nhóm: list -> critique-coverage -> detail (fan-out)."""
from __future__ import annotations

from typing import Any

from llama_index.core.workflow import Context, Event, StartEvent, StopEvent, Workflow, step

from services.ai_schemas import validate_criteria_list, validate_criterion_detail

from experiment.decompose.llm import LlmFn
from experiment.decompose.prompts import (
    SYS_CRITIQUE,
    SYS_DETAIL,
    SYS_LIST,
    critique_prompt,
    detail_prompt,
    list_prompt,
)
from experiment.decompose.retrieval import RetrieveFn
from experiment.decompose.schema import Coverage, GroupDecomposition, norm_ten

# check_type cần ngưỡng số -> khi thiếu bằng chứng phải can_review (không bịa).
_THRESHOLD_TYPES = {"value_threshold", "date_validity"}


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
        return _Critiqued(crits=listed, added=added, listed_n=listed_n)

    # ---- bước 2: fan-out chi tiết từng tiêu chí ----
    @step
    async def fan_out(self, ctx: Context, ev: _Critiqued) -> _DetailReq | StopEvent:
        await ctx.store.set("added", ev.added)
        await ctx.store.set("listed_n", ev.listed_n)
        group = await ctx.store.get("group")
        if not ev.crits:
            return StopEvent(result=self._assemble(group, [], ev.added, ev.listed_n))
        await ctx.store.set("n", len(ev.crits))
        for c in ev.crits:
            ctx.send_event(_DetailReq(crit=c))
        return None

    # ---- bước 3: chi tiết 1 tiêu chí (retrieval bằng chứng + no-fabrication) ----
    @step
    async def detail(self, ctx: Context, ev: _DetailReq) -> _DetailDone:
        crit = ev.crit
        source = await ctx.store.get("source")
        ten = crit.get("ten", "")

        evidence: list[dict] = []
        if self._retrieve:
            evidence = self._retrieve(f"{ten} giá trị hiệu lực yêu cầu HSMT", k=3)
        ev_text = "\n".join(h["text"][:300] for h in evidence)

        out = await self._llm(
            SYS_DETAIL, detail_prompt(crit, source, ev_text), validate=validate_criterion_detail
        )
        if out.status == "error":
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
        nr = None
        if not evidence:
            # Thiếu bằng chứng -> mọi sub_check cần ngưỡng phải can_review (KHÔNG bịa số).
            flagged = False
            for sc in item.get("sub_checks", []):
                if sc.get("check_type") in _THRESHOLD_TYPES:
                    sc.setdefault("thong_so", {})["can_review"] = True
                    flagged = True
            if flagged:
                nr = {"ten": ten, "ly_do": "không truy được số ngưỡng (BDS) — cần soi"}
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
        return StopEvent(result=self._assemble(group, criteria, added, listed_n, needs))
