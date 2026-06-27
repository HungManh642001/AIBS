from services.prompts import cot_block, SCALE_DEF


def test_cot_block_demands_reasoning_then_json():
    b = cot_block('{"result":"..."}')
    assert "suy luận" in b.lower()
    assert "```json" in b
    assert '{"result":"..."}' in b


def test_cot_block_includes_scale_when_given():
    b = cot_block('{"x":1}', scale=SCALE_DEF)
    assert "PASS" in b and "FAIL" in b and "PARTIAL" in b
