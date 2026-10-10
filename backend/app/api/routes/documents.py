"""Administrator document endpoints."""

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.exc import SQLAlchemyError

from app.api.pagination import (
    DEFAULT_PAGE_SIZE,
    LimitQuery,
    OffsetQuery,
    set_total_count_header,
)
from app.auth.dependencies import CurrentAdmin, SessionDependency
from app.core.config import get_settings
from app.db.session import SessionFactoryDependency
from app.models.document import DocumentStatus
from app.rag.dependencies import EmbeddingDependency, QdrantDependency
from app.repositories.document import DocumentRepository
from app.repositories.fts import FtsChunkRepository
from app.schemas.document import DocumentResponse
from app.schemas.indexing import DocumentIndexJobResponse, DocumentIndexResult
from app.schemas.response import ResponseModel
from app.services.chunk import ChunkService
from app.services.document import (
    DocumentTooLargeError,
    DocumentUploadService,
    DuplicateDocumentError,
    UnsupportedDocumentTypeError,
)
from app.services.document_parser import (
    DocumentContent,
    DocumentFileNotFoundError,
    DocumentParseError,
    DocumentParsingService,
    UnsupportedParserError,
)
from app.services.document_parser.dependencies import ParserRegistryDependency
from app.services.indexing import (
    DocumentIndexError,
    DocumentIndexingService,
    DocumentIndexOwnershipError,
    DocumentTextEmptyError,
)
from app.services.indexing_jobs import claim_indexing_job, run_indexing_job

router = APIRouter(prefix="/api/admin/documents", tags=["admin-documents"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    response_model=ResponseModel[list[DocumentResponse]],
    response_model_exclude_none=True,
)
def list_documents(
    current_admin: CurrentAdmin,
    session: SessionDependency,
    response: Response,
    search: str | None = Query(default=None, max_length=255),
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
    offset: OffsetQuery = 0,
) -> ResponseModel[list[DocumentResponse]]:
    """List one page of documents for administrators with optional search."""
    del current_admin
    repository = DocumentRepository(session)
    documents = repository.list_all(search, limit=limit, offset=offset)
    set_total_count_header(response, repository.count_all(search))
    return ResponseModel(
        status="ok",
        data=[DocumentResponse.model_validate(document) for document in documents],
    )


@router.post(
    "",
    response_model=ResponseModel[DocumentResponse],
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    file: Annotated[UploadFile, File(description="Document to upload")],
    current_admin: CurrentAdmin,
    session: SessionDependency,
) -> ResponseModel[DocumentResponse]:
    """Store one supported document and return its persisted metadata."""
    settings = get_settings()
    service = DocumentUploadService(
        DocumentRepository(session),
        settings.document_upload_dir,
        settings.document_max_upload_bytes,
    )

    try:
        document = service.upload(
            source=file.file,
            original_filename=file.filename or "",
            uploader_id=current_admin.id,
        )
    except UnsupportedDocumentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported document types are pdf, docx, md, and txt",
        ) from exc
    except DocumentTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Document exceeds the 50MB size limit",
        ) from exc
    except DuplicateDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document already exists",
        ) from exc
    finally:
        file.file.close()

    return ResponseModel(
        status="ok",
        data=DocumentResponse.model_validate(document),
    )


@router.delete(
    "/{document_id}",
    response_model=ResponseModel[None],
    response_model_exclude_none=True,
)
def delete_document(
    document_id: int,
    current_admin: CurrentAdmin,
    session: SessionDependency,
    qdrant_repository: QdrantDependency,
) -> ResponseModel[None]:
    """Delete a document, its source file, and its search indexes."""
    del current_admin
    repository = DocumentRepository(session)
    document = repository.get_by_id(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    # Mark the row first: if any cleanup step fails, the document stays visible
    # as pending_delete instead of vanishing while its vectors remain orphaned.
    repository.update_status(document, DocumentStatus.PENDING_DELETE)
    try:
        qdrant_repository.delete_document(document.id)
    except Exception as exc:
        logger.warning(
            "Vector index cleanup failed during document deletion",
            extra={"document_id": document.id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document deletion service is unavailable",
        ) from exc

    try:
        FtsChunkRepository(session).delete_document(document.id)
        source_path = get_settings().document_upload_dir / document.filename
        source_path.unlink(missing_ok=True)
        repository.delete(document)
    except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document deletion service is unavailable",
        ) from exc

    return ResponseModel(status="ok")


@router.post(
    "/{document_id}/parse",
    response_model=ResponseModel[DocumentContent],
    response_model_exclude_none=True,
)
def parse_document(
    document_id: int,
    current_admin: CurrentAdmin,
    session: SessionDependency,
    parser_registry: ParserRegistryDependency,
) -> ResponseModel[DocumentContent]:
    """Extract and return normalized text from a stored document."""
    del current_admin
    repository = DocumentRepository(session)
    document = repository.get_by_id(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    settings = get_settings()
    service = DocumentParsingService(
        repository,
        settings.document_upload_dir,
        parser_registry,
        manage_status=False,
    )
    try:
        content = service.parse(document)
    except DocumentFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found",
        ) from exc
    except UnsupportedParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Document type is not supported",
        ) from exc
    except DocumentParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Document could not be parsed",
        ) from exc

    return ResponseModel(status="ok", data=content)


@router.post(
    "/{document_id}/index/async",
    response_model=ResponseModel[DocumentIndexJobResponse],
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_document_indexing(
    document_id: int,
    background_tasks: BackgroundTasks,
    current_admin: CurrentAdmin,
    session: SessionDependency,
    session_factory: SessionFactoryDependency,
    embedding_service: EmbeddingDependency,
    qdrant_repository: QdrantDependency,
    parser_registry: ParserRegistryDependency,
) -> ResponseModel[DocumentIndexJobResponse]:
    """Claim a document for indexing and run the pipeline in the background."""
    del current_admin
    repository = DocumentRepository(session)
    document = repository.get_by_id(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    if document.status is DocumentStatus.INDEXED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is already indexed",
        )

    job_id = claim_indexing_job(repository, document_id)
    if job_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document indexing is already in progress",
        )

    background_tasks.add_task(
        run_indexing_job,
        session_factory,
        document_id,
        job_id,
        embedding_service=embedding_service,
        vector_repository=qdrant_repository,
        parser_registry=parser_registry,
    )
    return ResponseModel(
        status="ok",
        data=DocumentIndexJobResponse(document_id=document_id, job_id=job_id),
    )


@router.post(
    "/{document_id}/index",
    response_model=ResponseModel[DocumentIndexResult],
    response_model_exclude_none=True,
)
def index_document(
    document_id: int,
    current_admin: CurrentAdmin,
    session: SessionDependency,
    embedding_service: EmbeddingDependency,
    qdrant_repository: QdrantDependency,
    parser_registry: ParserRegistryDependency,
) -> ResponseModel[DocumentIndexResult]:
    """Parse, chunk, embed, and index a stored document in Qdrant."""
    del current_admin
    repository = DocumentRepository(session)
    document = repository.get_by_id(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    if document.status is DocumentStatus.INDEXED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is already indexed",
        )

    settings = get_settings()
    # A worker that died mid-index must not block a retry forever: an expired
    # lease is released before the new claim is attempted.
    repository.release_expired_lease(document_id, settings.indexing_lease_seconds)
    job_id = str(uuid4())
    claimed_document = repository.claim_for_indexing(document_id, job_id)
    if claimed_document is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document indexing is already in progress",
        )

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
        vector_repository=qdrant_repository,
        text_repository=FtsChunkRepository(session),
    )
    try:
        result = service.index(claimed_document, job_id)
    except DocumentFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found",
        ) from exc
    except UnsupportedParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Document type is not supported",
        ) from exc
    except DocumentParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Document could not be parsed",
        ) from exc
    except DocumentTextEmptyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Document contains no extractable text; scanned files need OCR",
        ) from exc
    except DocumentIndexOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document indexing ownership was lost",
        ) from exc
    except (DocumentIndexError, OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document indexing service is unavailable",
        ) from exc

    return ResponseModel(status="ok", data=result)
