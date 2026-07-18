from services.prompts import cot_block


def test_cot_block_demands_reasoning_then_json():
    b = cot_block('{"result":"..."}')
    assert "suy luận" in b.lower()
    assert "```json" in b
    assert '{"result":"..."}' in b


def test_cot_block_yeu_cau_evidence_truoc_ket_luan():
    """Ràng buộc chống ảo giác: bắt model dẫn chứng trước khi chốt kết quả."""
    b = cot_block('{"x":1}')
    assert "TRƯỚC result" in b
