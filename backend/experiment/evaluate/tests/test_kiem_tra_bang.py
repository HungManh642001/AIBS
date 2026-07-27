"""Tự kiểm text bảng do vision bóc — bắt dấu hiệu bóc thiếu/lệch cột trước khi dùng để chấm."""
from experiment.evaluate.tu_kiem import kiem_tra_bang


def _bang(*hang: str) -> str:
    return "\n".join(hang)


def test_bang_deu_o_thi_khong_van_de():
    got = kiem_tra_bang(_bang("STT | Ten | Tien",
                              "1 | May chu | 100",
                              "2 | UPS | 200"))
    assert got == []


def test_o_trong_van_tinh_la_deu():
    """Ô trống là bình thường trong bảng giá (dòng tổng nhóm) — không được báo nhầm."""
    assert kiem_tra_bang(_bang("STT | Ten | Tien", "I | Hang hoa |  ", "1 | May chu | 100")) == []


def test_so_o_lech_thi_bao():
    got = kiem_tra_bang(_bang("STT | Ten | Tien", "1 | May chu | 100", "2 | UPS"))
    assert got and any("cột" in v for v in got)


def test_dau_hieu_tom_tat_thi_bao():
    for tom in ("...", "v.v", "tương tự", "(còn tiếp)"):
        got = kiem_tra_bang(_bang("STT | Ten | Tien", "1 | May chu | 100", f"2 | {tom} | 200"))
        assert got and any("tóm tắt" in v for v in got), tom


def test_text_khong_phai_bang_thi_bo_qua():
    """Trang văn bản thường (đơn dự thầu) không có bảng -> không áp quy tắc cột."""
    assert kiem_tra_bang("ĐƠN DỰ THẦU\nKính gửi: Bên mời thầu\nChúng tôi cam kết...") == []


def test_mot_dong_bang_duy_nhat_khong_du_de_ket_luan():
    """1 hàng thì không có gì để so số cột — không được báo bừa."""
    assert kiem_tra_bang("STT | Ten | Tien") == []
