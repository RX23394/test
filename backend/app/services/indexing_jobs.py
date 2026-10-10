"""Background document indexing jobs.

Parsing, embedding, and writing a large document can take minutes, so the HTTP
request only claims the job and returns its identifier. The pipeline then runs
with a session this module owns: the request-scoped session given to ``get_db``
is already closed when a FastAPI background task runs.

The process-wide embedding, vector, and parser dependencies are resolved by the
request and passed in, so a background job uses exactly the objects the test
suite can replace.
"""

import logging
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.repositories.document import DocumentRepository
from app.repositories.fts import FtsChunkRepository
from app.services.chunk import ChunkService
from app.services.document_parser import DocumentParsingService, ParserRegistry
from app.services.embedding import EmbeddingService
from app.services.indexing import (
    ChunkVectorRepository,
    DocumentIndexingService,
)

logger = logging.getLogger(__name__)


def claim_indexing_job(repository: DocumentRepository, document_id: int) -> str | None:
    """Release any expired lease, claim the document, and return the job id."""
    settings = get_settings()
    repository.release_expired_lease(document_id, settings.indexing_lease_seconds)
    job_id = str(uuid4())
    if repository.claim_for_indexing(document_id, job_id) is None:
        return None
    return job_id


def run_indexing_job(
    session_factory: sessionmaker[Session],
    document_id: int,
    job_id: str,
    *,
    embedding_service: EmbeddingService,
    vector_repository: ChunkVectorRepository,
    parser_registry: ParserRegistry,
) -> None:
    """Run the indexing pipeline for one claimed document.

    Failures are recorded on the document row by the pipeline itself (status
    ``failed`` plus store compensation), so this function only logs them.
    """
    settings = get_settings()
    with session_factory() as session:
        repository = DocumentRepository(session)
        document = repository.get_by_id(document_id)
        if document is None:
            logger.warning(
                "Indexing job %s: document %s no longer exists",
                job_id,
                document_id,
            )
            return

        service = DocumentIndexingService(
            document_repository=repository,
            parsing_service=DocumentParsingService(
                repository,
                settings.document_upload_dir,
                parser_registry,
                manage_status=False,
            ),
            chunk_service=ChunkService(),
            embedding_service=embedding_service,
            vector_repository=vector_repository,
            text_repository=FtsChunkRepository(session),
        )
        try:
            service.index(document, job_id)
        except Exception:
            logger.exception(
                "Background indexing failed",
                extra={"document_id": document_id},
            )
        finally:
            # This session is the job's transaction boundary: the completion or
            # failure status written by the pipeline becomes visible here, and a
            # transaction that cannot commit is rolled back so the lease reaper
            # can recover the document.
            try:
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                logger.exception(
                    "Background indexing status could not be committed",
                    extra={"document_id": document_id},
                )
