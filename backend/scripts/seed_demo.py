"""Seed dữ liệu DEMO để chạy thử giao diện khi KHÔNG có LiteLLM proxy.

Chạy:  cd backend && python3 scripts/seed_demo.py [--reset] [--with-error]

Vì không có proxy, hai bước cần AI (bóc tiêu chí, chấm HSDT) không chạy được. Script ghi thẳng
vào DB kết quả tương đương để xem được toàn bộ giao diện: gói thầu -> tài liệu -> tiêu chí ->
kết quả -> báo cáo.

QUAN TRỌNG — đây KHÔNG phải output của AI. Mọi verdict dưới đây do script này viết tay để dựng
giao diện; tên gói thầu và ghi chú đều gắn nhãn DEMO để không ai nhầm là kết quả chấm thật.

--reset      xóa gói DEMO cũ rồi tạo lại (mặc định: có sẵn thì giữ nguyên, không làm gì)
--with-error thêm 1 verdict "lỗi" để xem trạng thái CHẶN xuất báo cáo (mặc định: không)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz  # PyMuPDF

import models
import storage
from database import SessionLocal, init_db
from experiment.evaluate.schema import (
    HINH_THUC_DOC_LAP, HINH_THUC_LIEN_DANH,
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_KHONG_AP_DUNG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
)

MA_SO = "DEMO-2026-001"

# Mã áp dụng của rubric là mã kỹ thuật ('lien_danh'), KHÁC hằng hình thức nhà thầu ('liên danh').
# Backend canon_hinh_thuc() nhận cả hai, nhưng Select trên giao diện khớp theo mã kỹ thuật.
AP_DUNG_LIEN_DANH = "lien_danh"


def _pdf(lines: list[str]) -> bytes:
    """PDF text 1 trang — đủ để giao diện có file thật để hiện/tải."""
    doc = fitz.open()
    page = doc.new_page()
    html = "".join(f"<p>{ln}</p>" for ln in lines)
    page.insert_htmlbox(fitz.Rect(50, 50, 545, 780), html)
    return doc.tobytes()


def _doc(db, pkg_id: int, loai: str, name: str, subdir: str, lines: list[str],
         vendor_id: int | None = None, artifact_type: str | None = None,
         file_kind: str = "pdf_text", trang_thai_ocr: str = "hoan_thanh",
         validation: dict | None = None) -> models.TenderDocument:
    rel = storage.save_upload(pkg_id, name, _pdf(lines), subdir)
    d = models.TenderDocument(
        package_id=pkg_id, loai=loai, vendor_id=vendor_id, file_path=rel,
        file_kind=file_kind, trang_thai_ocr=trang_thai_ocr, extracted_text="[]",
        artifact_type=artifact_type, artifact_validation=validation or {})
    db.add(d)
    return d


def _crit(db, pkg_id: int, thu_tu: int, ten: str, yeu_cau_goc: str, ho_so: list[str], noi_dung: list[dict], loi_ai: str = "") -> models.RubricCriterion:
    c = models.RubricCriterion(
        package_id=pkg_id, thu_tu=thu_tu, nhom="hop_le", ten=ten, yeu_cau_goc=yeu_cau_goc,
        hsdt_can_kiem_tra=ho_so, loi_ai=loi_ai)
    db.add(c)
    db.flush()
    for i, n in enumerate(noi_dung):
        db.add(models.RubricNoiDung(
            criterion_id=c.id, thu_tu=i, noi_dung_kiem_tra=n["ten"],
            hsdt_kiem_tra=n.get("ho_so", ""), yeu_cau=n.get("yeu_cau", ""),
            can_lam_ro=n.get("can_lam_ro", ""), can_tra_cuu=False,
            thong_tin_bo_sung=n.get("chuan", ""), nguon=n.get("nguon", ""),
            can_review=n.get("can_review", False), ap_dung=n.get("ap_dung", "")))
    return c


def _eval(db, pkg_id: int, vendor_id: int, thu_tu: int, ten: str, yeu_cau_goc: str, verdicts: list[dict], nhom: str = "hop_le") -> None:
    """1 tiêu chí đã chấm + các verdict con; ket_qua tiêu chí roll-up từ verdict.

    PHẢI khớp luật ở `routers.evaluation._rollup` / `experiment.evaluate.evaluate.evaluate_criterion`
    (xem docstring `_rollup`) — đây là bản THỨ BA của cùng luật, script viết tay chứ không gọi lại
    hai bản kia (không import được routers ở đây khi chạy độc lập ngoài app).
    """
    kqs = {v["ket_qua"] for v in verdicts}
    xet = kqs - {KET_QUA_KHONG_AP_DUNG}
    if KET_QUA_KHONG in xet:
        ket_qua = KET_QUA_KHONG
    elif xet & {KET_QUA_SOI, KET_QUA_LOI}:
        ket_qua = KET_QUA_SOI
    elif KET_QUA_THIEU in xet:
        ket_qua = KET_QUA_THIEU
    elif xet == {KET_QUA_DAT}:
        ket_qua = KET_QUA_DAT
    else:
        ket_qua = KET_QUA_KHONG_AP_DUNG

    ev = models.HsdtCriterionEval(
        package_id=pkg_id, vendor_id=vendor_id, thu_tu=thu_tu, nhom=nhom, ten=ten,
        ket_qua=ket_qua, yeu_cau_goc=yeu_cau_goc)
    db.add(ev)
    db.flush()
    for i, v in enumerate(verdicts):
        db.add(models.HsdtVerdict(
            eval_id=ev.id, thu_tu=i, noi_dung_kiem_tra=v["ten"], hsdt_kiem_tra=v.get("ho_so", ""),
            yeu_cau=v.get("yeu_cau", ""), thong_tin_bo_sung=v.get("chuan", ""),
            ket_qua=v["ket_qua"], bang_chung=v.get("bang_chung", ""), trang=v.get("trang", []),
            do_tin=v.get("do_tin", 0.0), ghi_chu=v.get("ghi_chu", ""),
            nguon_hsmt=v.get("nguon", ""), nguon_doc=v.get("nguon_doc", [])))


def _profile(db, pkg_id: int, vendor_id: int, hinh_thuc: str, nguon: str, bang_chung: str,
             ho_so: list[dict], mau_thuan: bool = False, ghi_chu: str = "") -> None:
    db.add(models.HsdtVendorEval(
        package_id=pkg_id, vendor_id=vendor_id, hinh_thuc=hinh_thuc, nguon=nguon,
        bang_chung=bang_chung, trang=[1], do_tin=0.92, mau_thuan=mau_thuan, ghi_chu=ghi_chu,
        ho_so_nhan_duoc=ho_so))


def seed(reset: bool = False, with_error: bool = False) -> None:
    init_db()
    db = SessionLocal()

    old = db.query(models.ProcurementPackage).filter_by(ma_so=MA_SO).first()
    if old and not reset:
        print(f"Gói {MA_SO} đã tồn tại (id={old.id}). Dùng --reset để tạo lại.")
        db.close()
        return
    if old:
        db.delete(old)     # cascade: vendors, documents, rubric, evals
        db.commit()
        print(f"Đã xóa gói DEMO cũ (id={old.id}).")

    pkg = models.ProcurementPackage(
        ma_so=MA_SO, ten="[DEMO] Mua sắm thiết bị tin học năm 2026",
        loai="hang_hoa", gia_tri_uoc_tinh=4_800_000_000, trang_thai="cho_review",
        nguoi_phu_trach="Tổ chuyên gia số 1")
    db.add(pkg)
    db.flush()
    pid = pkg.id

    # ---- Nhà thầu: mỗi bên minh họa một trạng thái giao diện khác nhau ----
    v_ap = models.Vendor(package_id=pid, ten="Công ty CP Xây dựng An Phát",
                         ten_viet_tat="An Phát", hinh_thuc=HINH_THUC_DOC_LAP)
    v_ld = models.Vendor(package_id=pid, ten="Liên danh Trường Sơn - Đại Việt",
                         ten_viet_tat="TS-ĐV", hinh_thuc=HINH_THUC_LIEN_DANH)
    v_hb = models.Vendor(package_id=pid, ten="Công ty TNHH Thương mại Hòa Bình",
                         ten_viet_tat="Hòa Bình", hinh_thuc=HINH_THUC_DOC_LAP)
    v_mq = models.Vendor(package_id=pid, ten="Công ty CP Thiết bị Minh Quang",
                         ten_viet_tat="Minh Quang", hinh_thuc="")
    v_tt = models.Vendor(package_id=pid, ten="Công ty TNHH Tân Tiến",
                         ten_viet_tat="Tân Tiến", hinh_thuc="")
    db.add_all([v_ap, v_ld, v_hb, v_mq, v_tt])
    db.flush()

    # ---- Tài liệu gói thầu ----
    _doc(db, pid, "HSMT", "hsmt_gt2026.pdf", "hsmt",
         ["HỒ SƠ MỜI THẦU - Mua sắm thiết bị tin học 2026",
          "Chương I. Chỉ dẫn nhà thầu", "Chương III. Tiêu chuẩn đánh giá"])
    _doc(db, pid, "TBMT", "tbmt_gt2026.pdf", "tbmt",
         ["THÔNG BÁO MỜI THẦU", "Thời điểm đóng thầu: 09:00 ngày 15/03/2026",
          "Thời điểm mở thầu: 09:30 ngày 15/03/2026"], file_kind="pdf_scan")
    _doc(db, pid, "HSDT", "webform_ket_qua_mo_thau.pdf", "hsdt/0",
         ["KẾT QUẢ MỞ THẦU (webform)",
          "An Phát: 4.520.000.000 VND", "TS-ĐV: 4.410.000.000 VND",
          "Hòa Bình: 4.980.000.000 VND", "Minh Quang: 4.750.000.000 VND"],
         artifact_type="webform")

    # ---- Hồ sơ từng nhà thầu ----
    for v, ten_tat in ((v_ap, "an_phat"), (v_ld, "ts_dv"), (v_hb, "hoa_binh"), (v_mq, "minh_quang")):
        sub = f"hsdt/{v.id}"
        _doc(db, pid, "HSDT", f"don_du_thau_{ten_tat}.pdf", sub,
             [f"ĐƠN DỰ THẦU - {v.ten}", "Kính gửi: Bên mời thầu",
              "Đại diện hợp pháp ký tên, đóng dấu"],
             vendor_id=v.id, artifact_type="don_du_thau")
        _doc(db, pid, "HSDT", f"bao_dam_du_thau_{ten_tat}.pdf", sub,
             [f"BẢO ĐẢM DỰ THẦU - {v.ten}", "Giá trị: 96.000.000 VND",
              "Hiệu lực: 150 ngày kể từ ngày đóng thầu"],
             vendor_id=v.id, artifact_type="bao_dam_du_thau")
        _doc(db, pid, "HSDT", f"bang_gia_{ten_tat}.pdf", sub,
             [f"BẢNG GIÁ DỰ THẦU - {v.ten}", "Tổng cộng: xem chi tiết từng hạng mục"],
             vendor_id=v.id, artifact_type="bang_gia")

    _doc(db, pid, "HSDT", "thoa_thuan_lien_danh_ts_dv.pdf", f"hsdt/{v_ld.id}",
         ["THỎA THUẬN LIÊN DANH", "Thành viên đứng đầu: Công ty CP Trường Sơn (60%)",
          "Thành viên: Công ty TNHH Đại Việt (40%)"],
         vendor_id=v_ld.id, artifact_type="thoa_thuan_lien_danh")
    # Hòa Bình: 1 file nghi tải nhầm loại + 1 file OCR lỗi -> xem cảnh báo trên giao diện
    _doc(db, pid, "HSDT", "dang_ky_kinh_doanh_hoa_binh.pdf", f"hsdt/{v_hb.id}",
         ["GIẤY CHỨNG NHẬN ĐĂNG KÝ DOANH NGHIỆP", "Công ty TNHH Thương mại Hòa Bình"],
         vendor_id=v_hb.id, artifact_type="bao_cao_tai_chinh",
         validation={"match": False, "suggested_type": "dang_ky_kinh_doanh", "confidence": 0.88,
                     "note": "Nội dung là giấy ĐKKD, không phải báo cáo tài chính"})
    _doc(db, pid, "HSDT", "catalogue_hoa_binh.pdf", f"hsdt/{v_hb.id}",
         ["(bản scan mờ)"], vendor_id=v_hb.id, artifact_type="catalogue_thong_so",
         file_kind="pdf_scan", trang_thai_ocr="loi: không đọc được trang 2-5")

    # ---- Tiêu chí đánh giá ----
    NG1, NG2, NG3, NG4 = "E-CDNT 11.1", "E-CDNT 18.2", "E-BDL 18", "E-CDNT 4.2"
    _crit(db, pid, 0, "Đơn dự thầu hợp lệ",
          "Đơn dự thầu phải được đại diện hợp pháp của nhà thầu ký tên, đóng dấu (nếu có). "
          "Đối với nhà thầu liên danh, đơn dự thầu phải do đại diện hợp pháp của từng thành viên "
          "liên danh ký tên, đóng dấu hoặc do đại diện hợp pháp của thành viên đứng đầu liên danh "
          "ký theo phân công trách nhiệm trong văn bản thỏa thuận liên danh.",
          ["don_du_thau", "thoa_thuan_lien_danh"], True,
          [{"ten": "Có chữ ký của đại diện hợp pháp", "ho_so": "don_du_thau",
            "yeu_cau": "Có chữ ký và đóng dấu", "nguon": NG1},
           {"ten": "Thành viên liên danh cùng ký theo thỏa thuận",
            "ho_so": "thoa_thuan_lien_danh", "yeu_cau": "Đúng phân công trong thỏa thuận",
            "nguon": NG1, "ap_dung": AP_DUNG_LIEN_DANH}])
    _crit(db, pid, 1, "Bảo đảm dự thầu",
          "Bảo đảm dự thầu phải có giá trị và thời hạn hiệu lực đáp ứng yêu cầu của HSMT.",
          ["bao_dam_du_thau"], True,
          [{"ten": "Giá trị bảo đảm", "ho_so": "bao_dam_du_thau",
            "yeu_cau": "Không thấp hơn mức quy định", "chuan": "≥ 96.000.000 VND",
            "nguon": NG3},
           {"ten": "Thời hạn hiệu lực", "ho_so": "bao_dam_du_thau",
            "yeu_cau": "Đủ số ngày kể từ đóng thầu", "chuan": "≥ 150 ngày kể từ 15/03/2026",
            "nguon": NG3}])
    _crit(db, pid, 2, "Hiệu lực hồ sơ dự thầu",
          "HSDT phải có hiệu lực không ngắn hơn thời hạn quy định trong E-BDL.",
          ["don_du_thau"], True,
          [{"ten": "Thời hạn hiệu lực HSDT", "ho_so": "don_du_thau",
            "yeu_cau": "Đủ số ngày quy định", "chuan": "≥ 120 ngày kể từ 15/03/2026",
            "nguon": NG2}])
    _crit(db, pid, 3, "Tư cách hợp lệ của nhà thầu",
          "Nhà thầu có tên trên Hệ thống mạng đấu thầu quốc gia, hạch toán độc lập, "
          "không đang trong quá trình giải thể.",
          ["dang_ky_kinh_doanh"], False,
          [{"ten": "Đăng ký trên Hệ thống", "ho_so": "dang_ky_kinh_doanh",
            "yeu_cau": "Có tên trên hệ thống", "nguon": NG4, "can_review": True,
            "can_lam_ro": "Cần đối chiếu với dữ liệu hệ thống mạng đấu thầu quốc gia"}],
          loi_ai="Không tra được trạng thái trên hệ thống — cần chuyên gia xác nhận thủ công")
    _crit(db, pid, 4, "Giá dự thầu khớp webform",
          "Giá dự thầu ghi trong bảng giá phải khớp với giá trên webform kết quả mở thầu.",
          ["bang_gia", "webform"], False,
          [{"ten": "Đối chiếu giá bảng giá vs webform", "ho_so": "bang_gia",
            "yeu_cau": "Hai phía khớp nhau", "nguon": "E-CDNT 26.1"}])

    # Tiêu chí THUẦN liên danh -> với nhà thầu độc lập cả tiêu chí thành "không áp dụng"
    # (khác với ca trên: N/A ở cấp nội dung, tiêu chí vẫn roll-up thành "đạt").
    _crit(db, pid, 5, "Thỏa thuận liên danh hợp lệ",
          "Văn bản thỏa thuận liên danh phải phân định rõ trách nhiệm, quyền hạn, khối lượng "
          "công việc của từng thành viên và có chữ ký của đại diện hợp pháp các bên.",
          ["thoa_thuan_lien_danh"], True,
          [{"ten": "Phân định trách nhiệm từng thành viên", "ho_so": "thoa_thuan_lien_danh",
            "yeu_cau": "Ghi rõ phần việc và tỷ lệ", "nguon": "E-CDNT 11.3",
            "ap_dung": AP_DUNG_LIEN_DANH},
           {"ten": "Đủ chữ ký các thành viên", "ho_so": "thoa_thuan_lien_danh",
            "yeu_cau": "Có chữ ký đại diện hợp pháp mỗi bên", "nguon": "E-CDNT 11.3",
            "ap_dung": AP_DUNG_LIEN_DANH}])

    # ---- Kết quả đã chấm ----
    HS_AP = [{"loai_ho_so": "don_du_thau", "files": ["don_du_thau_an_phat.pdf"], "n_trang": 1},
             {"loai_ho_so": "bao_dam_du_thau", "files": ["bao_dam_du_thau_an_phat.pdf"], "n_trang": 1},
             {"loai_ho_so": "bang_gia", "files": ["bang_gia_an_phat.pdf"], "n_trang": 1}]

    # An Phát — hợp lệ hoàn toàn (có 1 N/A vì là nhà thầu độc lập)
    _profile(db, pid, v_ap.id, HINH_THUC_DOC_LAP, "đơn dự thầu (AI đọc)",
             "Đơn dự thầu do đại diện Công ty CP Xây dựng An Phát ký, không có thỏa thuận liên danh",
             HS_AP)
    _eval(db, pid, v_ap.id, 0, "Đơn dự thầu hợp lệ", True, "Đơn dự thầu phải được đại diện hợp pháp ký tên",
          [{"ten": "Có chữ ký của đại diện hợp pháp", "ho_so": "don_du_thau", "ket_qua": KET_QUA_DAT,
            "bang_chung": "Trang 1: chữ ký Giám đốc Nguyễn Văn A, có dấu tròn công ty",
            "trang": [1], "do_tin": 0.95, "nguon": NG1, "nguon_doc": ["don_du_thau"]},
           {"ten": "Thành viên liên danh cùng ký theo thỏa thuận", "ho_so": "thoa_thuan_lien_danh",
            "ket_qua": KET_QUA_KHONG_AP_DUNG, "trang": [], "do_tin": 1.0, "nguon": NG1,
            "ghi_chu": "Nhà thầu độc lập — nội dung này chỉ áp dụng với nhà thầu liên danh"}])
    _eval(db, pid, v_ap.id, 1, "Bảo đảm dự thầu", True, "Bảo đảm dự thầu phải đáp ứng giá trị và hiệu lực",
          [{"ten": "Giá trị bảo đảm", "ho_so": "bao_dam_du_thau", "ket_qua": KET_QUA_DAT,
            "chuan": "≥ 96.000.000 VND", "bang_chung": "Trang 1: 96.000.000 VND",
            "trang": [1], "do_tin": 0.93, "nguon": NG3, "nguon_doc": ["bao_dam_du_thau"]},
           {"ten": "Thời hạn hiệu lực", "ho_so": "bao_dam_du_thau", "ket_qua": KET_QUA_DAT,
            "chuan": "≥ 150 ngày kể từ 15/03/2026", "bang_chung": "Trang 1: hiệu lực 150 ngày",
            "trang": [1], "do_tin": 0.9, "nguon": NG3, "nguon_doc": ["bao_dam_du_thau", "tbmt"]}])
    _eval(db, pid, v_ap.id, 2, "Hiệu lực hồ sơ dự thầu", True, "HSDT phải có hiệu lực đủ dài",
          [{"ten": "Thời hạn hiệu lực HSDT", "ho_so": "don_du_thau", "ket_qua": KET_QUA_DAT,
            "chuan": "≥ 120 ngày kể từ 15/03/2026", "bang_chung": "Trang 1: hiệu lực 120 ngày",
            "trang": [1], "do_tin": 0.88, "nguon": NG2}])
    _eval(db, pid, v_ap.id, 3, "Tư cách hợp lệ của nhà thầu", False, "Nhà thầu có tên trên Hệ thống",
          [{"ten": "Đăng ký trên Hệ thống", "ho_so": "dang_ky_kinh_doanh", "ket_qua": KET_QUA_SOI,
            "bang_chung": "", "trang": [], "do_tin": 0.4, "nguon": NG4,
            "ghi_chu": "Không có giấy đăng ký kinh doanh trong HSDT — cần chuyên gia tra cứu"}])
    _eval(db, pid, v_ap.id, 4, "Giá dự thầu khớp webform", False, "Giá bảng giá phải khớp webform",
          [{"ten": "Đối chiếu giá bảng giá vs webform", "ho_so": "bang_gia", "ket_qua": KET_QUA_DAT,
            "bang_chung": "Bảng giá 4.520.000.000 VND = webform 4.520.000.000 VND",
            "trang": [1], "do_tin": 0.97, "nguon": "E-CDNT 26.1",
            "nguon_doc": ["bang_gia", "webform"]}])
    _eval(db, pid, v_ap.id, 5, "Thỏa thuận liên danh hợp lệ", True,
          "Văn bản thỏa thuận liên danh phải phân định rõ trách nhiệm các thành viên",
          [{"ten": "Phân định trách nhiệm từng thành viên", "ho_so": "thoa_thuan_lien_danh",
            "ket_qua": KET_QUA_KHONG_AP_DUNG, "trang": [], "do_tin": 1.0, "nguon": "E-CDNT 11.3",
            "ghi_chu": "Nhà thầu độc lập — tiêu chí chỉ áp dụng với nhà thầu liên danh"},
           {"ten": "Đủ chữ ký các thành viên", "ho_so": "thoa_thuan_lien_danh",
            "ket_qua": KET_QUA_KHONG_AP_DUNG, "trang": [], "do_tin": 1.0, "nguon": "E-CDNT 11.3",
            "ghi_chu": "Nhà thầu độc lập — tiêu chí chỉ áp dụng với nhà thầu liên danh"}])
    # Kiểm tra thường trực của hệ thống: mỗi kiểm tra một TIÊU CHÍ, đếm chung trong tổng hợp
    # — xem experiment/evaluate/pipeline._thanh_tieu_chi.
    _eval(db, pid, v_ap.id, 10, "Người ký đơn dự thầu khớp đại diện pháp luật (ĐKKD)", False, "",
          [{"ten": "Người ký đơn dự thầu khớp đại diện pháp luật (ĐKKD)", "ho_so": "don_du_thau",
            "ket_qua": KET_QUA_SOI, "bang_chung": "Người ký: Nguyễn Văn A",
            "trang": [1], "do_tin": 0.5,
            "ghi_chu": "Không có ĐKKD trong HSDT để đối chiếu người ký"}],
          nhom="phat_hien_bo_sung")
    _eval(db, pid, v_ap.id, 11, "Tên gói thầu ghi trong tài liệu khớp gói thầu đang xét", False, "",
          [{"ten": "Tên gói thầu ghi trong tài liệu khớp gói thầu đang xét",
            "ho_so": "don_du_thau", "ket_qua": KET_QUA_DAT,
            "bang_chung": "Đơn ghi 'Gói thầu Mua sắm máy tính xách tay' — trùng gói đang xét",
            "trang": [1], "do_tin": 0.9, "ghi_chu": ""}],
          nhom="phat_hien_bo_sung")
    _eval(db, pid, v_ap.id, 12,
          "Người ký bảo đảm dự thầu có thẩm quyền (đứng đầu hoặc ủy quyền hợp lệ)", False, "",
          [{"ten": "Người ký bảo đảm dự thầu có thẩm quyền", "ho_so": "bao_dam_du_thau",
            "ket_qua": KET_QUA_KHONG,
            "bang_chung": "Thư bảo lãnh do Phó giám đốc chi nhánh ký, không kèm giấy ủy quyền",
            "trang": [1], "do_tin": 0.85,
            "ghi_chu": "Ký thay mà không có ủy quyền — chuyên gia cần xem xét loại"}],
          nhom="phat_hien_bo_sung")
    _eval(db, pid, v_ap.id, 13,
          "Phân công liên danh nêu rõ hạng mục và khớp tỷ lệ trong bảng giá", False, "",
          [{"ten": "Phân công liên danh nêu rõ hạng mục và khớp tỷ lệ trong bảng giá",
            "ho_so": "thoa_thuan_lien_danh", "ket_qua": KET_QUA_KHONG_AP_DUNG, "trang": [],
            "do_tin": 1.0,
            "ghi_chu": "HSDT không có thỏa thuận liên danh — nhà thầu dự thầu độc lập"}],
          nhom="phat_hien_bo_sung")

    # Liên danh TS-ĐV — hợp lệ, nội dung liên danh được chấm thật
    _profile(db, pid, v_ld.id, HINH_THUC_LIEN_DANH, "thỏa thuận liên danh",
             "Thỏa thuận liên danh giữa Trường Sơn (60%) và Đại Việt (40%)",
             [{"loai_ho_so": "don_du_thau", "files": ["don_du_thau_ts_dv.pdf"], "n_trang": 1},
              {"loai_ho_so": "thoa_thuan_lien_danh", "files": ["thoa_thuan_lien_danh_ts_dv.pdf"],
               "n_trang": 1}])
    _eval(db, pid, v_ld.id, 0, "Đơn dự thầu hợp lệ", True, "Đơn dự thầu phải được đại diện hợp pháp ký tên",
          [{"ten": "Có chữ ký của đại diện hợp pháp", "ho_so": "don_du_thau", "ket_qua": KET_QUA_DAT,
            "bang_chung": "Trang 1: chữ ký đại diện Trường Sơn (thành viên đứng đầu)",
            "trang": [1], "do_tin": 0.94, "nguon": NG1},
           {"ten": "Thành viên liên danh cùng ký theo thỏa thuận", "ho_so": "thoa_thuan_lien_danh",
            "ket_qua": KET_QUA_DAT,
            "bang_chung": "Thỏa thuận điều 3: Trường Sơn được ủy quyền ký đơn dự thầu",
            "trang": [1], "do_tin": 0.91, "nguon": NG1,
            "nguon_doc": ["don_du_thau", "thoa_thuan_lien_danh"]}])
    _eval(db, pid, v_ld.id, 1, "Bảo đảm dự thầu", True, "Bảo đảm dự thầu phải đáp ứng giá trị và hiệu lực",
          [{"ten": "Giá trị bảo đảm", "ho_so": "bao_dam_du_thau", "ket_qua": KET_QUA_DAT,
            "chuan": "≥ 96.000.000 VND", "bang_chung": "Trang 1: 96.000.000 VND",
            "trang": [1], "do_tin": 0.92, "nguon": NG3},
           {"ten": "Thời hạn hiệu lực", "ho_so": "bao_dam_du_thau", "ket_qua": KET_QUA_SOI,
            "chuan": "≥ 150 ngày kể từ 15/03/2026",
            "bang_chung": "Trang 1: ghi 'hiệu lực đến 10/08/2026'", "trang": [1], "do_tin": 0.6,
            "nguon": NG3, "ghi_chu": "Ghi theo ngày cụ thể, cần quy đổi và xác nhận đủ 150 ngày"}])
    _eval(db, pid, v_ld.id, 2, "Hiệu lực hồ sơ dự thầu", True, "HSDT phải có hiệu lực đủ dài",
          [{"ten": "Thời hạn hiệu lực HSDT", "ho_so": "don_du_thau", "ket_qua": KET_QUA_DAT,
            "chuan": "≥ 120 ngày kể từ 15/03/2026", "bang_chung": "Trang 1: hiệu lực 130 ngày",
            "trang": [1], "do_tin": 0.9, "nguon": NG2}])
    _eval(db, pid, v_ld.id, 3, "Tư cách hợp lệ của nhà thầu", False, "Nhà thầu có tên trên Hệ thống",
          [{"ten": "Đăng ký trên Hệ thống", "ho_so": "dang_ky_kinh_doanh", "ket_qua": KET_QUA_SOI,
            "trang": [], "do_tin": 0.4, "nguon": NG4,
            "ghi_chu": "Cần tra cứu hệ thống cho cả hai thành viên liên danh"}])
    _eval(db, pid, v_ld.id, 4, "Giá dự thầu khớp webform", False, "Giá bảng giá phải khớp webform",
          [{"ten": "Đối chiếu giá bảng giá vs webform", "ho_so": "bang_gia", "ket_qua": KET_QUA_DAT,
            "bang_chung": "Bảng giá 4.410.000.000 VND = webform 4.410.000.000 VND",
            "trang": [1], "do_tin": 0.96, "nguon": "E-CDNT 26.1",
            "nguon_doc": ["bang_gia", "webform"]}])

    _eval(db, pid, v_ld.id, 5, "Thỏa thuận liên danh hợp lệ", True,
          "Văn bản thỏa thuận liên danh phải phân định rõ trách nhiệm các thành viên",
          [{"ten": "Phân định trách nhiệm từng thành viên", "ho_so": "thoa_thuan_lien_danh",
            "ket_qua": KET_QUA_DAT,
            "bang_chung": "Điều 2: Trường Sơn 60% (thiết bị), Đại Việt 40% (lắp đặt)",
            "trang": [1], "do_tin": 0.93, "nguon": "E-CDNT 11.3"},
           {"ten": "Đủ chữ ký các thành viên", "ho_so": "thoa_thuan_lien_danh",
            "ket_qua": KET_QUA_DAT, "bang_chung": "Trang 1: đủ 2 chữ ký, 2 dấu",
            "trang": [1], "do_tin": 0.9, "nguon": "E-CDNT 11.3"}])

    # Hòa Bình — có tiêu chí KHÔNG ĐẠT + mâu thuẫn hình thức
    _profile(db, pid, v_hb.id, HINH_THUC_LIEN_DANH, "hồ sơ HSDT",
             "Đơn dự thầu nhắc tới 'các thành viên liên danh' nhưng không có thỏa thuận liên danh",
             [{"loai_ho_so": "don_du_thau", "files": ["don_du_thau_hoa_binh.pdf"], "n_trang": 1}],
             mau_thuan=True,
             ghi_chu="Nhà thầu KHAI BÁO độc lập nhưng hồ sơ có dấu hiệu liên danh — cần làm rõ")
    _eval(db, pid, v_hb.id, 0, "Đơn dự thầu hợp lệ", True, "Đơn dự thầu phải được đại diện hợp pháp ký tên",
          [{"ten": "Có chữ ký của đại diện hợp pháp", "ho_so": "don_du_thau", "ket_qua": KET_QUA_DAT,
            "bang_chung": "Trang 1: có chữ ký và dấu", "trang": [1], "do_tin": 0.9, "nguon": NG1},
           {"ten": "Thành viên liên danh cùng ký theo thỏa thuận", "ho_so": "thoa_thuan_lien_danh",
            "ket_qua": KET_QUA_KHONG, "bang_chung": "Không tìm thấy thỏa thuận liên danh trong HSDT",
            "trang": [], "do_tin": 0.85, "nguon": NG1,
            "ghi_chu": "Đơn nhắc tới liên danh nhưng thiếu văn bản thỏa thuận"}])
    _eval(db, pid, v_hb.id, 1, "Bảo đảm dự thầu", True, "Bảo đảm dự thầu phải đáp ứng giá trị và hiệu lực",
          [{"ten": "Giá trị bảo đảm", "ho_so": "bao_dam_du_thau", "ket_qua": KET_QUA_KHONG,
            "chuan": "≥ 96.000.000 VND", "bang_chung": "Trang 1: 50.000.000 VND",
            "trang": [1], "do_tin": 0.95, "nguon": NG3,
            "ghi_chu": "Thấp hơn mức yêu cầu 46.000.000 VND"},
           {"ten": "Thời hạn hiệu lực", "ho_so": "bao_dam_du_thau", "ket_qua": KET_QUA_DAT,
            "chuan": "≥ 150 ngày kể từ 15/03/2026", "bang_chung": "Trang 1: hiệu lực 150 ngày",
            "trang": [1], "do_tin": 0.9, "nguon": NG3}])
    _eval(db, pid, v_hb.id, 2, "Hiệu lực hồ sơ dự thầu", True, "HSDT phải có hiệu lực đủ dài",
          [{"ten": "Thời hạn hiệu lực HSDT", "ho_so": "don_du_thau",
            "ket_qua": KET_QUA_LOI if with_error else KET_QUA_SOI,
            "chuan": "≥ 120 ngày kể từ 15/03/2026", "trang": [], "do_tin": 0.0, "nguon": NG2,
            "ghi_chu": ("Proxy vision lỗi khi đọc trang này — chưa có kết luận"
                        if with_error else "Trang scan mờ, không đọc được thời hạn")}])
    _eval(db, pid, v_hb.id, 3, "Tư cách hợp lệ của nhà thầu", False, "Nhà thầu có tên trên Hệ thống",
          [{"ten": "Đăng ký trên Hệ thống", "ho_so": "dang_ky_kinh_doanh", "ket_qua": KET_QUA_DAT,
            "bang_chung": "Giấy ĐKKD số 0301234567 (tải nhầm mục báo cáo tài chính)",
            "trang": [1], "do_tin": 0.7, "nguon": NG4}])
    _eval(db, pid, v_hb.id, 4, "Giá dự thầu khớp webform", False, "Giá bảng giá phải khớp webform",
          [{"ten": "Đối chiếu giá bảng giá vs webform", "ho_so": "bang_gia", "ket_qua": KET_QUA_KHONG,
            "bang_chung": "Bảng giá 4.880.000.000 VND ≠ webform 4.980.000.000 VND",
            "trang": [1], "do_tin": 0.93, "nguon": "E-CDNT 26.1",
            "nguon_doc": ["bang_gia", "webform"], "ghi_chu": "Chênh lệch 100.000.000 VND"}])

    _eval(db, pid, v_hb.id, 5, "Thỏa thuận liên danh hợp lệ", True,
          "Văn bản thỏa thuận liên danh phải phân định rõ trách nhiệm các thành viên",
          [{"ten": "Phân định trách nhiệm từng thành viên", "ho_so": "thoa_thuan_lien_danh",
            "ket_qua": KET_QUA_SOI, "trang": [], "do_tin": 0.3, "nguon": "E-CDNT 11.3",
            "ghi_chu": "Hồ sơ có dấu hiệu liên danh nhưng không nộp thỏa thuận — cần làm rõ"},
           {"ten": "Đủ chữ ký các thành viên", "ho_so": "thoa_thuan_lien_danh",
            "ket_qua": KET_QUA_SOI, "trang": [], "do_tin": 0.3, "nguon": "E-CDNT 11.3",
            "ghi_chu": "Không có văn bản để đối chiếu chữ ký"}])

    # Minh Quang: có hồ sơ nhưng CHƯA chấm.  Tân Tiến: chưa có hồ sơ nào.
    db.commit()

    n_doc = db.query(models.TenderDocument).filter_by(package_id=pid).count()
    n_crit = db.query(models.RubricCriterion).filter_by(package_id=pid).count()
    print(f"""
Đã tạo gói DEMO (id={pid}, mã {MA_SO})
  {n_doc} tài liệu, {n_crit} tiêu chí, 5 nhà thầu:
    An Phát    - đã chấm, hợp lệ (có 1 nội dung 'không áp dụng' vì độc lập)
    TS-ĐV      - đã chấm, liên danh, 1 nội dung 'cần làm rõ'
    Hòa Bình   - đã chấm, có tiêu chí không đạt + mâu thuẫn hình thức{' + 1 verdict LỖI (chặn xuất báo cáo)' if with_error else ''}
    Minh Quang - có hồ sơ, CHƯA chấm
    Tân Tiến   - chưa có hồ sơ

  LƯU Ý: verdict trong gói này do script seed viết, KHÔNG phải kết quả AI.
""")
    db.close()


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv, with_error="--with-error" in sys.argv)
