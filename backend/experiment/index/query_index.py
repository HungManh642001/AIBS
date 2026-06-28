"""CLI: truy hồi hybrid top-k từ collection Qdrant đã dựng; in để người soi mắt.

Chế độ thật cần proxy (dense query). --fake dùng DeterministicEmbedding để kiểm tra keyword
(BM25 thật) offline; RRF vẫn kéo node khớp keyword lên top.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

from config import get_settings

from experiment.index.embedder import DeterministicEmbedding, build_embedder
from experiment.index.schema import COLLECTION
from experiment.index.store import build_vector_store, hybrid_retriever, open_index

from qdrant_client import QdrantClient

_DEFAULT_DB = "out/qdrant"


def run(
    query: str,
    k: int = 5,
    db_path: str = _DEFAULT_DB,
    collection: str = COLLECTION,
    embed: Any | None = None,
) -> list[dict[str, Any]]:
    """Truy hồi hybrid top-k; trả list {score, chunk_id, page, section_path, snippet}."""
    if embed is None:
        embed = build_embedder(get_settings())
    client = QdrantClient(path=str(db_path))
    try:
        store = build_vector_store(client, collection)
        index = open_index(store, embed)
        hits = hybrid_retriever(index, k).retrieve(query)
        results = []
        for h in hits:
            md = h.node.metadata or {}
            results.append(
                {
                    "score": round(float(h.score or 0.0), 4),
                    "chunk_id": md.get("chunk_id"),
                    "page": [md.get("page_start"), md.get("page_end")],
                    "section_path": md.get("section_path"),
                    "snippet": (h.node.text or "")[:160].replace("\n", " "),
                }
            )
        return results
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Truy hồi hybrid từ Qdrant index")
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--db", default=_DEFAULT_DB)
    ap.add_argument("--collection", default=COLLECTION)
    ap.add_argument("--fake", action="store_true", help="DeterministicEmbedding (offline keyword)")
    args = ap.parse_args(argv)

    embed = DeterministicEmbedding() if args.fake else None
    try:
        results = run(args.query, k=args.k, db_path=args.db, collection=args.collection, embed=embed)
    except Exception as exc:
        print(f"[query_index] LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"Top {len(results)} cho: {args.query!r}")
    for i, r in enumerate(results, 1):
        print(f"{i:>2}. score={r['score']:<8} trang={r['page']} {r['section_path']}")
        print(f"    {r['snippet']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
