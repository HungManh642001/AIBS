from experiment.index.build_index import run as build_run
from experiment.index.query_index import run as query_run
from experiment.index.schema import keep_for_index


def test_build_e2e_with_fake_embedder(sample_chunks, det_embedder, tmp_path):
    """Sample-gated: build chunks.jsonl bằng DeterministicEmbedding (offline), có lọc TCĐG/Biểu mẫu."""
    total = len(sample_chunks["chunks"])
    kept = sum(1 for c in sample_chunks["chunks"] if keep_for_index(c))
    db = tmp_path / "qdrant"
    out = tmp_path / "out"

    metrics = build_run(
        chunks_path=sample_chunks["path"],
        db_path=str(db),
        out_dir=str(out),
        embed=det_embedder,
    )

    assert metrics["n_chunks"] == kept          # chỉ index chương mang giá trị
    assert metrics["n_excluded"] == total - kept
    assert metrics["n_points"] == kept          # mọi chunk giữ lại vào collection, không mất/nhân đôi
    assert metrics["dense_dim"] == 256
    assert metrics["sparse"] is True
    assert (out / "index_report.md").exists()

    # Truy hồi lại từ collection vừa dựng.
    results = query_run(query="bảo đảm dự thầu", k=5, db_path=str(db), embed=det_embedder)
    assert results
    assert results[0]["chunk_id"]
