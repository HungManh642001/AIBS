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
from experiment.multisource.manifest import Manifest, hash_file, hash_ma_nguon, khoa
from experiment.multisource.merge import merge_chunk_files
from experiment.multisource.ocr_chunks import ocr_scan_to_chunks
from experiment.multisource.summarize import summarize_source

from config import get_settings

# log = logging.getLogger("experiment.multisource")
from experiment.logger_config import setup_logger
log = setup_logger('MULTISOURCE', 'multisource.log')

_GOC = Path(__file__).resolve().parents[1]          # backend/experiment


def _doc_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


async def run_multi(hsmt_pdf: str, scan_sources: list[tuple[str, str]], out_dir: str,
                    vision_fn: Any | None = None, embed: Any | None = None,
                    llm_fn: Any | None = None, retrieve_fn: Any | None = None,
                    force: bool = False) -> dict[str, Any]:
    """HSMT + danh sách (source_doc, scan_pdf) -> decomposition.json (đa nguồn). Trả metrics decompose.

    force=True: chạy lại cả 3 bước chuẩn bị dù đầu vào không đổi (xem manifest.py).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mf = Manifest(out)
    h_hsmt = hash_file(hsmt_pdf)

    # (1) chunk HSMT — hàm thuần của file HSMT + mã chunker.
    chunks_path = out / "chunks.jsonl"
    k1 = khoa(h_hsmt, hash_ma_nguon(_GOC / "chunking"))
    if not force and mf.con_moi("chunk", k1, [chunks_path]):
        log.info("[multi] (1/5) chunk HSMT — BỎ QUA (đầu vào không đổi)")
    else:
        log.info("[multi] (1/5) chunk HSMT")
        mf.bo("chunk")                                  # lỗi giữa chừng -> lần sau không tin file dở
        chunk_run(hsmt_pdf, str(out))                   # -> out/chunks.jsonl
        mf.ghi("chunk", k1)

    # (2) extract Chương III — cũng chỉ phụ thuộc file HSMT + mã extract.
    groups_path = out / "chuong3_groups.json"
    k2 = khoa(h_hsmt, hash_ma_nguon(_GOC / "extract"))
    if not force and mf.con_moi("extract", k2, [groups_path]):
        log.info("[multi] (2/5) extract Chương III (HSMT) — BỎ QUA (đầu vào không đổi)")
    else:
        log.info("[multi] (2/5) extract Chương III (HSMT)")
        mf.bo("extract")
        extract_run(hsmt_pdf, str(out))                 # -> out/chuong3_groups.json
        mf.ghi("extract", k2)

    # (3) OCR từng nguồn scan — có gọi vision nên khóa thêm TÊN MODEL.
    ma_ocr = hash_ma_nguon(_GOC / "multisource" / "ocr_chunks.py",
                           _GOC / "multisource" / "summarize.py")
    model = getattr(get_settings(), "ai_model", "")
    spath = out / "source_summaries.json"
    summaries_cu = {}
    if spath.is_file():
        try:
            summaries_cu = json.loads(spath.read_text(encoding="utf-8"))
        except ValueError:
            summaries_cu = {}

    extra: list[dict] = []
    summaries: dict[str, str] = {}
    for source_doc, pdf in scan_sources:
        buoc = f"ocr:{source_doc}"
        ocr_path = out / f"ocr_{source_doc}.jsonl"      # phải lưu riêng mới bỏ qua được
        k3 = khoa(hash_file(pdf), ma_ocr, model)
        if not force and source_doc in summaries_cu and mf.con_moi(buoc, k3, [ocr_path, spath]):
            log.info("[multi] (3/5) OCR %s — BỎ QUA (đầu vào không đổi)", source_doc)
            sc = _doc_jsonl(ocr_path)
            summaries[source_doc] = summaries_cu[source_doc]
        else:
            log.info("[multi] (3/5) OCR %s", source_doc)
            mf.bo(buoc)
            sc = await ocr_scan_to_chunks(pdf, source_doc=source_doc, vision_fn=vision_fn)
            summaries[source_doc] = await summarize_source(source_doc, sc, llm_fn=llm_fn)
            ocr_path.write_text(
                "\n".join(json.dumps(c, ensure_ascii=False) for c in sc), encoding="utf-8")
            mf.ghi(buoc, k3)
        extra.extend(sc)

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
    ap.add_argument("--force", action="store_true",
                    help="chạy lại chunk/extract/OCR dù đầu vào không đổi")
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
        metrics = asyncio.run(run_multi(args.hsmt, sources, args.out, force=args.force))
    except Exception as exc:  # no-silent-mock
        print(f"[run_rubric] LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("  Chế độ thật cần LiteLLM proxy (vision OCR + LLM + embeddings).", file=sys.stderr)
        return 2
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
