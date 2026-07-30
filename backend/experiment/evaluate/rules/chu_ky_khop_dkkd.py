"""Luật: người ký đơn dự thầu KHỚP người đại diện pháp luật trong ĐKKD (dang_ky_kinh_doanh).

STANDING CHECK (pham_vi="goi"): chạy 1 lần/nhà thầu bất kể HSMT có nêu hay không — HSMT thường
chỉ ghi "đại diện hợp pháp ký" mà không nhắc ĐKKD, nếu chờ HSMT yêu cầu thì MẤT hẳn kiểm tra này.
Đổi lại, verdict KHÔNG gắn vào tiêu chí nào (gắn bừa vào tiêu chí đầu tiên có đơn dự thầu là quy
kết sai + phụ thuộc thứ tự), KHÔNG vào roll-up, KHÔNG tự kéo 'loại' — nó ra
`EvalResult.phat_hien_bo_sung` và hiện ở mục riêng "ngoài checklist HSMT" để chuyên gia tự quyết.

Text-only (chữ ký/dấu đã được ingest mô tả trong text). Quy ước: `trang` theo đơn dự thầu; trang
ĐKKD ghi trong bang_chung. Thiếu ĐƠN DỰ THẦU -> 'thiếu hồ sơ' (không gọi LLM).

KÝ THAY (rẽ nhánh ở CODE — không bắt LLM tự làm if/else):
- ĐỦ đơn + ĐKKD: bước 1 đối chiếu người ký ↔ đại diện PL; chỉ khi 'không đạt' mới xét giấy ủy
  quyền (giay_uy_quyen, file riêng trong HSDT). Không có GUQ -> 'không đạt' (ký thay không ủy
  quyền), KHÔNG gọi LLM lần 2. Có GUQ -> call 2 thẩm định 3 ý: người ủy quyền = đại diện PL;
  người được ủy quyền = người ký đơn; phạm vi ủy quyền bao gồm ký đơn dự thầu.
- KHÔNG có ĐKKD (hay gặp trong thực tế): còn GUQ thì vẫn kiểm được phần lớn giá trị — MỘT call
  thẩm định 2 ý (người được ủy quyền = người ký đơn; phạm vi gồm ký đơn dự thầu), ghi_chu nêu rõ
  chưa đối chiếu được đại diện pháp luật. Không có cả GUQ -> 'thiếu hồ sơ' (không gọi LLM).

Bằng chứng ủy quyền LUÔN mở đầu bằng "ai ủy quyền cho ai" — chuyên gia cần thấy ngay cặp tên này
để rà lại, không phải đọc lần trong đoạn trích.

PHÁP NHÂN (kiểm TRƯỚC tên người): ĐKKD và giấy ủy quyền phải là của CHÍNH pháp nhân đứng tên ký
đơn dự thầu. Ca thật (samples/62/HSDT/osb): giấy ủy quyền do 'Công ty TNHH Công nghệ cao OSB' cấp
trong khi đơn dự thầu đứng tên 'Công ty cổ phần Tập đoàn OSB' — trùng thương hiệu nên rất dễ lọt,
mà ủy quyền từ pháp nhân khác thì VÔ HIỆU dù đúng người và đúng phạm vi. Sai pháp nhân thì việc so
tên người cũng vô nghĩa (khớp với đại diện của công ty khác), nên chặn ngay, không xét tiếp.
`khop_phap_nhan` guard MỘT CHIỀU: LLM nói 'khác' mà hai tên chuẩn hóa giống hệt -> tin code, tránh
báo động giả do hoa/thường/dấu; chiều ngược lại để LLM phán vì viết tắt vẫn là cùng pháp nhân.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.prompts import cot_block

from experiment.evaluate.route import _norm, pages_text
from experiment.evaluate.rules.registry import PHAM_VI_GOI, RuleSkill
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    PageRecord, VendorContext, Verdict, _Base,
)

_TEN = "Người ký đơn dự thầu khớp đại diện pháp luật (ĐKKD)"
_DON = "don_du_thau"          # BẮT BUỘC — không có đơn thì không có chữ ký để đối chiếu
_DKKD = "dang_ky_kinh_doanh"
_HO_SO = [_DON, _DKKD]
_GUQ = "giay_uy_quyen"        # hồ sơ TÙY CHỌN — xét khi ký thay hoặc khi HSDT thiếu ĐKKD
_TTLD = "thoa_thuan_lien_danh"   # hồ sơ TÙY CHỌN — có thì nhà thầu là LIÊN DANH, đổi hẳn cách kiểm
_TEN_LD = "Người ký đơn dự thầu đúng đại diện liên danh (thỏa thuận liên danh)"
_DOC_CAP = 3000       # trần text MỖI tài liệu trong prompt
_MAX_TOKENS = 4096

_QUY_TAC_PHAP_NHAN = (
    "QUY TẮC PHÁP NHÂN (rất dễ sai, đọc kỹ): hai tên chỉ CÙNG pháp nhân khi trùng cả LOẠI HÌNH và "
    "TÊN RIÊNG. Khác loại hình (TNHH ≠ cổ phần) hoặc khác tên riêng (Công nghệ cao ≠ Tập đoàn) là "
    "HAI PHÁP NHÂN KHÁC NHAU, kể cả khi trùng thương hiệu — ví dụ 'Công ty TNHH Công nghệ cao OSB' "
    "KHÁC 'Công ty cổ phần Tập đoàn OSB'. Viết tắt cùng một tên thì vẫn là một ('Cty CP Tập đoàn "
    "OSB' = 'Công ty cổ phần Tập đoàn OSB'). "
)

SYS_RULE_CHU_KY = (
    "Bạn là chuyên gia chấm thầu. Đối chiếu NGƯỜI KÝ trong ĐƠN DỰ THẦU với NGƯỜI ĐẠI DIỆN THEO "
    "PHÁP LUẬT trong GIẤY ĐĂNG KÝ KINH DOANH (ĐKKD). ket_qua: 'đạt' nếu cùng một người (hoặc ký theo "
    "ủy quyền hợp lệ nêu rõ trong hồ sơ); 'không đạt' nếu khác người và không có ủy quyền; "
    "'cần làm rõ' nếu KHÔNG tìm thấy tên một trong hai phía — TUYỆT ĐỐI KHÔNG bịa tên. "
    "bang_chung: trích cả hai phía kèm số trang từng tài liệu.\n"
    "NGOÀI RA bóc thêm: nha_thau_don = tên PHÁP NHÂN đứng tên ký đơn dự thầu (nhà thầu liên danh "
    "thì lấy thành viên đứng tên ký thay mặt liên danh); doanh_nghiep_dkkd = tên doanh nghiệp ghi "
    "trong ĐKKD (nếu có nhiều ĐKKD thì lấy cái của bên ký đơn; không có cái nào của bên đó thì lấy "
    "tên trên ĐKKD đầu tiên); phap_nhan_khop = hai tên đó có cùng một pháp nhân không. "
    + _QUY_TAC_PHAP_NHAN +
    "Không đọc được tên nào thì để chuỗi rỗng, KHÔNG bịa. Chỉ trả JSON."
)


SYS_RULE_UY_QUYEN = (
    "Bạn là chuyên gia chấm thầu. Người ký ĐƠN DỰ THẦU KHÔNG phải đại diện pháp luật — hãy thẩm "
    "định GIẤY ỦY QUYỀN theo ĐỦ 3 điều kiện: (1) người ủy quyền là ĐẠI DIỆN PHÁP LUẬT nêu dưới "
    "đây; (2) người được ủy quyền ĐÚNG là người đã ký đơn dự thầu; (3) nội dung/phạm vi ủy quyền "
    "bao gồm việc KÝ ĐƠN DỰ THẦU; (4) BÊN ỦY QUYỀN là CHÍNH pháp nhân đứng tên ký đơn dự thầu nêu "
    "ở đầu prompt. ket_qua: 'đạt' khi thỏa CẢ BỐN; 'không đạt' khi vi phạm bất kỳ điều nào; "
    "'cần làm rõ' khi thiếu thông tin — TUYỆT ĐỐI KHÔNG bịa tên hay phạm vi. "
    "BẮT BUỘC điền nguoi_uy_quyen và nguoi_duoc_uy_quyen (ai ủy quyền cho ai) để chuyên gia rà "
    "lại, cùng phap_nhan_uy_quyen (tên pháp nhân BÊN ỦY QUYỀN) và phap_nhan_khop. "
    + _QUY_TAC_PHAP_NHAN +
    "bang_chung: trích nguyên văn giấy ủy quyền kèm số trang. Chỉ trả JSON."
)


SYS_RULE_UY_QUYEN_KHONG_DKKD = (
    "Bạn là chuyên gia chấm thầu. HSDT KHÔNG có giấy đăng ký kinh doanh (ĐKKD) nên KHÔNG đối chiếu "
    "được đại diện pháp luật — chỉ thẩm định GIẤY ỦY QUYỀN theo 2 điều kiện: (1) người được ủy "
    "quyền ĐÚNG là người đã ký ĐƠN DỰ THẦU dưới đây; (2) nội dung/phạm vi ủy quyền bao gồm việc "
    "KÝ ĐƠN DỰ THẦU; (3) BÊN ỦY QUYỀN là CHÍNH pháp nhân đứng tên ký đơn dự thầu. ket_qua: 'đạt' "
    "khi thỏa CẢ BA; 'không đạt' khi vi phạm một trong ba; 'cần làm rõ' khi không đọc được người "
    "ký đơn, người được ủy quyền hoặc phạm vi ủy quyền — TUYỆT ĐỐI KHÔNG bịa tên hay phạm vi, và "
    "KHÔNG suy đoán ai là đại diện pháp luật. BẮT BUỘC điền nguoi_uy_quyen và nguoi_duoc_uy_quyen "
    "(ai ủy quyền cho ai), nha_thau_don (pháp nhân đứng tên ký đơn), phap_nhan_uy_quyen (pháp "
    "nhân BÊN ỦY QUYỀN) và phap_nhan_khop. "
    + _QUY_TAC_PHAP_NHAN +
    "bang_chung: trích nguyên văn giấy ủy quyền + câu ký trong đơn, kèm số trang. Chỉ trả JSON."
)


class ChuKyOut(_Base):
    ket_qua: str = KET_QUA_SOI
    nguoi_ky: str = ""
    dai_dien_phap_luat: str = ""
    nha_thau_don: str = ""          # pháp nhân đứng tên ký ĐƠN DỰ THẦU
    doanh_nghiep_dkkd: str = ""     # pháp nhân trong ĐKKD
    phap_nhan_khop: bool = False
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


class UyQuyenOut(_Base):
    ket_qua: str = KET_QUA_SOI
    nguoi_uy_quyen: str = ""
    nguoi_duoc_uy_quyen: str = ""
    nha_thau_don: str = ""          # nhánh thiếu ĐKKD: LLM tự đọc từ đơn
    phap_nhan_uy_quyen: str = ""    # pháp nhân BÊN ỦY QUYỀN trong giấy ủy quyền
    phap_nhan_khop: bool = False
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


class ThanhVienLienDanh(_Base):
    ten_phap_nhan: str = ""
    nguoi_dai_dien: str = ""      # đại diện của CHÍNH thành viên đó, ghi trong thỏa thuận liên danh
    la_dung_dau: bool = False


class KhoiChuKy(_Base):
    phap_nhan: str = ""           # pháp nhân đứng tên khối chữ ký trên đơn
    nguoi_ky: str = ""
    thanh_vien_ttld: str = ""     # LLM gán khối này về thành viên nào trong TTLD; '' = không thuộc ai


class LienDanhKyOut(_Base):
    thanh_vien: list[ThanhVienLienDanh] = []
    chu_ky: list[KhoiChuKy] = []
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


class MucUyQuyenLienDanh(_Base):
    phap_nhan: str = ""           # thành viên liên danh của khối chữ ký đang xét
    nguoi_uy_quyen: str = ""
    nguoi_duoc_uy_quyen: str = ""
    phap_nhan_uy_quyen: str = ""  # BÊN ỦY QUYỀN ghi trong giấy ủy quyền
    phap_nhan_khop: bool = False
    dung_nguoi: bool = False      # người được ủy quyền = người đã ký đơn?
    dung_pham_vi: bool = False    # phạm vi ủy quyền gồm việc ký đơn dự thầu?
    ghi_chu: str = ""


class UyQuyenLienDanhOut(_Base):
    muc: list[MucUyQuyenLienDanh] = []
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


@dataclass(frozen=True)
class ChuKyLech:
    """Khối chữ ký mà người ký KHÁC đại diện của thành viên đó theo TTLD -> phải xét ủy quyền."""
    phap_nhan: str        # tên thành viên liên danh (theo TTLD)
    nguoi_ky: str         # người đã ký trên đơn
    nguoi_dai_dien: str   # đại diện của thành viên đó theo TTLD


def validate_lien_danh_ky(d: dict[str, Any]) -> dict[str, Any]:
    return LienDanhKyOut(**d).model_dump()


def validate_uy_quyen_lien_danh(d: dict[str, Any]) -> dict[str, Any]:
    return UyQuyenLienDanhOut(**d).model_dump()


def validate_chu_ky(d: dict[str, Any]) -> dict[str, Any]:
    return ChuKyOut(**d).model_dump()


def validate_uy_quyen(d: dict[str, Any]) -> dict[str, Any]:
    return UyQuyenOut(**d).model_dump()


def chu_ky_prompt(don_text: str, dkkd_text: str) -> str:
    return (
        "[RULE:chu_ky_khop_dkkd]\n"
        f"ĐƠN DỰ THẦU (bóc từ ảnh):\n{don_text}\n\n"
        f"GIẤY ĐĂNG KÝ KINH DOANH (ĐKKD, bóc từ ảnh):\n{dkkd_text}\n\n"
        + cot_block('{"ket_qua":"đạt|không đạt|cần làm rõ","nguoi_ky":"...","dai_dien_phap_luat":"...",'
                    '"nha_thau_don":"<pháp nhân ký đơn>","doanh_nghiep_dkkd":"<pháp nhân ĐKKD>",'
                    '"phap_nhan_khop":true,"bang_chung":"<trích 2 phía>","trang":[...],'
                    '"do_tin":0.0,"ghi_chu":""}')
    )


_SCHEMA_UY_QUYEN = ('{"ket_qua":"đạt|không đạt|cần làm rõ","nguoi_uy_quyen":"...",'
                    '"nguoi_duoc_uy_quyen":"...","nha_thau_don":"<pháp nhân ký đơn>",'
                    '"phap_nhan_uy_quyen":"<pháp nhân bên ủy quyền>","phap_nhan_khop":true,'
                    '"bang_chung":"<trích GUQ>","trang":[...],"do_tin":0.0,"ghi_chu":""}')


def uy_quyen_prompt(guq_text: str, nguoi_ky: str, dai_dien: str, nha_thau_don: str = "") -> str:
    return (
        "[RULE:chu_ky_uy_quyen]\n"
        f"NHÀ THẦU ĐỨNG TÊN KÝ ĐƠN DỰ THẦU: {nha_thau_don or '(không rõ)'}\n"
        f"NGƯỜI KÝ ĐƠN DỰ THẦU: {nguoi_ky or '(không rõ)'}\n"
        f"ĐẠI DIỆN PHÁP LUẬT (theo ĐKKD): {dai_dien or '(không rõ)'}\n"
        f"GIẤY ỦY QUYỀN (bóc từ ảnh):\n{guq_text}\n\n"
        + cot_block(_SCHEMA_UY_QUYEN)
    )


def uy_quyen_khong_dkkd_prompt(don_text: str, guq_text: str) -> str:
    return (
        "[RULE:chu_ky_uy_quyen_khong_dkkd]\n"
        "LƯU Ý: HSDT KHÔNG có ĐKKD — chỉ xét người ký đơn ↔ người được ủy quyền và phạm vi.\n"
        f"ĐƠN DỰ THẦU (bóc từ ảnh):\n{don_text}\n\n"
        f"GIẤY ỦY QUYỀN (bóc từ ảnh):\n{guq_text}\n\n"
        + cot_block(_SCHEMA_UY_QUYEN)
    )


def khop_phap_nhan(ten_don: str, ten_kia: str, llm_noi_khop: bool) -> bool | None:
    """Hai tên có cùng MỘT pháp nhân? None = không đủ căn cứ (thiếu tên) -> KHÔNG suy đoán.

    Guard MỘT CHIỀU: LLM nói 'khác' mà hai tên chuẩn hóa giống hệt -> tin code (khớp), chống báo
    động giả do hoa/thường, dấu, khoảng trắng. Chiều ngược lại KHÔNG đụng: 'Cty CP Tập đoàn OSB'
    và 'Công ty cổ phần Tập đoàn OSB' là một pháp nhân dù chuỗi khác — chỉ LLM phán được.
    """
    a, b = _norm(ten_don).strip(), _norm(ten_kia).strip()
    if not a or not b:
        return None
    return True if a == b else llm_noi_khop


def _tra_thanh_vien(tvs: list[dict[str, Any]], ck: dict[str, Any]) -> dict[str, Any] | None:
    """Khối chữ ký -> thành viên trong TTLD. None = pháp nhân KHÔNG có trong thỏa thuận.

    Ưu tiên phần gán của LLM (`thanh_vien_ttld`), sau đó so tên chuẩn hoá — cùng tinh thần guard
    MỘT CHIỀU của `khop_phap_nhan`: LLM bỏ trống mà hai tên chuẩn hoá bằng nhau thì tin code.
    """
    for khoa in (ck.get("thanh_vien_ttld", ""), ck.get("phap_nhan", "")):
        k = _norm(str(khoa)).strip()
        if not k:
            continue
        for tv in tvs:
            if _norm(str(tv.get("ten_phap_nhan", ""))).strip() == k:
                return tv
    return None


def _dong_chu_ky(ck: dict[str, Any], tv: dict[str, Any] | None) -> str:
    return (f"{ck.get('phap_nhan') or '(không rõ pháp nhân)'} — ký bởi "
            f"{ck.get('nguoi_ky') or '(không rõ)'}; thỏa thuận liên danh ghi đại diện là "
            f"{(tv or {}).get('nguoi_dai_dien') or '(không rõ)'}")


def _khong_ro_ten_phap_nhan(ck: dict[str, Any]) -> bool:
    """Khối chữ ký không có LẤY MỘT tên pháp nhân nào để đối chiếu (bóc thiếu, không phải lạ).

    Khác hẳn ca 'pháp nhân lạ' (có tên, chỉ là tên đó không có trong TTLD): ở đây không có căn cứ
    nào để tra cứu, nên phải SOI — không được kết luận 'không đạt' bằng một cái tên rỗng.
    """
    return (not _norm(str(ck.get("thanh_vien_ttld", ""))).strip()
            and not _norm(str(ck.get("phap_nhan", ""))).strip())


def doi_chieu_chu_ky_lien_danh(
        d: dict[str, Any]) -> tuple[str, str, str, list[ChuKyLech]]:
    """Dữ liệu đã bóc -> (ket_qua, bang_chung, ghi_chu, lech). Hàm THUẦN: mọi phán quyết ở đây.

    ket_qua = '' nghĩa là CHƯA kết luận được: có khối chữ ký lệch người, phải xét giấy ủy quyền
    cho danh sách `lech`. Hai hình thức ký hợp lệ của nhà thầu liên danh: thành viên đứng đầu ký
    thay mặt liên danh, HOẶC tất cả thành viên cùng ký.
    """
    tvs = [tv for tv in (d.get("thanh_vien") or [])
           if str(tv.get("ten_phap_nhan", "")).strip()]
    cks = list(d.get("chu_ky") or [])
    if not tvs:
        return KET_QUA_SOI, "", "không bóc được thành viên nào trong thỏa thuận liên danh", []
    if not cks:
        return KET_QUA_SOI, "", "không bóc được khối chữ ký nào trên đơn dự thầu", []

    cap = [(ck, _tra_thanh_vien(tvs, ck)) for ck in cks]
    bang_chung = "; ".join(_dong_chu_ky(ck, tv) for ck, tv in cap)

    # THIẾU CĂN CỨ (không đọc được tên pháp nhân nào trên khối) phải kiểm TRƯỚC ca 'pháp nhân lạ':
    # mọi phán quyết phía sau (hình thức A/B, thiếu chữ ký) dựa trên biết ĐỦ tập pháp nhân đã ký —
    # thiếu một tên là cả kết luận không còn đáng tin, kể cả khi một khối khác đúng là người lạ.
    mo_ho = [ck for ck, tv in cap if tv is None and _khong_ro_ten_phap_nhan(ck)]
    if mo_ho:
        return (KET_QUA_SOI, bang_chung,
                "không đọc được tên pháp nhân trên một hoặc nhiều khối chữ ký của đơn dự thầu — "
                "chưa đối chiếu được với thỏa thuận liên danh", [])

    la = [str(ck.get("phap_nhan") or "(không rõ)") for ck, tv in cap if tv is None]
    if la:
        return (KET_QUA_KHONG, bang_chung,
                f"đơn dự thầu có chữ ký đứng tên pháp nhân KHÔNG có trong thỏa thuận liên danh: "
                f"{', '.join(la)}", [])

    ten_ky = {_norm(str(tv.get("ten_phap_nhan", ""))) for _, tv in cap}
    ten_tv = {_norm(str(tv.get("ten_phap_nhan", ""))) for tv in tvs}
    dd_list = [tv for tv in tvs if tv.get("la_dung_dau")]

    if ten_ky == ten_tv:
        hinh_thuc = "tất cả thành viên liên danh cùng ký"
    elif len(dd_list) > 1:
        # Bóc dữ liệu lỗi (TTLD không thể có 2 thành viên đứng đầu) — không đoán bừa lấy người nào.
        return (KET_QUA_SOI, bang_chung,
                "thỏa thuận liên danh (theo dữ liệu bóc được) nêu NHIỀU HƠN MỘT thành viên đứng "
                "đầu — chưa đối chiếu được thẩm quyền ký đơn", [])
    elif not dd_list:
        return (KET_QUA_SOI, bang_chung,
                "thỏa thuận liên danh không nêu rõ thành viên đứng đầu — chưa đối chiếu được thẩm "
                "quyền ký đơn", [])
    elif ten_ky == {_norm(str(dd_list[0].get("ten_phap_nhan", "")))}:
        hinh_thuc = f"thành viên đứng đầu ({dd_list[0].get('ten_phap_nhan')}) ký thay mặt liên danh"
    else:
        dd = dd_list[0]
        thieu = [str(tv.get("ten_phap_nhan", "")) for tv in tvs
                 if _norm(str(tv.get("ten_phap_nhan", ""))) not in ten_ky]
        return (KET_QUA_KHONG, bang_chung,
                f"đơn dự thầu không do thành viên đứng đầu ({dd.get('ten_phap_nhan')}) ký thay mặt "
                f"liên danh, mà cũng không đủ chữ ký của mọi thành viên — thiếu chữ ký của: "
                f"{', '.join(thieu)}", [])

    if any(not str(ck.get("nguoi_ky", "")).strip()
           or not str((tv or {}).get("nguoi_dai_dien", "")).strip() for ck, tv in cap):
        return (KET_QUA_SOI, bang_chung,
                "không đọc được tên người ký trên đơn và/hoặc tên đại diện trong thỏa thuận liên "
                "danh — chưa đối chiếu được", [])

    lech = [ChuKyLech(phap_nhan=str(tv.get("ten_phap_nhan", "")),
                      nguoi_ky=str(ck.get("nguoi_ky", "")),
                      nguoi_dai_dien=str(tv.get("nguoi_dai_dien", "")))
            for ck, tv in cap
            if _norm(str(ck.get("nguoi_ky", ""))) != _norm(str(tv.get("nguoi_dai_dien", "")))]
    if lech:
        return "", bang_chung, "", lech
    return KET_QUA_DAT, bang_chung, f"đơn dự thầu hợp lệ theo hình thức: {hinh_thuc}", []


def ket_luan_uy_quyen_lien_danh(lech: list[ChuKyLech],
                                muc: list[dict[str, Any]]) -> tuple[str, str]:
    """(chữ ký lệch, mục ủy quyền đã bóc) -> (ket_qua, ghi_chu). Hàm THUẦN.

    MỖI khối chữ ký lệch phải có một mục ủy quyền thỏa CẢ BA: bên ủy quyền đúng là thành viên
    liên danh mà khối chữ ký đó đứng tên; người được ủy quyền đúng là người ký đơn; phạm vi bao
    gồm việc ký đơn dự thầu. Ủy quyền từ thành viên KHÁC là vô hiệu dù đúng người, đúng phạm vi.
    """
    theo_ten = {_norm(str(m.get("phap_nhan", ""))): m for m in muc}
    loi: list[str] = []
    soi: list[str] = []
    for ck_lech in lech:
        m = theo_ten.get(_norm(ck_lech.phap_nhan))
        if m is None:
            loi.append(f"{ck_lech.phap_nhan}: không có giấy ủy quyền cho người ký "
                       f"{ck_lech.nguoi_ky}")
            continue
        khop = khop_phap_nhan(ck_lech.phap_nhan, str(m.get("phap_nhan_uy_quyen", "")),
                              bool(m.get("phap_nhan_khop")))
        if khop is None:
            soi.append(f"{ck_lech.phap_nhan}: không đọc được tên pháp nhân bên ủy quyền")
            continue
        if not khop:
            loi.append(f"{ck_lech.phap_nhan}: giấy ủy quyền do pháp nhân KHÁC cấp "
                       f"({m.get('phap_nhan_uy_quyen') or '?'}), không phải thành viên liên danh "
                       f"đứng tên khối chữ ký này — ủy quyền vô hiệu")
            continue
        if not m.get("dung_nguoi"):
            loi.append(f"{ck_lech.phap_nhan}: người được ủy quyền "
                       f"({m.get('nguoi_duoc_uy_quyen') or '?'}) không phải người ký đơn "
                       f"({ck_lech.nguoi_ky})")
            continue
        if not m.get("dung_pham_vi"):
            loi.append(f"{ck_lech.phap_nhan}: phạm vi ủy quyền không bao gồm việc ký đơn dự thầu")
    if loi:
        return KET_QUA_KHONG, "; ".join(loi)
    if soi:
        return KET_QUA_SOI, "; ".join(soi)
    return KET_QUA_DAT, ""


def _bang_chung_phap_nhan(nhan_kia: str, ten_don: str, ten_kia: str) -> str:
    return f"đơn dự thầu: {ten_don}; {nhan_kia}: {ten_kia} — KHÁC pháp nhân"


def _bang_chung_uy_quyen(d: dict[str, Any]) -> str:
    """Mở đầu bằng 'ai ủy quyền cho ai' rồi mới tới trích dẫn — chuyên gia đọc cặp tên ngay."""
    ai = (f"{d.get('nguoi_uy_quyen') or '?'} ủy quyền cho "
          f"{d.get('nguoi_duoc_uy_quyen') or '?'}")
    bc = d.get("bang_chung", "")
    return f"{ai}; {bc}" if bc else ai


def _ket_qua_hop_le(raw: str) -> str:
    return raw if raw in {KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI} else KET_QUA_SOI


def _verdict(ket_qua: str, bang_chung: str = "", trang: list[int] | None = None,
             do_tin: float = 0.0, ghi_chu: str = "",
             nguon_doc: list[str] | None = None) -> Verdict:
    return Verdict(noi_dung_kiem_tra=_TEN, hsdt_kiem_tra=_DON,
                   yeu_cau="Người ký đơn dự thầu phải là đại diện pháp luật hoặc người được ủy quyền hợp lệ",
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung=bang_chung,
                   trang=trang or [], do_tin=do_tin, ghi_chu=ghi_chu,
                   nguon_doc=nguon_doc or list(_HO_SO))


async def handler(by_type: dict[str, list[PageRecord]], vendor_ctx: VendorContext | None,
                  criterion: dict[str, Any], vision_fn: Any,
                  *, nd: dict[str, Any] | None = None, pkg: Any = None) -> Verdict:
    # standing check: không phục vụ nội dung nào -> bỏ qua nd; không cần ngữ cảnh gói -> bỏ qua pkg.
    if not by_type.get(_DON):
        return _verdict(KET_QUA_THIEU, bang_chung=f"HSDT không có: {_DON}",
                        ghi_chu="thiếu hồ sơ để đối chiếu chữ ký")
    if not by_type.get(_DKKD):
        # Không có ĐKKD: còn giấy ủy quyền thì vẫn kiểm được người ký + phạm vi ủy quyền.
        if not by_type.get(_GUQ):
            return _verdict(KET_QUA_THIEU, bang_chung=f"HSDT không có: {_DKKD}",
                            ghi_chu="thiếu hồ sơ để đối chiếu chữ ký")
        return await _xet_uy_quyen_khong_dkkd(by_type, vision_fn)
    out = await vision_fn(SYS_RULE_CHU_KY,
                          chu_ky_prompt(pages_text(by_type[_DON]),
                                        pages_text(by_type[_DKKD])),
                          validate=validate_chu_ky, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi: {out.error}", ghi_chu="cần soi lại")
    d = out.data
    ket_qua = _ket_qua_hop_le(d.get("ket_qua", KET_QUA_SOI))
    bang_chung = d.get("bang_chung", "") or \
        f"người ký: {d.get('nguoi_ky', '?')}; đại diện pháp luật: {d.get('dai_dien_phap_luat', '?')}"
    trang = [int(t) for t in d.get("trang", []) if str(t).isdigit()]

    # PHÁP NHÂN trước TÊN NGƯỜI: ĐKKD của pháp nhân khác thì so tên người là vô nghĩa (khớp với
    # đại diện của công ty khác). Fail sớm, không xét tiếp ủy quyền.
    ten_don, ten_dkkd = d.get("nha_thau_don", ""), d.get("doanh_nghiep_dkkd", "")
    khop = khop_phap_nhan(ten_don, ten_dkkd, bool(d.get("phap_nhan_khop")))
    if khop is None:
        return _verdict(KET_QUA_SOI, bang_chung=bang_chung, trang=trang,
                        ghi_chu="không đọc được tên pháp nhân trên đơn dự thầu và/hoặc ĐKKD — "
                                "chưa đối chiếu được ĐKKD có đúng của nhà thầu ký đơn hay không")
    if not khop:
        return _verdict(KET_QUA_KHONG, trang=trang,
                        bang_chung=_bang_chung_phap_nhan("ĐKKD", ten_don, ten_dkkd),
                        ghi_chu="ĐKKD không phải của pháp nhân đứng tên ký đơn dự thầu")

    if ket_qua == KET_QUA_KHONG:      # người ký ≠ đại diện PL -> xét ký thay theo ủy quyền
        return await _xet_uy_quyen(by_type, vision_fn, d, bang_chung, trang)
    return _verdict(ket_qua, bang_chung=bang_chung, trang=trang,
                    do_tin=float(d.get("do_tin", 0.0) or 0.0), ghi_chu=d.get("ghi_chu", ""))


async def _xet_uy_quyen(by_type: dict[str, list[PageRecord]], vision_fn: Any,
                        d1: dict[str, Any], bang_chung_1: str, trang_1: list[int]) -> Verdict:
    """Bước 2 (chỉ khi ký thay): thẩm định giấy ủy quyền — đúng người + đúng phạm vi ký đơn."""
    if not by_type.get(_GUQ):
        return _verdict(KET_QUA_KHONG, bang_chung=bang_chung_1, trang=trang_1,
                        do_tin=float(d1.get("do_tin", 0.0) or 0.0),
                        ghi_chu="người ký khác đại diện pháp luật và HSDT không có giấy ủy quyền")
    ten_don = d1.get("nha_thau_don", "")
    out = await vision_fn(SYS_RULE_UY_QUYEN,
                          uy_quyen_prompt(pages_text(by_type[_GUQ]), d1.get("nguoi_ky", ""),
                                          d1.get("dai_dien_phap_luat", ""), ten_don),
                          validate=validate_uy_quyen, max_tokens=_MAX_TOKENS)
    nguon = _HO_SO + [_GUQ]
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi (thẩm định ủy quyền): {out.error}",
                        ghi_chu="cần soi lại", nguon_doc=nguon)
    d2 = out.data
    bang_chung = f"{bang_chung_1}; ủy quyền: {_bang_chung_uy_quyen(d2)}"
    lech = _kiem_phap_nhan_guq(d2, ten_don, bang_chung, trang_1, nguon)
    if lech is not None:
        return lech
    return _verdict(_ket_qua_hop_le(d2.get("ket_qua", KET_QUA_SOI)), bang_chung=bang_chung,
                    trang=trang_1, do_tin=float(d2.get("do_tin", 0.0) or 0.0),
                    ghi_chu=d2.get("ghi_chu", ""), nguon_doc=nguon)


def _kiem_phap_nhan_guq(d: dict[str, Any], ten_don: str, bang_chung: str, trang: list[int],
                        nguon: list[str]) -> Verdict | None:
    """Bên ỦY QUYỀN phải là chính pháp nhân ký đơn. None = khớp (hoặc chưa đủ căn cứ) -> đi tiếp.

    Ủy quyền từ pháp nhân khác là VÔ HIỆU dù đúng người và đúng phạm vi — nên chặn ở đây, không
    để verdict 'đạt' lọt qua chỉ vì ba điều kiện kia thỏa.
    """
    ten_guq = d.get("phap_nhan_uy_quyen", "")
    khop = khop_phap_nhan(ten_don or d.get("nha_thau_don", ""), ten_guq,
                          bool(d.get("phap_nhan_khop")))
    if khop is None:
        return _verdict(KET_QUA_SOI, bang_chung=bang_chung, trang=trang, nguon_doc=nguon,
                        ghi_chu="không đọc được tên pháp nhân trên đơn dự thầu và/hoặc giấy ủy "
                                "quyền — chưa đối chiếu được ủy quyền có đúng của nhà thầu không")
    if not khop:
        return _verdict(KET_QUA_KHONG, trang=trang, nguon_doc=nguon,
                        bang_chung=_bang_chung_phap_nhan(
                            "giấy ủy quyền", ten_don or d.get("nha_thau_don", ""), ten_guq),
                        ghi_chu="giấy ủy quyền do pháp nhân KHÁC cấp, không phải nhà thầu đứng tên "
                                "ký đơn dự thầu — ủy quyền vô hiệu")
    return None


async def _xet_uy_quyen_khong_dkkd(by_type: dict[str, list[PageRecord]],
                                   vision_fn: Any) -> Verdict:
    """HSDT thiếu ĐKKD: thẩm định GUQ độc lập — người ký đơn = người được ủy quyền + đúng phạm vi.

    KHÔNG kết luận về đại diện pháp luật (không có căn cứ) — ghi_chu nêu rõ để chuyên gia biết
    verdict này hẹp hơn kiểm tra đầy đủ.
    """
    nguon = [_DON, _GUQ]
    out = await vision_fn(SYS_RULE_UY_QUYEN_KHONG_DKKD,
                          uy_quyen_khong_dkkd_prompt(pages_text(by_type[_DON]),
                                                     pages_text(by_type[_GUQ])),
                          validate=validate_uy_quyen, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi (thẩm định ủy quyền): {out.error}",
                        ghi_chu="cần soi lại", nguon_doc=nguon)
    d = out.data
    lech = _kiem_phap_nhan_guq(d, d.get("nha_thau_don", ""), _bang_chung_uy_quyen(d),
                               [int(t) for t in d.get("trang", []) if str(t).isdigit()], nguon)
    if lech is not None:
        return lech
    thieu_dkkd = ("HSDT không có ĐKKD — chỉ thẩm định giấy ủy quyền (người ký đơn + phạm vi), "
                  "CHƯA đối chiếu được đại diện pháp luật")
    ghi_chu = d.get("ghi_chu", "")
    return _verdict(_ket_qua_hop_le(d.get("ket_qua", KET_QUA_SOI)),
                    bang_chung=_bang_chung_uy_quyen(d),
                    trang=[int(t) for t in d.get("trang", []) if str(t).isdigit()],
                    do_tin=float(d.get("do_tin", 0.0) or 0.0),
                    ghi_chu=f"{thieu_dkkd}; {ghi_chu}" if ghi_chu else thieu_dkkd,
                    nguon_doc=nguon)


SKILL = RuleSkill(id="chu_ky_khop_dkkd", ten=_TEN, ho_so_can=list(_HO_SO), can_vendor=False,
                  handler=handler, pham_vi=PHAM_VI_GOI)
