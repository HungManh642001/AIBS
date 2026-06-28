import json
from experiment.extract.schema import Block, GroupContent, groups_to_json


def test_groups_to_json_preserves_unicode_and_rows():
    g = GroupContent(
        group="nang_luc", muc="Mục 2. Tiêu chuẩn đánh giá về năng lực và kinh nghiệm",
        muc_page=[27, 40], is_reference=False, ref_target=None,
        blocks=[Block(type="table", page=[28, 39], rows=[["TT", "Mô tả"], ["1", "Lịch sử"]])],
    )
    s = groups_to_json("E-HSMT", [27, 42], [g])
    data = json.loads(s)
    assert "\\u" not in s
    assert data["doc"] == "E-HSMT"
    assert data["chuong3_page"] == [27, 42]
    assert data["groups"][0]["blocks"][0]["rows"][1] == ["1", "Lịch sử"]
    assert data["groups"][0]["blocks"][0]["text"] is None
