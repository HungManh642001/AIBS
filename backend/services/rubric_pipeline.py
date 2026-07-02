"""Orchestration bóc tiêu chí bằng pipeline agentic (thay extract_rubric).

Chuỗi: HSMT PDF -> extract 4 nhóm (offline) -> chunking (offline) -> build Qdrant index (proxy
embeddings) -> decompose (proxy LLM) -> decomposition.json. Tái dùng NGUYÊN TRẠNG các run() của
experiment/ (không sửa). no-silent-mock: bước nào lỗi (proxy tắt...) -> raise, KHÔNG bịa.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from experiment.chunking.cli_chunk import run as chunk_run          # sync, offline
from experiment.decompose.run_decompose import run as decompose_run  # async, cần proxy (LLM)
from experiment.extract.cli_extract import run as extract_run        # sync, offline
from experiment.index.build_index import run as index_run           # sync, cần proxy (embeddings)


async def build_decomposition(pdf_path: str, workdir: str) -> dict[str, Any]:
    """HSMT PDF -> decomposition.json (dict). workdir chứa artefact per gói (chunks, qdrant, json)."""
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)

    extract_run(pdf_path, str(wd))                      # -> chuong3_groups.json
    chunk_run(pdf_path, str(wd))                        # -> chunks.jsonl
    index_run(chunks_path=str(wd / "chunks.jsonl"),
              db_path=str(wd / "qdrant"), out_dir=str(wd))          # -> Qdrant on-disk
    await decompose_run(groups_path=str(wd / "chuong3_groups.json"),
                        db_path=str(wd / "qdrant"), out_dir=str(wd))  # -> decomposition.json

    return json.loads((wd / "decomposition.json").read_text(encoding="utf-8"))
