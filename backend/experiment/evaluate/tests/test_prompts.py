from experiment.evaluate.prompts import ingest_prompt, eval_prompt, catalog_codes


def test_ingest_prompt_has_tag_and_codes():
    p = ingest_prompt()
    assert "[IN]" in p
    assert "don_du_thau" in catalog_codes()
    assert "loai_ho_so" in p


def test_eval_prompt_carries_standard_and_tag():
    nd = {"noi_dung_kiem_tra": "Giá trị bảo lãnh", "yeu_cau": "Thỏa mãn giá trị",
          "thong_tin_bo_sung": "6.100.000 VNĐ", "kieu_check": "đối chiếu"}
    p = eval_prompt(nd, "Trang HSDT: bảo lãnh 6.100.000", has_image=False)
    assert "[EV:Giá trị bảo lãnh]" in p
    assert "6.100.000 VNĐ" in p          # chuẩn HSMT (thong_tin_bo_sung)
    assert "Thỏa mãn giá trị" in p        # yêu cầu
    assert "Trang HSDT" in p              # nội dung HSDT
