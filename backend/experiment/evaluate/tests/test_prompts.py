from experiment.evaluate.prompts import SYS_EVAL, ingest_prompt, eval_prompt
from experiment.evaluate.schema import (
    HINH_THUC_DOC_LAP, HINH_THUC_LIEN_DANH, NGUON_HO_SO, NGUON_KHAI_BAO,
    VendorContext, VendorProfile,
)

_ND = {"noi_dung_kiem_tra": "Giá trị bảo lãnh", "yeu_cau": "Thỏa mãn giá trị",
       "thong_tin_bo_sung": "6.100.000 VNĐ"}


def test_ingest_prompt_ocr_only_no_classification():
    p = ingest_prompt()
    assert "[IN]" in p
    assert "text" in p and "co_chu_ky" in p
    assert "loai_ho_so" not in p              # loại hồ sơ đã biết khi tải -> KHÔNG bắt LLM phân loại


def test_eval_prompt_carries_standard_and_tag():
    nd = {"noi_dung_kiem_tra": "Giá trị bảo lãnh", "yeu_cau": "Thỏa mãn giá trị",
          "thong_tin_bo_sung": "6.100.000 VNĐ"}
    p = eval_prompt(nd, "Trang HSDT: bảo lãnh 6.100.000")
    assert "[EV:Giá trị bảo lãnh]" in p
    assert "6.100.000 VNĐ" in p          # chuẩn HSMT (thong_tin_bo_sung)
    assert "Thỏa mãn giá trị" in p        # yêu cầu
    assert "Trang HSDT" in p              # nội dung HSDT
    assert "KIỂU CHECK" not in p          # đã bỏ kieu_check


def test_eval_prompt_states_vendor_form_when_doc_lap():
    """Biết chắc độc lập -> nêu hình thức + căn cứ, và MỞ tùy chọn N/A trong schema hint."""
    p = eval_prompt(_ND, "text", vendor_ctx=VendorContext(ten="Công ty ABC"),
                    profile=VendorProfile(hinh_thuc=HINH_THUC_DOC_LAP, nguon=NGUON_KHAI_BAO))
    assert "[NHÀ THẦU]" in p and "Công ty ABC" in p
    assert "độc lập" in p and NGUON_KHAI_BAO in p
    assert "không áp dụng" in p


def test_eval_prompt_hides_vendor_form_when_unknown():
    """Hình thức không rõ -> KHÔNG nêu + KHÔNG mở N/A (AI không được tự tuyên)."""
    p = eval_prompt(_ND, "text", profile=VendorProfile())
    assert "[NHÀ THẦU]" not in p
    assert "không áp dụng" not in p


def test_eval_prompt_lien_danh_states_form_but_no_na_option():
    """Liên danh -> nêu hình thức nhưng KHÔNG mở N/A (N/A chỉ có nghĩa với độc lập)."""
    p = eval_prompt(_ND, "t", profile=VendorProfile(hinh_thuc=HINH_THUC_LIEN_DANH, nguon=NGUON_HO_SO))
    assert "[NHÀ THẦU]" in p and "liên danh" in p
    assert "không áp dụng" not in p


def test_eval_prompt_default_unchanged():
    """Không truyền gì -> prompt BẰNG HỆT trước đây (backward-compat)."""
    assert eval_prompt(_ND, "text") == eval_prompt(_ND, "text", vendor_ctx=None, profile=None)
    assert "[NHÀ THẦU]" not in eval_prompt(_ND, "text")


def test_sys_eval_teaches_na_rule_without_tag_collision():
    """SYS_EVAL dạy quy tắc N/A nhưng KHÔNG chứa tag [NHÀ THẦU] — chống assert phủ định fail giả."""
    assert "không áp dụng" in SYS_EVAL and "liên danh" in SYS_EVAL
    assert "ghi_chu" in SYS_EVAL                 # bắt buộc nêu căn cứ
    assert "[NHÀ THẦU]" not in SYS_EVAL
