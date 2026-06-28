"""CLI: chunks.jsonl -> Qdrant collection (hybrid) on-disk + index_report.md.

Chế độ thật cần LiteLLM proxy phục vụ model embedding. Proxy lỗi -> build_index raise,
collection bị xóa, CLI thoát mã != 0 — KHÔNG tạo vector giả (no-silent-mock).
Cờ --fake dùng DeterministicEmbedding để dựng/kiểm tra offline (BM25 vẫn thật).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from config import get_settings

from experiment.index.embedder import DeterministicEmbedding, build_embedder
from experiment.index.schema import COLLECTION, chunks_to_nodes
from experiment.index.store import build_index, build_vector_store

from qdrant_client import QdrantClient

_DEFAULT_CHUNKS = "out/chunks.jsonl"
_DEFAULT_DB = "out/qdrant"
_DEFAULT_OUT = "out"


def _load_chunks(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Không thấy chunks: {p} (chạy bước chunking trước)")
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_report(out_dir: Path, m: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    txt = (
        f"# Index report — {m['collection']}\n\n"
        f"- chunks: {m['n_chunks']}\n"
        f"- points: {m['n_points']}\n"
        f"- dense_dim: {m['dense_dim']}\n"
        f"- sparse: BM25 (Qdrant/bm25)\n"
        f"- db: {m['db']}\n"
        f"- elapsed: {m['elapsed']}s\n"
    )
    path = out_dir / "index_report.md"
    path.write_text(txt, encoding="utf-8")
    return path


def run(
    chunks_path: str = _DEFAULT_CHUNKS,
    db_path: str = _DEFAULT_DB,
    out_dir: str = _DEFAULT_OUT,
    collection: str = COLLECTION,
    embed: Any | None = None,
) -> dict[str, Any]:
    """Đọc chunks -> nodes -> dựng collection Qdrant on-disk; trả metrics + ghi report."""
    t0 = time.time()
    if embed is None:
        embed = build_embedder(get_settings())
    chunks = _load_chunks(chunks_path)
    nodes = chunks_to_nodes(chunks)

    db = Path(db_path)
    db.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(db))
    try:
        store = build_vector_store(client, collection)
        try:
            build_index(nodes, store, embed)
        except Exception:
            # Thất bại (vd proxy tắt) -> không để lại collection dở dang.
            try:
                client.delete_collection(collection)
            except Exception:
                pass
            raise
        n_points = client.count(collection).count
        dense_dim = len(embed.get_query_embedding("dim probe"))
    finally:
        client.close()

    metrics = {
        "collection": collection,
        "n_chunks": len(chunks),
        "n_points": n_points,
        "dense_dim": dense_dim,
        "sparse": True,
        "db": str(db),
        "elapsed": round(time.time() - t0, 2),
    }
    _write_report(Path(out_dir), metrics)
    return metrics


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build Qdrant hybrid index từ chunks.jsonl")
    ap.add_argument("--chunks", default=_DEFAULT_CHUNKS)
    ap.add_argument("--db", default=_DEFAULT_DB)
    ap.add_argument("--out", default=_DEFAULT_OUT)
    ap.add_argument("--collection", default=COLLECTION)
    ap.add_argument("--fake", action="store_true", help="Dùng DeterministicEmbedding (offline)")
    args = ap.parse_args(argv)

    embed = DeterministicEmbedding() if args.fake else None
    try:
        metrics = run(
            chunks_path=args.chunks,
            db_path=args.db,
            out_dir=args.out,
            collection=args.collection,
            embed=embed,
        )
    except Exception as exc:  # no-silent-mock: báo lỗi rõ, không tạo vector giả
        print(f"[build_index] LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "  Chế độ thật cần LiteLLM proxy chạy & phục vụ model embedding. "
            "Dùng --fake để dựng/kiểm tra offline.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
