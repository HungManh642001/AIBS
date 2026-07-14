from experiment.evaluate.schema import (
    validate_ingest_page, validate_eval_verdict, CriterionEval, Verdict,
    EvalResult, result_to_json, PageRecord, VendorContext,
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI, KET_QUA_KHONG_AP_DUNG,
)


def _v(ket_qua="đạt"):
    return Verdict(noi_dung_kiem_tra="Giá trị bảo lãnh", hsdt_kiem_tra="bao_dam_du_thau",
                   yeu_cau="Thỏa mãn giá trị", thong_tin_bo_sung="6.100.000 VNĐ",
                   ket_qua=ket_qua, bang_chung="ghi 6.100.000", trang=[1], do_tin=0.9, ghi_chu="")


def test_validate_ingest_page_defaults():
    out = validate_ingest_page({"text": "abc", "field_la": "bỏ"})
    assert out["text"] == "abc"
    assert out["co_chu_ky"] is False and out["co_dau"] is False
    assert "field_la" not in out and "loai_ho_so" not in out  # ingest KHÔNG phân loại


def test_validate_eval_verdict_defaults():
    out = validate_eval_verdict({"ket_qua": "đạt", "bang_chung": "x"})
    assert out["ket_qua"] == "đạt" and out["trang"] == [] and out["do_tin"] == 0.0


def test_result_to_json_omits_image_and_summary():
    ce = CriterionEval(nhom="hop_le", ten="Bảo đảm dự thầu", tien_quyet=True,
                       ket_qua="đạt", loai=False, verdicts=[_v("đạt")])
    r = EvalResult(doc="HSDT-A", criteria=[ce])
    d = result_to_json(r)
    assert d["doc"] == "HSDT-A"
    assert d["criteria"][0]["verdicts"][0]["ket_qua"] == "đạt"
    assert "image" not in str(d)  # bytes ảnh KHÔNG lọt vào JSON
    assert d["summary"]["n_dat"] == 1 and d["summary"]["n_tieu_chi"] == 1


def test_verdict_nguon_doc_backward_compat():
    """Verdict dựng kiểu cũ (không nguon_doc) vẫn OK; JSON chứa nguon_doc; luật đặt được đa nguồn."""
    v = _v("đạt")                                     # positional cũ — không nguon_doc
    assert v.nguon_doc == []
    ce = CriterionEval(nhom="hop_le", ten="Đơn dự thầu", tien_quyet=False,
                       ket_qua="đạt", loai=False, verdicts=[v])
    d = result_to_json(EvalResult(doc="A", criteria=[ce]))
    assert d["criteria"][0]["verdicts"][0]["nguon_doc"] == []
    v2 = _v("đạt")
    v2.nguon_doc = ["don_du_thau", "tu_cach_phap_ly"]
    assert v2.nguon_doc == ["don_du_thau", "tu_cach_phap_ly"]


def test_vendor_context_defaults():
    ctx = VendorContext(ten="Công ty TNHH ABC")
    assert ctx.ten == "Công ty TNHH ABC" and ctx.ma_so_thue == "" and ctx.aliases == []
    ctx2 = VendorContext(ten="ABC", ma_so_thue="0123", aliases=["abc jsc"])
    assert ctx2.aliases == ["abc jsc"]


def test_summary_counts_khong_ap_dung_separately():
    """'không áp dụng' có counter RIÊNG — không lẫn vào đạt/không đạt/cần làm rõ."""
    def _ce(ket_qua):
        return CriterionEval(nhom="hop_le", ten=ket_qua, tien_quyet=False,
                             ket_qua=ket_qua, loai=False, verdicts=[_v(ket_qua)])
    r = EvalResult(doc="A", criteria=[_ce(KET_QUA_DAT), _ce(KET_QUA_KHONG),
                                      _ce(KET_QUA_SOI), _ce(KET_QUA_KHONG_AP_DUNG)])
    s = r.summary
    assert s["n_tieu_chi"] == 4
    assert s["n_dat"] == 1 and s["n_khong_dat"] == 1 and s["n_can_lam_ro"] == 1
    assert s["n_khong_ap_dung"] == 1
    assert s["n_loai"] == 0


def test_page_record_holds_image_bytes():
    p = PageRecord(file="a.pdf", trang=1, loai_ho_so="don_du_thau", text="x",
                   co_chu_ky=True, co_dau=False, image=b"\x89PNG")
    assert p.image == b"\x89PNG"
