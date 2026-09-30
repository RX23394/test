"""Rebuild the keyword search index from the chunks already stored in it.

Run this after a migration that changes how text is tokenized. FTS5 segments
text as rows are written, so existing rows keep their old segmentation until
they are rewritten; the chunk text itself is preserved in the index, so a
rebuild needs no source file, no embedding model, and no LLM call.

Usage, from the ``backend`` directory:

    python -m app.cli.rebuild_search_index
"""

import argparse
import logging

from app.core.logging import configure_logging
from app.db.session import SessionFactory
from app.services.search_index_rebuild import rebuild_document_chunks_index

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the search index rebuild argument parser."""
    return argparse.ArgumentParser(
        description="Rebuild the keyword search index from stored chunks"
    )


def main() -> None:
    """Re-tokenize every stored chunk and report how many were rewritten."""
    configure_logging()
    build_parser().parse_args()

    with SessionFactory() as session:
        try:
            rebuilt = rebuild_document_chunks_index(session.connection())
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Search index rebuild failed")
            raise SystemExit(1) from None

    logger.info("Search index rebuilt for %s chunks", rebuilt)


if __name__ == "__main__":
    main()
