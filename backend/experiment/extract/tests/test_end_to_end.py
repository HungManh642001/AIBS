# backend/experiment/extract/tests/test_end_to_end.py
import json

from experiment.extract.cli_extract import run


def test_end_to_end_writes_artefacts(sample_pdf, tmp_path):
    metrics = run(sample_pdf, str(tmp_path))

    data = json.loads((tmp_path / "chuong3_groups.json").read_text(encoding="utf-8"))
    assert (tmp_path / "chuong3_groups.md").exists()
    assert (tmp_path / "report.md").exists()

    assert [g["group"] for g in data["groups"]] == ["hop_le", "nang_luc", "ky_thuat", "tai_chinh"]
    assert metrics["n_groups"] == 4
    assert metrics["nang_luc_has_table"] is True
    assert metrics["ky_thuat_is_reference"] is True
