from experiment.extract.schema import Block, GroupContent
from experiment.extract.render import groups_to_markdown


def _grp(**kw):
    base = dict(group="nang_luc", muc="Mục 2. Năng lực", muc_page=[27, 40],
               is_reference=False, ref_target=None, blocks=[])
    base.update(kw)
    return GroupContent(**base)


def test_renders_table_as_markdown():
    g = _grp(blocks=[Block(type="table", page=[28, 28],
                           rows=[["TT", "Mô tả"], ["1", "Lịch sử\nhợp đồng"]])])
    md = groups_to_markdown("E-HSMT", [27, 42], [g])
    assert "| TT | Mô tả |" in md
    assert "| --- | --- |" in md
    assert "Lịch sử hợp đồng" in md  # newline trong ô -> space


def test_renders_reference_note():
    g = _grp(group="ky_thuat", muc="Mục 3. Kỹ thuật",
             is_reference=True, ref_target={"kind": "phan", "number": "4"},
             blocks=[Block(type="text", page=[40, 40], text="Theo Phần 4")])
    md = groups_to_markdown("E-HSMT", [27, 42], [g])
    assert "Tham chiếu" in md and "phan 4" in md.lower()
    assert "Theo Phần 4" in md


def test_renders_text_block():
    g = _grp(group="hop_le", muc="Mục 1. Hợp lệ",
             blocks=[Block(type="text", page=[27, 27], text="E-HSDT hợp lệ khi...")])
    md = groups_to_markdown("E-HSMT", [27, 42], [g])
    assert "E-HSDT hợp lệ khi..." in md
    assert "Mục 1. Hợp lệ" in md
