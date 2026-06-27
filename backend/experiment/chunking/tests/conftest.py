from pathlib import Path

import pytest

_SAMPLE = (Path(__file__).resolve().parents[1].parent
           / "samples" / "E-HSMT gói thầu số VT-1954.25-KT-TTH.pdf")


@pytest.fixture
def sample_pdf():
    if not _SAMPLE.exists():
        pytest.skip("HSMT sample không có trong samples/ — bỏ qua test tích hợp")
    return str(_SAMPLE)
