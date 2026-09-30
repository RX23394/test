"""Rebuild the keyword search index from the chunks already stored in it.

Changing the tokenizer cannot be done in place: FTS5 tokenizes as rows are
written, so existing rows keep the old segmentation until they are rewritten.
The chunk text is preserved in the ``content`` column, so a rebuild only has to
re-tokenize and reinsert. It never re-parses a source file and never calls the
embedding model or the LLM, which keeps the operation free and fast.
"""

import logging

from sqlalchemy import Connection, text

from app.db.schema import DOCUMENT_CHUNKS_FTS_TABLE
from app.services.tokenization import TokenizationService, get_tokenization_service

logger = logging.getLogger(__name__)


def rebuild_document_chunks_index(
    connection: Connection,
    tokenizer: TokenizationService | None = None,
) -> int:
    """Rewrite every stored chunk with its current tokenization.

    Returns the number of chunks rewritten. The function is idempotent and
    transactional: it commits only after every row has been reinserted.
    """
    resolved_tokenizer = tokenizer or get_tokenization_service()
    rows = list(
        connection.execute(
            text(
                f"""
                SELECT document_id, chunk_index, content, page, section
                FROM {DOCUMENT_CHUNKS_FTS_TABLE}
                ORDER BY document_id, chunk_index
                """
            )
        ).mappings()
    )
    if not rows:
        logger.info("Search index rebuild skipped: no stored chunks")
        return 0

    payload = [
        {
            "document_id": int(row["document_id"]),
            "chunk_index": int(row["chunk_index"]),
            "content": str(row["content"]),
            "page": row["page"],
            "section": row["section"],
            "content_tokens": resolved_tokenizer.tokenize_for_index(
                str(row["content"])
            ),
        }
        for row in rows
    ]

    connection.execute(text(f"DELETE FROM {DOCUMENT_CHUNKS_FTS_TABLE}"))
    connection.execute(
        text(
            f"""
            INSERT INTO {DOCUMENT_CHUNKS_FTS_TABLE}
                (document_id, chunk_index, content, page, section, content_tokens)
            VALUES
                (:document_id, :chunk_index, :content, :page, :section,
                 :content_tokens)
            """
        ),
        payload,
    )
    logger.info("Search index rebuilt for %s chunks", len(payload))
    return len(payload)
