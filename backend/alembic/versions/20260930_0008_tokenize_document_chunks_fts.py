"""Tokenize document chunks for Chinese keyword search.

Revision ID: 20260930_0008
Revises: 20260806_0007
Create Date: 2026-09-30

The FTS5 table created in revision 20260715_0004 uses ``tokenize='unicode61'``,
which treats a run of CJK characters as one token. Measured against that schema,
the paragraph "配置BGP邻居关系时，需要在对等体下指定对端自治系统号" indexed as four
multi-character tokens, and the queries ``bgp``, ``配置``, ``邻居`` and
``自治系统`` each returned zero rows, so the keyword half of hybrid retrieval
contributed nothing for Chinese content.

This revision adds a ``content_tokens`` column holding a jieba token stream and
backfills it for every stored chunk. The chunk text is preserved in the
``content`` column, so no source file is re-parsed, and no embedding or LLM call
is made. jieba is imported from the installed dependency rather than from
``app.services`` so that this migration keeps working unchanged if the
application is later refactored.

The column list below must stay byte-identical to
``app.db.schema.DOCUMENT_CHUNKS_FTS_COLUMNS``: a migrated database and a
test-fixture database have to be the same shape.
"""

from collections.abc import Sequence

import jieba
from sqlalchemy import text

from alembic import op

revision: str = "20260930_0008"
down_revision: str | Sequence[str] | None = "20260806_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "document_chunks_fts"
TEMP_TABLE_NAME = "document_chunks_fts_v2"
MAX_TOKEN_CHARS = 64

CREATE_V2 = f"""
    CREATE VIRTUAL TABLE {TEMP_TABLE_NAME} USING fts5(
        document_id UNINDEXED,
        chunk_index UNINDEXED,
        content UNINDEXED,
        page UNINDEXED,
        section UNINDEXED,
        content_tokens,
        tokenize='unicode61'
    )
"""

CREATE_LEGACY_SHAPE = f"""
    CREATE VIRTUAL TABLE {TEMP_TABLE_NAME} USING fts5(
        document_id UNINDEXED,
        chunk_index UNINDEXED,
        content,
        page UNINDEXED,
        section UNINDEXED,
        tokenize='unicode61'
    )
"""


def tokenize_for_index(value: str) -> str:
    """Return the jieba token stream for one chunk of text."""
    tokens: list[str] = []
    for segment in jieba.cut_for_search(value):
        token = segment.strip()
        if not token:
            continue
        if len(token) > MAX_TOKEN_CHARS:
            tokens.extend(
                token[index : index + MAX_TOKEN_CHARS]
                for index in range(0, len(token), MAX_TOKEN_CHARS)
            )
            continue
        tokens.append(token)
    return " ".join(tokens)


def _read_chunks() -> list[dict[str, object]]:
    """Read every stored chunk, ordered for a deterministic rebuild."""
    rows = list(
        op.get_bind()
        .execute(
            text(
                f"SELECT document_id, chunk_index, content, page, section "
                f"FROM {TABLE_NAME} ORDER BY document_id, chunk_index"
            )
        )
        .mappings()
    )
    return [
        {
            "document_id": int(row["document_id"]),
            "chunk_index": int(row["chunk_index"]),
            "content": str(row["content"]),
            "page": row["page"],
            "section": row["section"],
        }
        for row in rows
    ]


def upgrade() -> None:
    """Add the token column and backfill it for every stored chunk."""
    chunks = _read_chunks()

    op.execute(f"DROP TABLE IF EXISTS {TEMP_TABLE_NAME}")
    op.execute(CREATE_V2)

    if chunks:
        op.get_bind().execute(
            text(
                f"""
                INSERT INTO {TEMP_TABLE_NAME}
                    (document_id, chunk_index, content, page, section,
                     content_tokens)
                VALUES
                    (:document_id, :chunk_index, :content, :page, :section,
                     :content_tokens)
                """
            ),
            [
                {
                    **chunk,
                    "content_tokens": tokenize_for_index(str(chunk["content"])),
                }
                for chunk in chunks
            ],
        )

    op.execute(f"DROP TABLE {TABLE_NAME}")
    op.execute(f"ALTER TABLE {TEMP_TABLE_NAME} RENAME TO {TABLE_NAME}")


def downgrade() -> None:
    """Restore the untokenized shape, keeping the stored chunk text."""
    chunks = _read_chunks()

    op.execute(f"DROP TABLE IF EXISTS {TEMP_TABLE_NAME}")
    op.execute(CREATE_LEGACY_SHAPE)

    if chunks:
        op.get_bind().execute(
            text(
                f"""
                INSERT INTO {TEMP_TABLE_NAME}
                    (document_id, chunk_index, content, page, section)
                VALUES
                    (:document_id, :chunk_index, :content, :page, :section)
                """
            ),
            chunks,
        )

    op.execute(f"DROP TABLE {TABLE_NAME}")
    op.execute(f"ALTER TABLE {TEMP_TABLE_NAME} RENAME TO {TABLE_NAME}")
