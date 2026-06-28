"""CLI: chuong3_groups.json + vector index -> decomposition.json/.md + report.

Chế độ thật cần LiteLLM proxy (LLM phân rã). Truy hồi qua index Qdrant on-disk.
Test offline tiêm llm_fn/retrieve_fn kịch bản (xem tests/).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config import get_settings

from experiment.decompose.llm import default_llm_fn
from experiment.decompose.retrieval import open_disk_index
from experiment.decompose.schema import DecomposeResult, GroupDecomposition, result_to_json
from experiment.decompose.workflow import DecomposeWorkflow

_DEFAULT_GROUPS = "out/chuong3_groups.json"
_DEFAULT_DB = "out/qdrant"
_DEFAULT_OUT = "out"


def _to_markdown(r: DecomposeResult) -> str:
    lines = [f"# Phân rã tiêu chí — {r.doc}", "", f"Tổng: {r.summary}", ""]
    for g in r.groups:
        lines.append(f"## {g.group} — {g.muc}")
        if g.is_reference:
            lines.append(f"> tham chiếu: {g.ref_target}")
        lines.append(
            f"- coverage: listed={g.coverage.listed_n} final={g.coverage.final_n} "
            f"added={g.coverage.added_by_critique}"
        )
        for c in g.criteria:
            flag = " ⚠️cần soi" if c.get("can_review") else ""
            lines.append(f"- **{c.get('ten')}** ({c.get('nhom')}/{c.get('kieu')}){flag}")
            for sc in c.get("sub_checks", []):
                cr = " [can_review]" if sc.get("thong_so", {}).get("can_review") else ""
                lines.append(f"    - {sc.get('ten')} · {sc.get('check_type')}{cr}")
        if g.needs_review:
            lines.append(f"- needs_review: {g.needs_review}")
        lines.append("")
    return "\n".join(lines)


async def run(
    groups_path: str = _DEFAULT_GROUPS,
    db_path: str = _DEFAULT_DB,
    out_dir: str = _DEFAULT_OUT,
    llm_fn: Any | None = None,
    retrieve_fn: Any | None = None,
    settings: Any | None = None,
) -> dict[str, Any]:
    """Phân rã 4 nhóm; ghi decomposition.json/.md + report; trả metrics."""
    settings = settings or get_settings()
    gp = Path(groups_path)
    if not gp.exists():
        raise FileNotFoundError(f"Không thấy {gp} (chạy bước extract trước)")
    data = json.loads(gp.read_text(encoding="utf-8"))

    llm_fn = llm_fn or default_llm_fn
    close_client = None
    if retrieve_fn is None:
        close_client, retrieve_fn = open_disk_index(db_path, settings)

    try:
        result = DecomposeResult(doc=data.get("doc", "HSMT"))
        for g in data.get("groups", []):
            wf = DecomposeWorkflow(llm_fn=llm_fn, retrieve_fn=retrieve_fn, timeout=600)
            gd: GroupDecomposition = await wf.run(group=g)
            result.groups.append(gd)
    finally:
        if close_client is not None:
            close_client.close()

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "decomposition.json").write_text(
        json.dumps(result_to_json(result), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "decomposition.md").write_text(_to_markdown(result), encoding="utf-8")
    metrics = {"doc": result.doc, **result.summary,
               "groups": [g.group for g in result.groups]}
    (out / "decompose_report.md").write_text(
        f"# Decompose report\n\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n", encoding="utf-8"
    )
    return metrics


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phân rã tiêu chí (agentic workflow)")
    ap.add_argument("--groups", default=_DEFAULT_GROUPS)
    ap.add_argument("--db", default=_DEFAULT_DB)
    ap.add_argument("--out", default=_DEFAULT_OUT)
    args = ap.parse_args(argv)
    try:
        metrics = asyncio.run(run(groups_path=args.groups, db_path=args.db, out_dir=args.out))
    except Exception as exc:  # no-silent-mock: báo lỗi rõ
        print(f"[run_decompose] LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("  Chế độ thật cần LiteLLM proxy chạy & phục vụ model. ", file=sys.stderr)
        return 2
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
