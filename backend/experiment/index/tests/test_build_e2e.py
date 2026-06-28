from experiment.index.build_index import run as build_run
from experiment.index.query_index import run as query_run


def test_build_e2e_with_fake_embedder(sample_chunks, det_embedder, tmp_path):
    """Sample-gated: build toàn bộ chunks.jsonl bằng DeterministicEmbedding (offline)."""
    n_chunks = len(sample_chunks["chunks"])
    db = tmp_path / "qdrant"
    out = tmp_path / "out"

    metrics = build_run(
        chunks_path=sample_chunks["path"],
        db_path=str(db),
        out_dir=str(out),
        embed=det_embedder,
    )

    assert metrics["n_chunks"] == n_chunks
    assert metrics["n_points"] == n_chunks  # mọi chunk vào collection, không mất/nhân đôi
    assert metrics["dense_dim"] == 256
    assert metrics["sparse"] is True
    assert (out / "index_report.md").exists()

    # Truy hồi lại từ collection vừa dựng.
    results = query_run(query="bảo đảm dự thầu", k=5, db_path=str(db), embed=det_embedder)
    assert results
    assert results[0]["chunk_id"]
