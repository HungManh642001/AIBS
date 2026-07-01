from experiment.evaluate.schema import (
    validate_ingest_page, validate_eval_verdict, CriterionEval, Verdict,
    EvalResult, result_to_json, PageRecord,
)


def _v(ket_qua="đạt"):
    return Verdict(noi_dung_kiem_tra="Giá trị bảo lãnh", hsdt_kiem_tra="bao_dam_du_thau",
                   yeu_cau="Thỏa mãn giá trị", thong_tin_bo_sung="6.100.000 VNĐ",
                   ket_qua=ket_qua, bang_chung="ghi 6.100.000", trang=[1], do_tin=0.9, ghi_chu="")


def test_validate_ingest_page_defaults():
    out = validate_ingest_page({"loai_ho_so": "don_du_thau", "text": "abc", "field_la": "bỏ"})
    assert out["loai_ho_so"] == "don_du_thau" and out["text"] == "abc"
    assert out["co_chu_ky"] is False and out["co_dau"] is False
    assert "field_la" not in out


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


def test_page_record_holds_image_bytes():
    p = PageRecord(file="a.pdf", trang=1, loai_ho_so="don_du_thau", text="x",
                   co_chu_ky=True, co_dau=False, image=b"\x89PNG")
    assert p.image == b"\x89PNG"
