import json
from pathlib import Path

from experiment.decompose.llm import ScriptedLlm
from experiment.decompose.run_decompose import run as decompose_run


def _generic_detail():
    return {
        "nhom": "hop_le", "ten": "Tiêu chí mẫu", "yeu_cau_goc": "theo HSMT",
        "hsdt_can_kiem_tra": ["don_du_thau"], "tien_quyet": False,
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": "Có tài liệu", "hsdt_kiem_tra": "don_du_thau",
             "yeu_cau": "phải có", "can_lam_ro": "", "can_tra_cuu": False}],
    }


async def test_run_e2e_with_scripted(sample_groups, tmp_path):
    """Sample-gated: chạy run() trên chuong3_groups.json thật với LLM kịch bản -> 4 nhóm + artefact."""
    n_groups = len(sample_groups["data"]["groups"])

    # Khớp theo prefix tag: structure trả 1 tiêu chí mẫu (không _need -> bỏ query/resolve).
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Tiêu chí mẫu"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:STRUCT:": _generic_detail(),
    })
    out = tmp_path / "out"
    metrics = await decompose_run(
        groups_path=sample_groups["path"],
        out_dir=str(out),
        llm_fn=llm,
        retrieve_fn=lambda q, k=5: [],
    )

    assert metrics["n_groups"] == n_groups
    assert (out / "decomposition.json").exists()
    assert (out / "decomposition.md").exists()
    assert (out / "decompose_report.md").exists()

    data = json.loads((out / "decomposition.json").read_text(encoding="utf-8"))
    assert len(data["groups"]) == n_groups
    assert data["summary"]["n_criteria"] >= n_groups  # mỗi nhóm ít nhất 1 tiêu chí
