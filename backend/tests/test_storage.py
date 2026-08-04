from pathlib import Path
import storage


def test_save_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_DIR", tmp_path)
    rel = storage.save_upload(7, "hsmt.pdf", b"hello", subdir="hsmt")
    assert rel.startswith("7/hsmt/")
    assert storage.read_bytes(rel) == b"hello"
    assert storage.abs_path(rel) == Path(tmp_path) / rel


def test_save_sanitizes_unsafe_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_DIR", tmp_path)
    rel = storage.save_upload(3, "../e v!l.pdf", b"x", subdir="hsmt")
    # tên file đã được làm sạch: không còn '/', khoảng trắng hay ký tự đặc biệt
    stored_name = rel.split("/")[-1]
    assert "/" not in stored_name
    assert ".." not in stored_name or stored_name == ".._e_v_l.pdf"
    assert storage.read_bytes(rel) == b"x"


def test_giu_nguyen_ten_file_tieng_viet_co_dau(tmp_path, monkeypatch):
    """Tên hồ sơ thầu thật luôn có dấu + dấu cách. Bóp thành '1.__N_D__TH_U.pdf' làm chuyên gia
    không nhận ra file mình vừa tải, và tên hỏng đó còn đi thẳng vào bằng chứng của báo cáo."""
    monkeypatch.setattr(storage, "STORAGE_DIR", tmp_path)
    ten = "1. ĐƠN DỰ THẦU - PGĐ ký.pdf"
    rel = storage.save_upload(5, ten, b"x", subdir="hsdt/1")
    assert rel.split("/")[-1] == ten
    assert storage.read_bytes(rel) == b"x"


def test_chan_duong_dan_ca_hai_kieu_phan_cach(tmp_path, monkeypatch):
    """Giữ tên gốc KHÔNG được nới lỏng chống path traversal — bỏ mọi thành phần đường dẫn."""
    monkeypatch.setattr(storage, "STORAGE_DIR", tmp_path)
    for doc, mong_doi in [("../../etc/passwd.pdf", "passwd.pdf"),
                          ("..\\..\\windows\\hosts.pdf", "hosts.pdf"),
                          ("/tuyệt/đối/Đơn dự thầu.pdf", "Đơn dự thầu.pdf")]:
        rel = storage.save_upload(9, doc, b"x", subdir="hsmt")
        stored = rel.split("/")[-1]
        assert stored == mong_doi
        assert "/" not in stored and "\\" not in stored


def test_bo_ky_tu_cam_va_ten_suy_bien(tmp_path, monkeypatch):
    """Ký tự cấm trên Windows/NTFS bị bỏ; tên chỉ còn rác -> tên dự phòng, không ném lỗi."""
    monkeypatch.setattr(storage, "STORAGE_DIR", tmp_path)
    rel = storage.save_upload(4, 'a<b>c:d"e|f?g*h.pdf', b"x", subdir="hsmt")
    stored = rel.split("/")[-1]
    assert stored == "abcdefgh.pdf"

    for xau in ["..", ".", "", "   "]:
        rel = storage.save_upload(4, xau, b"y", subdir="hsmt")
        stored = rel.split("/")[-1]
        assert stored == storage.TEN_DU_PHONG
        assert storage.read_bytes(rel) == b"y"


def test_cat_ngan_ten_qua_dai_ma_giu_duoi_file(tmp_path, monkeypatch):
    """Tiếng Việt 3 byte/ký tự nên tên dài dễ vượt trần 255 byte của filesystem -> phải cắt
    thân tên chứ không cắt đuôi, nếu không file mất luôn phần mở rộng."""
    monkeypatch.setattr(storage, "STORAGE_DIR", tmp_path)
    ten = "Đ" * 300 + ".pdf"
    rel = storage.save_upload(6, ten, b"x", subdir="hsmt")
    stored = rel.split("/")[-1]
    assert stored.endswith(".pdf")
    assert len(stored.encode("utf-8")) <= storage.TRAN_BYTE_TEN
    assert storage.read_bytes(rel) == b"x"
