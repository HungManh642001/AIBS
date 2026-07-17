"""Orchestration bóc tiêu chí bằng pipeline ĐA NGUỒN (thay extract_rubric).

Chuỗi (run_multi): chunk HSMT (pdf-text) -> extract 4 nhóm (offline) -> OCR mỗi nguồn scan (TBMT)
-> tóm tắt vai trò nguồn -> gộp chunks -> build Qdrant index (proxy embeddings) -> decompose kèm
chunks_path (bảng neo E-BDL + nguyên văn TBMT) + summaries (route mềm theo nguồn). Tái dùng NGUYÊN
TRẠNG run_multi của experiment/multisource (không sửa). no-silent-mock: bước nào lỗi -> raise.

TBMT (scan) chứa mốc đóng/mở thầu -> bảng neo tự đủ chuẩn tương đối ("≥120 ngày kể từ đóng thầu").
Không có nguồn scan -> run_multi vẫn chạy đúng (chỉ HSMT), và VẪN truyền chunks_path (vá lỗ hổng
bảng neo E-BDL của đường đơn nguồn cũ).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from experiment.multisource.run_rubric import run_multi   # async, cần proxy (vision OCR + LLM + embed)

log = logging.getLogger("abes.rubric")


async def build_decomposition(pdf_path: str, workdir: str,
                              scan_sources: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    """HSMT PDF (+ nguồn scan TBMT) -> decomposition.json (dict). workdir chứa artefact per gói.

    scan_sources: [(source_doc, đường_dẫn_pdf)] các tài liệu scan gói thầu (vd TBMT). Rỗng -> chỉ HSMT.
    """
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    scan = scan_sources or []
    log.info("[rubric] bắt đầu bóc tiêu chí (đa nguồn): HSMT + %d nguồn scan", len(scan))

    await run_multi(pdf_path, scan, str(wd))            # -> wd/decomposition.json

    log.info("[rubric] HOÀN TẤT bóc tiêu chí trong %.1fs", time.perf_counter() - t0)
    return json.loads((wd / "decomposition.json").read_text(encoding="utf-8"))
