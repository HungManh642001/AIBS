from experiment.chunking.schema import Heading, LEVEL_PHAN, LEVEL_CHUONG, LEVEL_MUC
from experiment.chunking.structure import roman_to_int, drop_toc_clusters, keep_monotonic_chapters


def _h(kind, level, number, page):
    return Heading(kind=kind, level=level, number=number, title=f"{kind} {number}",
                   page=page, y0=100.0)


def test_roman_to_int():
    assert [roman_to_int(x) for x in ("I", "II", "III", "IV", "V")] == [1, 2, 3, 4, 5]


def test_drop_toc_clusters_removes_dense_overview_page():
    toc = [_h("phan", LEVEL_PHAN, "1", 2), _h("chuong", LEVEL_CHUONG, "I", 2),
           _h("chuong", LEVEL_CHUONG, "II", 2), _h("chuong", LEVEL_CHUONG, "III", 2),
           _h("chuong", LEVEL_CHUONG, "IV", 2)]
    body = [_h("chuong", LEVEL_CHUONG, "I", 5), _h("muc", LEVEL_MUC, "1", 6)]
    kept = drop_toc_clusters(toc + body)
    assert all(h.page != 2 for h in kept)
    assert any(h.page == 5 for h in kept)


def test_keep_monotonic_chapters_drops_out_of_sequence():
    seq = [_h("chuong", LEVEL_CHUONG, "I", 5), _h("muc", LEVEL_MUC, "1", 6),
           _h("chuong", LEVEL_CHUONG, "III", 9),   # nhảy cóc -> loại (inline ref sót)
           _h("chuong", LEVEL_CHUONG, "II", 23),   # đúng thứ tự -> giữ
           _h("chuong", LEVEL_CHUONG, "III", 27)]
    kept = keep_monotonic_chapters(seq)
    chapters = [(h.number, h.page) for h in kept if h.kind == "chuong"]
    assert chapters == [("I", 5), ("II", 23), ("III", 27)]
    assert any(h.kind == "muc" for h in kept)  # Mục không bị đụng
