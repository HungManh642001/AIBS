import json
from pathlib import Path

from experiment.decompose.llm import ScriptedLlm
from experiment.decompose.run_decompose import run as decompose_run


def _generic_detail():
    return {
        "nhom": "hop_le", "ten": "Tiêu chí mẫu", "yeu_cau": "theo HSMT",
        "required_artifacts": [], "kieu": "pass_fail", "trong_so": 0.0,
        "sub_checks": [{"ten": "kiểm tra", "check_type": "presence", "thong_so": {},
                        "required_artifact": "", "blocking": True}],
        "proposed_artifacts": [],
    }


async def test_run_e2e_with_scripted(sample_groups, tmp_path):
    """Sample-gated: chạy run() trên chuong3_groups.json thật với LLM kịch bản -> 4 nhóm + artefact."""
    n_groups = len(sample_groups["data"]["groups"])

    # Khớp theo prefix tag: mọi lời gọi detail trả 1 tiêu chí mẫu hợp lệ.
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Tiêu chí mẫu"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:DETAIL:": _generic_detail(),
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
