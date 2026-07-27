"""Prompt ingest — bóc chữ từ ảnh scan. Ổn định là yêu cầu số một, không phải văn phong."""
from experiment.evaluate.prompts import SYS_INGEST, ingest_prompt


def test_ingest_khong_yeu_cau_suy_luan_truoc():
    """Bóc chữ không cần suy luận: phần CoT vừa tốn token vừa làm kết quả trôi giữa 2 lần chạy."""
    p = ingest_prompt()
    assert "suy luận" not in p.lower()
    assert "json" in p.lower()                       # vẫn phải nêu rõ định dạng trả về


def test_sys_ingest_neu_quy_uoc_bang():
    """Không nêu quy ước thì mỗi lần model tự chọn một cách biểu diễn bảng -> lệch nhau."""
    s = SYS_INGEST.lower()
    assert "bảng" in s
    assert "|" in SYS_INGEST                         # quy ước phân tách ô
    for cam in ("không tóm tắt", "không bỏ"):
        assert cam in s
