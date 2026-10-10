"""Release document indexing leases that outlived their worker.

An indexing worker that crashes, is killed, or loses its database connection
leaves the document in ``processing``; the lease timestamp added in revision
``20261010_0010`` makes that state detectable, and this command resets every
expired lease to ``failed`` so the document can be indexed again.

The index endpoint already releases an expired lease for the document it is
asked to index, so this command is the operator-facing sweep for the rest.

Usage, from the ``backend`` directory:

    python -m app.cli.reap_stale_indexing
"""

import argparse
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionFactory
from app.repositories.document import DocumentRepository

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the stale indexing lease argument parser."""
    parser = argparse.ArgumentParser(
        description="Reset documents whose indexing lease expired"
    )
    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=None,
        help="Lease duration to apply (defaults to INDEXING_LEASE_SECONDS)",
    )
    return parser


def main() -> None:
    """Reset every expired indexing lease and report how many were reset."""
    configure_logging()
    arguments = build_parser().parse_args()
    lease_seconds = (
        arguments.lease_seconds
        if arguments.lease_seconds is not None
        else get_settings().indexing_lease_seconds
    )
    if lease_seconds < 0:
        raise SystemExit("--lease-seconds must not be negative")

    with SessionFactory() as session:
        try:
            released = DocumentRepository(session).release_all_expired_leases(
                lease_seconds
            )
            # The command owns its transaction: repositories only flush.
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Stale indexing lease sweep failed")
            raise SystemExit(1) from None

    logger.info("Released %s expired indexing leases", released)


if __name__ == "__main__":
    main()
