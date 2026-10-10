"""Administrator document endpoints."""

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import CurrentAdmin, SessionDependency
from app.core.config import get_settings
from app.models.document import DocumentStatus
from app.rag.dependencies import EmbeddingDependency, QdrantDependency
from app.repositories.document import DocumentRepository
from app.repositories.fts import FtsChunkRepository
from app.schemas.document import DocumentResponse
from app.schemas.indexing import DocumentIndexResult
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
)

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
    search: str | None = Query(default=None, max_length=255),
) -> ResponseModel[list[DocumentResponse]]:
    """List documents for administrators with optional text search."""
    del current_admin
    documents = DocumentRepository(session).list_all(search)
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

    job_id = str(uuid4())
    claimed_document = repository.claim_for_indexing(document_id, job_id)
    if claimed_document is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document indexing is already in progress",
        )

    settings = get_settings()
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
