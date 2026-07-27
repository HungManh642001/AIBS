from experiment.evaluate.report import to_markdown
from experiment.evaluate.schema import (
    HINH_THUC_DOC_LAP, KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_KHONG_AP_DUNG, KET_QUA_SOI,
    NGUON_DON_DU_THAU, CriterionEval, EvalResult, HoSoNhanDuoc, VendorContext, VendorProfile,
    Verdict,
)


def _v(noi_dung="Giá trị bảo lãnh", hsdt="bao_dam_du_thau", ket_qua=KET_QUA_KHONG,
       bang_chung="Số tiền bảo lãnh: 3.000.000 VNĐ", trang=None, nguon_hsmt="E-BDL 18.1",
       ghi_chu="", nguon_doc=None):
    return Verdict(noi_dung_kiem_tra=noi_dung, hsdt_kiem_tra=hsdt,
                   yeu_cau="Thỏa mãn giá trị bảo đảm dự thầu", thong_tin_bo_sung="6.100.000 VNĐ",
                   ket_qua=ket_qua, bang_chung=bang_chung, trang=[1] if trang is None else trang,
                   do_tin=0.9, ghi_chu=ghi_chu, nguon_doc=nguon_doc or [], nguon_hsmt=nguon_hsmt)


def _ce(ten="Bảo đảm dự thầu", ket_qua=KET_QUA_KHONG, loai=True, verdicts=None, tien_quyet=True,
        nhom="hop_le"):
    return CriterionEval(nhom=nhom, ten=ten, tien_quyet=tien_quyet, ket_qua=ket_qua, loai=loai,
                         verdicts=verdicts if verdicts is not None else [_v()],
                         yeu_cau_goc="" if nhom != "hop_le"
                         else "Nhà thầu phải nộp bảo đảm dự thầu 6.100.000 VNĐ")


def _result(profile=None, criteria=None):
    return EvalResult(
        doc="HSDT-A", vendor=VendorContext(ten="Công ty TNHH ABC", ma_so_thue="0312345678"),
        vendor_profile=profile or VendorProfile(hinh_thuc=HINH_THUC_DOC_LAP,
                                                nguon=NGUON_DON_DU_THAU,
                                                bang_chung="Chúng tôi... dự thầu độc lập",
                                                trang=[1], do_tin=0.9),
        ho_so_nhan_duoc=[HoSoNhanDuoc("bao_dam_du_thau", ["bl.pdf"], 1),
                         HoSoNhanDuoc("don_du_thau", ["don.pdf"], 3)],
        criteria=criteria if criteria is not None else [_ce()])


def test_markdown_header_shows_vendor_form_and_basis():
    md = to_markdown(_result())
    assert "Công ty TNHH ABC" in md and "0312345678" in md
    assert "độc lập" in md and NGUON_DON_DU_THAU in md
    assert "Chúng tôi... dự thầu độc lập" in md      # bằng chứng để kiểm chứng


def test_markdown_shows_conflict_warning_prominently():
    md = to_markdown(_result(profile=VendorProfile(mau_thuan=True,
                                                   ghi_chu="khai báo 'độc lập' nhưng HSDT CÓ hồ sơ")))
    assert "MÂU THUẪN" in md
    assert md.index("MÂU THUẪN") < md.index("## Hồ sơ nhận được")
    assert "khai báo 'độc lập' nhưng HSDT CÓ hồ sơ" in md


def test_markdown_no_conflict_warning_when_clean():
    assert "MÂU THUẪN" not in to_markdown(_result())


def test_markdown_lists_received_documents_table():
    md = to_markdown(_result())
    assert "## Hồ sơ nhận được" in md
    assert "bao_dam_du_thau" in md and "bl.pdf" in md
    assert "don_du_thau" in md and "don.pdf" in md


def test_markdown_can_xu_ly_section_comes_before_details():
    md = to_markdown(_result())
    assert md.index("CẦN XỬ LÝ") < md.index("Chi tiết theo tiêu chí")


def test_markdown_can_xu_ly_lists_only_actionable():
    """Chỉ loại/không đạt/cần làm rõ vào CẦN XỬ LÝ — tiêu chí đạt KHÔNG lọt vào."""
    md = to_markdown(_result(criteria=[
        _ce(), _ce(ten="Đạt tuốt", ket_qua=KET_QUA_DAT, loai=False,
                   verdicts=[_v(ket_qua=KET_QUA_DAT)])]))
    block = md[md.index("CẦN XỬ LÝ"):md.index("Chi tiết theo tiêu chí")]
    assert "Bảo đảm dự thầu" in block
    assert "Đạt tuốt" not in block


def test_markdown_details_sorted_loai_first():
    md = to_markdown(_result(criteria=[
        _ce(ten="Đạt tuốt", ket_qua=KET_QUA_DAT, loai=False, verdicts=[_v(ket_qua=KET_QUA_DAT)]),
        _ce(ten="Cần soi", ket_qua=KET_QUA_SOI, loai=False, verdicts=[_v(ket_qua=KET_QUA_SOI)]),
        _ce(ten="Bị loại")]))
    chi_tiet = md[md.index("Chi tiết theo tiêu chí"):]
    assert chi_tiet.index("Bị loại") < chi_tiet.index("Cần soi") < chi_tiet.index("Đạt tuốt")


def test_markdown_verdict_shows_both_sides():
    """Mỗi kết luận kiểm chứng được 2 chiều: HSMT (gốc/chuẩn/điều khoản) ↔ HSDT (trích/file+trang)."""
    md = to_markdown(_result())
    assert "Nhà thầu phải nộp bảo đảm dự thầu 6.100.000 VNĐ" in md   # yeu_cau_goc
    assert "6.100.000 VNĐ" in md                                      # chuẩn
    assert "E-BDL 18.1" in md                                         # điều khoản nguồn HSMT
    assert "bao_dam_du_thau (bl.pdf) tr.1" in md                      # file + trang bên HSDT
    assert "Số tiền bảo lãnh: 3.000.000 VNĐ" in md                    # trích dẫn HSDT


def test_markdown_na_section_shows_reason():
    md = to_markdown(_result(criteria=[_ce(
        ten="Thỏa thuận liên danh", ket_qua=KET_QUA_KHONG_AP_DUNG, loai=False,
        verdicts=[_v(noi_dung="Thỏa thuận liên danh hợp lệ", hsdt="thoa_thuan_lien_danh",
                     ket_qua=KET_QUA_KHONG_AP_DUNG, bang_chung="", trang=[],
                     ghi_chu="nhà thầu độc lập (căn cứ: khai báo) — chỉ áp dụng cho liên danh")])]))
    assert "Không áp dụng" in md
    assert "chỉ áp dụng cho liên danh" in md          # lý do hiện rõ, không im lặng bỏ qua


def test_markdown_na_criterion_not_in_details():
    md = to_markdown(_result(criteria=[
        _ce(), _ce(ten="Thỏa thuận liên danh", ket_qua=KET_QUA_KHONG_AP_DUNG, loai=False,
                   verdicts=[_v(ket_qua=KET_QUA_KHONG_AP_DUNG)])]))
    chi_tiet = md[md.index("Chi tiết theo tiêu chí"):md.index("## Không áp dụng")]
    assert "Thỏa thuận liên danh" not in chi_tiet


def test_markdown_rule_verdict_shows_all_nguon_doc():
    md = to_markdown(_result(criteria=[_ce(
        ten="Đơn dự thầu", ket_qua=KET_QUA_DAT, loai=False,
        verdicts=[_v(noi_dung="Bảng giá khớp webform", hsdt="bang_gia", ket_qua=KET_QUA_DAT,
                     nguon_doc=["bao_dam_du_thau", "don_du_thau"])])]))
    assert "bao_dam_du_thau (bl.pdf)" in md and "don_du_thau (don.pdf)" in md


def test_markdown_missing_page_numbers_is_explicit():
    """AI không nêu trang -> nói rõ, KHÔNG bịa số trang."""
    md = to_markdown(_result(criteria=[_ce(verdicts=[_v(trang=[])])]))
    assert "tr.(không nêu)" in md


def test_markdown_shows_ghi_chu_for_diagnosis():
    """ghi_chu phải hiện: phân biệt SOI do can_review (tất định) với SOI do AI chấm."""
    md = to_markdown(_result(criteria=[_ce(
        ket_qua=KET_QUA_SOI, loai=False,
        verdicts=[_v(ket_qua=KET_QUA_SOI, ghi_chu="chuẩn HSMT chưa tra được — cần chuyên gia")])]))
    assert "chuẩn HSMT chưa tra được" in md


def test_markdown_summary_counts():
    md = to_markdown(_result())
    assert "Tổng tiêu chí" in md and "Không áp dụng" in md


def test_to_markdown_does_not_mutate_criteria_order():
    r = _result(criteria=[_ce(ten="Đạt tuốt", ket_qua=KET_QUA_DAT, loai=False,
                              verdicts=[_v(ket_qua=KET_QUA_DAT)]),
                          _ce(ten="Bị loại")])
    before = [c.ten for c in r.criteria]
    to_markdown(r)
    assert [c.ten for c in r.criteria] == before      # sorted(), KHÔNG .sort()


def _pv(ket_qua=KET_QUA_KHONG):
    return Verdict(noi_dung_kiem_tra="Người ký đơn dự thầu khớp đại diện pháp luật (ĐKKD)",
                   hsdt_kiem_tra="don_du_thau", yeu_cau="Người ký phải là đại diện pháp luật",
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung="ký: A ≠ đại diện: B",
                   trang=[1], do_tin=0.9, ghi_chu="", nguon_doc=["don_du_thau", "dang_ky_kinh_doanh"])


def _ce_tt(ket_qua=KET_QUA_KHONG):
    """Kiểm tra thường trực là TIÊU CHÍ (nhóm phat_hien_bo_sung) nhưng KHÔNG tiên quyết."""
    from experiment.evaluate.schema import NHOM_PHAT_HIEN
    return _ce(ten="Người ký đơn dự thầu khớp đại diện pháp luật (ĐKKD)", ket_qua=ket_qua,
               loai=False, verdicts=[_pv(ket_qua)], nhom=NHOM_PHAT_HIEN, tien_quyet=False)


def test_kiem_tra_thuong_truc_khong_con_muc_rieng():
    """Không còn mục 'ngoài checklist HSMT' — nó là tiêu chí, nằm chung với tiêu chí HSMT."""
    md = to_markdown(_result(criteria=[_ce_tt()]))
    assert "ngoài checklist HSMT" not in md
    assert "ký: A ≠ đại diện: B" in md


def test_kiem_tra_thuong_truc_vao_can_xu_ly_kem_nhan_nguon():
    """Vào CẦN XỬ LÝ như tiêu chí thường, nhưng vẫn nêu rõ xuất xứ là hệ thống tự kiểm."""
    md = to_markdown(_result(criteria=[_ce_tt(KET_QUA_KHONG)]))
    block = md[md.index("CẦN XỬ LÝ"):md.index("Chi tiết theo tiêu chí")]
    assert "Người ký đơn dự thầu" in block
    assert "hệ thống tự kiểm" in block
    assert "LOẠI" not in block                  # KHÔNG tiên quyết -> không tự loại


def test_kiem_tra_thuong_truc_dat_khong_vao_can_xu_ly():
    md = to_markdown(_result(criteria=[_ce_tt(KET_QUA_DAT)]))
    block = md[md.index("CẦN XỬ LÝ"):md.index("Chi tiết theo tiêu chí")]
    assert "Người ký đơn dự thầu" not in block


def test_kiem_tra_thuong_truc_vao_summary_nhung_khong_tu_loai():
    """Đếm chung trong tổng kết, nhưng quyết định loại vẫn thuộc về chuyên gia."""
    r = _result(criteria=[_ce(ten="Đạt tuốt", ket_qua=KET_QUA_DAT, loai=False,
                              verdicts=[_v(ket_qua=KET_QUA_DAT)]),
                          _ce_tt(KET_QUA_KHONG)])
    assert r.summary["n_tieu_chi"] == 2 and r.summary["n_loai"] == 0
    assert "| Tổng tiêu chí | 2 |" in to_markdown(r)


def test_markdown_minimal_result_no_vendor():
    """EvalResult trần (không vendor/profile/hồ sơ) vẫn render được — không crash."""
    md = to_markdown(EvalResult(doc="HSDT-B"))
    assert "HSDT-B" in md


def test_bao_cao_neu_trang_nghi_doc_thieu():
    """Chuyên gia phải thấy trang nào đọc không chắc — nếu không, con số trong bảng giá vô nghĩa."""
    from experiment.evaluate.report import to_markdown
    from experiment.evaluate.schema import EvalResult

    r = EvalResult(doc="HSDT-A",
                   canh_bao_doc=["bg.pdf trang 3: số cột không đều: 2/5 hàng lệch"])
    md = to_markdown(r)
    assert "bg.pdf trang 3" in md and "số cột không đều" in md


def test_bao_cao_khong_nhac_khi_moi_trang_doc_on():
    from experiment.evaluate.report import to_markdown
    from experiment.evaluate.schema import EvalResult

    assert "CẢNH BÁO ĐỌC" not in to_markdown(EvalResult(doc="HSDT-A"))
