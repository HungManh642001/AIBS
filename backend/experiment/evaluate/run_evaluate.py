"""CLI: decomposition.json + HSDT (pdf scan) -> evaluation.json/.md (nhóm hợp lệ)."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from experiment.evaluate.evaluate import evaluate_criterion
from experiment.evaluate.ingest import ingest_hsdt
from experiment.evaluate.schema import EvalResult, result_to_json
from experiment.evaluate.vision import default_vision_fn

log = logging.getLogger("experiment.evaluate")


def _legality_criteria(decomp: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in decomp.get("groups", []):
        for c in g.get("criteria", []):
            if c.get("nhom") == "hop_le" or g.get("group") == "hop_le":
                out.append(c)
    return out


def _to_markdown(r: EvalResult) -> str:
    lines = [f"# Đánh giá HSDT (hợp lệ) — {r.doc}", "", f"Tổng: {r.summary}", ""]
    for c in r.criteria:
        flag = " ⛔LOẠI" if c.loai else ""
        lines.append(f"## {c.ten} — **{c.ket_qua}**{flag}")
        for v in c.verdicts:
            lines.append(f"- {v.noi_dung_kiem_tra} (HSDT:{v.hsdt_kiem_tra}) → **{v.ket_qua}** "
                         f"(tin {v.do_tin})")
            lines.append(f"    · chuẩn HSMT: {v.thong_tin_bo_sung or '(không có)'}")
            lines.append(f"    · bằng chứng HSDT [tr {v.trang}]: {v.bang_chung}")
        lines.append("")
    return "\n".join(lines)


async def run(decomposition_path: str, hsdt_files: list[tuple[str, str, bytes]], out_dir: str,
              doc: str = "HSDT", vision_fn: Any | None = None) -> dict[str, Any]:
    # hsdt_files: (tên_file, loai_ho_so [mã catalog đã biết], data pdf)
    vision_fn = vision_fn or default_vision_fn
    decomp = json.loads(Path(decomposition_path).read_text(encoding="utf-8"))
    criteria = _legality_criteria(decomp)
    log.info("[run] %d tiêu chí hợp lệ, %d file HSDT", len(criteria), len(hsdt_files))

    pages = await ingest_hsdt(hsdt_files, vision_fn)
    result = EvalResult(doc=doc)
    for c in criteria:
        result.criteria.append(await evaluate_criterion(c, pages, vision_fn))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "evaluation.json").write_text(
        json.dumps(result_to_json(result), ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "evaluation.md").write_text(_to_markdown(result), encoding="utf-8")
    return {"doc": result.doc, **result.summary}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Đánh giá HSDT nhóm hợp lệ")
    ap.add_argument("--decomp", required=True, help="decomposition.json")
    ap.add_argument("--hsdt", nargs="+", required=True,
                    help="các file HSDT dạng <mã_catalog>=<đường_dẫn.pdf> (loại hồ sơ đã biết)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--doc", default="HSDT")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(message)s", stream=sys.stderr)
    files: list[tuple[str, str, bytes]] = []
    for spec in args.hsdt:
        if "=" not in spec:
            print(f"[run_evaluate] --hsdt cần dạng <mã>=<đường_dẫn>: {spec}", file=sys.stderr)
            return 2
        code, path = spec.split("=", 1)
        files.append((Path(path).name, code.strip(), Path(path).read_bytes()))
    try:
        metrics = asyncio.run(run(args.decomp, files, args.out, doc=args.doc))
    except Exception as exc:  # no-silent-mock
        print(f"[run_evaluate] LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("  Chế độ thật cần LiteLLM proxy phục vụ model VL (đọc ảnh).", file=sys.stderr)
        return 2
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
