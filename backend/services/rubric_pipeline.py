"""Orchestration bóc tiêu chí bằng pipeline agentic (thay extract_rubric).

Chuỗi: HSMT PDF -> extract 4 nhóm (offline) -> chunking (offline) -> build Qdrant index (proxy
embeddings) -> decompose (proxy LLM) -> decomposition.json. Tái dùng NGUYÊN TRẠNG các run() của
experiment/ (không sửa). no-silent-mock: bước nào lỗi (proxy tắt...) -> raise, KHÔNG bịa.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from experiment.chunking.cli_chunk import run as chunk_run          # sync, offline
from experiment.decompose.run_decompose import run as decompose_run  # async, cần proxy (LLM)
from experiment.extract.cli_extract import run as extract_run        # sync, offline
from experiment.index.build_index import run as index_run           # sync, cần proxy (embeddings)

log = logging.getLogger("abes.rubric")


async def build_decomposition(pdf_path: str, workdir: str) -> dict[str, Any]:
    """HSMT PDF -> decomposition.json (dict). workdir chứa artefact per gói (chunks, qdrant, json)."""
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    def _step(n: int, msg: str) -> float:
        log.info("[rubric] (%d/4) %s ...", n, msg)
        return time.perf_counter()

    t = _step(1, "Trích 4 nhóm Chương III (offline)")
    extract_run(pdf_path, str(wd))                      # -> chuong3_groups.json
    log.info("[rubric] (1/4) xong trích 4 nhóm (%.1fs)", time.perf_counter() - t)

    t = _step(2, "Chunking HSMT phân cấp (offline)")
    chunk_run(pdf_path, str(wd))                        # -> chunks.jsonl
    log.info("[rubric] (2/4) xong chunking (%.1fs)", time.perf_counter() - t)

    t = _step(3, "Build Qdrant index — cần embeddings (proxy)")
    index_run(chunks_path=str(wd / "chunks.jsonl"),
              db_path=str(wd / "qdrant"), out_dir=str(wd))          # -> Qdrant on-disk
    log.info("[rubric] (3/4) xong build index (%.1fs)", time.perf_counter() - t)

    t = _step(4, "Decompose tiêu chí — cần LLM (proxy)")
    await decompose_run(groups_path=str(wd / "chuong3_groups.json"),
                        db_path=str(wd / "qdrant"), out_dir=str(wd))  # -> decomposition.json
    log.info("[rubric] (4/4) xong decompose (%.1fs)", time.perf_counter() - t)

    log.info("[rubric] HOÀN TẤT bóc tiêu chí trong %.1fs", time.perf_counter() - t0)
    return json.loads((wd / "decomposition.json").read_text(encoding="utf-8"))
