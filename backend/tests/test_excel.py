import io
from openpyxl import Workbook
from services import documents


def _make_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BangGia"
    ws.append(["STT", "Hạng mục", "Đơn giá", "Số lượng", "Thành tiền"])
    ws.append([1, "Máy chủ", 100, 2, 200])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_excel_reads_sheet_rows():
    sheets = documents.parse_excel(_make_xlsx())
    assert sheets[0]["sheet"] == "BangGia"
    assert sheets[0]["rows"][1] == [1, "Máy chủ", 100, 2, 200]


def test_extract_document_excel_returns_pagetext():
    pages = documents.extract_document(_make_xlsx(), "excel")
    assert pages[0]["page"] == 1
    assert "Máy chủ" in pages[0]["text"]
