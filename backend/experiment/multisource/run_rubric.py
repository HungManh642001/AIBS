"""Orchestrator RUBRIC ĐA NGUỒN (experiment) — đo chính xác trước khi tích hợp backend.

Chuỗi: chunk HSMT (pdf-text) -> OCR mỗi tài liệu scan (TBMT...) -> tóm tắt vai trò từng nguồn
(source_summaries.json — người sửa tay được) -> gộp chunks (source_doc) -> build index (mọi
nguồn) -> decompose (route mềm theo nguồn). Trích tiêu chí (Chương III) CHỈ từ HSMT.

Đo chính xác (server có proxy): chạy có TBMT vs không TBMT, so trong decomposition.md các nội dung
về thời gian (đóng thầu/hiệu lực): PASS nếu thong_tin_bo_sung được điền + nguon="Thông báo mời thầu tr N";
FAIL nếu còn '⚠️cần soi' (can_review). no-silent-mock: bước nào lỗi (proxy tắt) -> raise, không bịa.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from experiment.chunking.cli_chunk import run as chunk_run
from experiment.extract.cli_extract import run as extract_run
from experiment.index.build_index import run as index_run
from experiment.decompose.run_decompose import run as decompose_run
from experiment.multisource.merge import merge_chunk_files
from experiment.multisource.ocr_chunks import ocr_scan_to_chunks
from experiment.multisource.summarize import summarize_source

# log = logging.getLogger("experiment.multisource")
from experiment.logger_config import setup_logger
log = setup_logger('MULTISOURCE', 'multisource.log')

async def run_multi(hsmt_pdf: str, scan_sources: list[tuple[str, str]], out_dir: str,
                    vision_fn: Any | None = None, embed: Any | None = None,
                    llm_fn: Any | None = None, retrieve_fn: Any | None = None) -> dict[str, Any]:
    """HSMT + danh sách (source_doc, scan_pdf) -> decomposition.json (đa nguồn). Trả metrics decompose."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    log.info("[multi] (1/5) chunk HSMT")
    chunk_run(hsmt_pdf, str(out))                       # -> out/chunks.jsonl
    log.info("[multi] (2/5) extract Chương III (HSMT)")
    extract_run(hsmt_pdf, str(out))                     # -> out/chuong3_groups.json

    extra: list[dict] = []
    summaries: dict[str, str] = {}
    for source_doc, pdf in scan_sources:
        log.info("[multi] (3/5) OCR %s", source_doc)
        sc = await ocr_scan_to_chunks(pdf, source_doc=source_doc, vision_fn=vision_fn)
        extra.extend(sc)
        summaries[source_doc] = await summarize_source(source_doc, sc, llm_fn=llm_fn)

    spath = out / "source_summaries.json"
    spath.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")

    merged = str(out / "chunks_merged.jsonl")
    n = merge_chunk_files(str(out / "chunks.jsonl"), extra, merged)
    log.info("[multi] (4/5) build index: %d chunk (%d nguồn scan)", n, len(scan_sources))
    index_run(chunks_path=merged, db_path=str(out / "qdrant"), out_dir=str(out), embed=embed)

    log.info("[multi] (5/5) decompose")
    return await decompose_run(groups_path=str(out / "chuong3_groups.json"),
                               db_path=str(out / "qdrant"), out_dir=str(out),
                               llm_fn=llm_fn, retrieve_fn=retrieve_fn,
                               chunks_path=merged,      # nạp dòng A-BDL làm phụ lục resolve
                               summaries_path=str(spath))  


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rubric đa nguồn (HSMT + scan mời thầu)")
    ap.add_argument("--hsmt", default="experiment/samples/62/A-HSMT.pdf", help="HSMT pdf-text")
    ap.add_argument("--scan", nargs="*", default=[], help="các nguồn scan <source_doc>=<đường_dẫn.pdf>")
    ap.add_argument("--out", default="experiment/out_multi")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(message)s", stream=sys.stderr)
    sources: list[tuple[str, str]] = []
    for spec in args.scan:
        if "=" not in spec:
            print(f"[run_rubric] --scan cần <source_doc>=<đường_dẫn>: {spec}", file=sys.stderr)
            return 2
        sd, path = spec.split("=", 1)
        sources.append((sd.strip(), path))
    try:
        metrics = asyncio.run(run_multi(args.hsmt, sources, args.out))
    except Exception as exc:  # no-silent-mock
        print(f"[run_rubric] LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("  Chế độ thật cần LiteLLM proxy (vision OCR + LLM + embeddings).", file=sys.stderr)
        return 2
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
