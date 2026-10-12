r"""Show where each document ranks in the vector leg, and why it is dropped.

Diagnoses retrieval without touching the running server: it prints the first
rank at which each document appears and marks it ``OUTSIDE LIMIT`` (cut by
``VECTOR_SEARCH_LIMIT``) or ``below floor`` (cut by ``RETRIEVAL_MIN_SCORE``), so
it is obvious which of the two stages dropped a document.

Run from the project root:

    .venv\\Scripts\\python.exe scripts\\probe_retrieval_rank.py "你的问题"
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

QUESTION = sys.argv[1] if len(sys.argv) > 1 else "OSPF 邻居关系是怎么建立的？"
DATABASE = BACKEND / "network_rag.db"


def main() -> int:
    """Report the best rank per document inside the applied candidate limit."""
    from qdrant_client import QdrantClient

    from app.core.config import get_settings
    from app.services.embedding import EmbeddingService
    from app.services.search import VECTOR_SEARCH_LIMIT

    settings = get_settings()
    vector = EmbeddingService().embed_query(QUESTION)[0]
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    points = client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=vector,
        limit=300,
        with_payload=True,
    ).points

    connection = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True)
    names = dict(
        connection.execute("select id, original_filename from documents").fetchall()
    )

    first_rank: dict[int, tuple[int, float]] = {}
    for rank, point in enumerate(points, start=1):
        document_id = int((point.payload or {}).get("document_id", -1))
        if document_id not in first_rank:
            first_rank[document_id] = (rank, point.score)

    print(f"question      : {QUESTION}")
    print(f"vector limit  : {VECTOR_SEARCH_LIMIT} (VECTOR_SEARCH_LIMIT)")
    print(f"vector floor  : {settings.retrieval_min_score}")
    print("\nfirst appearance of each document in the vector ranking:")
    for document_id, (rank, score) in sorted(
        first_rank.items(), key=lambda item: item[1][0]
    ):
        inside = "in candidates" if rank <= VECTOR_SEARCH_LIMIT else "OUTSIDE LIMIT"
        above = (
            "above floor" if score >= settings.retrieval_min_score else "below floor"
        )
        print(
            f"   rank {rank:>3}  score {score:.4f}  doc {document_id:>3} "
            f"{names.get(document_id, '?')}  [{inside}, {above}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
