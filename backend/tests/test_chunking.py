from services.extraction import chunk_pages, _merge_criteria


def test_chunk_pages_splits_on_budget():
    pages = [{"page": i, "text": "x" * 5000} for i in range(1, 5)]
    chunks = chunk_pages(pages, max_chars=12000, overlap=0)
    assert len(chunks) >= 2
    assert all(len(c) <= 12000 + 200 for c in chunks)  # cộng nhãn [Trang N]


def test_chunk_pages_single_when_small():
    pages = [{"page": 1, "text": "ngắn"}]
    assert len(chunk_pages(pages, max_chars=12000, overlap=0)) == 1


def test_merge_criteria_dedupes_by_normalized_ten():
    a = [{"ten": "Đơn dự thầu"}, {"ten": "Bảo đảm dự thầu"}]
    b = [{"ten": "DON DU THAU"}, {"ten": "Hợp đồng tương tự"}]
    merged = _merge_criteria([a, b])
    tens = [c["ten"] for c in merged]
    assert tens == ["Đơn dự thầu", "Bảo đảm dự thầu", "Hợp đồng tương tự"]
