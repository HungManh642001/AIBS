# backend/experiment/extract/tests/conftest.py
import glob
from pathlib import Path

import pytest

_SAMPLES_DIR = Path(__file__).resolve().parents[1].parent / "samples"


@pytest.fixture
def sample_pdf():
    hits = sorted(glob.glob(str(_SAMPLES_DIR / "*.pdf")))
    if not hits:
        pytest.skip("Không có HSMT mẫu trong samples/ — bỏ qua test tích hợp")
    return hits[0]
