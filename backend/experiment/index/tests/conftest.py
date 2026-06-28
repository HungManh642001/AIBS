# backend/experiment/index/tests/conftest.py
import json
from pathlib import Path

import pytest

from experiment.index.embedder import DeterministicEmbedding

_OUT_DIR = Path(__file__).resolve().parents[1].parent / "out"


@pytest.fixture
def sample_chunks():
    """Đọc out/chunks.jsonl (artefact bước chunking). Skip nếu chưa chạy chunking."""
    path = _OUT_DIR / "chunks.jsonl"
    if not path.exists():
        pytest.skip("Không có out/chunks.jsonl — chạy bước chunking trước")
    chunks = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {"path": str(path), "chunks": chunks}


@pytest.fixture
def det_embedder():
    return DeterministicEmbedding()
