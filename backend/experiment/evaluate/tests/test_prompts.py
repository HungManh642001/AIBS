from experiment.evaluate.prompts import ingest_prompt, eval_prompt


def test_ingest_prompt_ocr_only_no_classification():
    p = ingest_prompt()
    assert "[IN]" in p
    assert "text" in p and "co_chu_ky" in p
    assert "loai_ho_so" not in p              # loại hồ sơ đã biết khi tải -> KHÔNG bắt LLM phân loại


def test_eval_prompt_carries_standard_and_tag():
    nd = {"noi_dung_kiem_tra": "Giá trị bảo lãnh", "yeu_cau": "Thỏa mãn giá trị",
          "thong_tin_bo_sung": "6.100.000 VNĐ", "kieu_check": "đối chiếu"}
    p = eval_prompt(nd, "Trang HSDT: bảo lãnh 6.100.000", has_image=False)
    assert "[EV:Giá trị bảo lãnh]" in p
    assert "6.100.000 VNĐ" in p          # chuẩn HSMT (thong_tin_bo_sung)
    assert "Thỏa mãn giá trị" in p        # yêu cầu
    assert "Trang HSDT" in p              # nội dung HSDT
