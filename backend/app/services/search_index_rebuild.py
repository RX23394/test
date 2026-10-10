"""Rebuild the keyword search index from the chunks already stored in it.

Changing the tokenizer cannot be done in place: FTS5 tokenizes as rows are
written, so existing rows keep the old segmentation until they are rewritten.
The chunk text is preserved in the content table, so a rebuild only has to
re-tokenize it and let the FTS5 triggers reindex the rows. It never re-parses a
source file and never calls the embedding model or the LLM, which keeps the
operation free and fast.
"""

import logging

from sqlalchemy import Connection, text

from app.db.schema import (
    DOCUMENT_CHUNK_ROWS_TABLE,
    DOCUMENT_CHUNKS_FTS_TABLE,
)
from app.services.tokenization import TokenizationService, get_tokenization_service

logger = logging.getLogger(__name__)


def rebuild_document_chunks_index(
    connection: Connection,
    tokenizer: TokenizationService | None = None,
) -> int:
    """Rewrite every stored chunk with its current tokenization.

    Returns the number of chunks rewritten. The function is idempotent and
    transactional: it commits only after every row has been rewritten.
    """
    resolved_tokenizer = tokenizer or get_tokenization_service()
    rows = list(
        connection.execute(
            text(
                f"""
                SELECT id, content
                FROM {DOCUMENT_CHUNK_ROWS_TABLE}
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
            "row_id": int(row["id"]),
            "content_tokens": resolved_tokenizer.tokenize_for_index(
                str(row["content"])
            ),
        }
        for row in rows
    ]
    # The update trigger reindexes each rewritten row.
    connection.execute(
        text(
            f"""
            UPDATE {DOCUMENT_CHUNK_ROWS_TABLE}
            SET content_tokens = :content_tokens
            WHERE id = :row_id
            """
        ),
        payload,
    )
    # Rebuild from the content table as a final consistency step, so an index
    # that was already out of step is repaired too.
    connection.execute(
        text(
            f"INSERT INTO {DOCUMENT_CHUNKS_FTS_TABLE}"
            f"({DOCUMENT_CHUNKS_FTS_TABLE}) VALUES ('rebuild')"
        )
    )
    logger.info("Search index rebuilt for %s chunks", len(payload))
    return len(payload)
