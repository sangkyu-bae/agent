"""Document upload API endpoints."""
from typing import Dict, Optional
import uuid

from fastapi import APIRouter, File, UploadFile, Depends, HTTPException, Query
from pydantic import BaseModel

from src.domain.pipeline.enums.document_category import DocumentCategory
from src.domain.pipeline.schemas.upload_schema import DocumentUploadResponse
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.compressor.interfaces.llm_provider_interface import LLMProviderInterface
from src.domain.vector.interfaces import VectorStoreInterface, EmbeddingInterface
from src.infrastructure.chunking.chunking_factory import ChunkingStrategyFactory
from src.infrastructure.pipeline.graph.document_processing_graph import (
    create_document_processing_graph,
    create_initial_state,
)
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

_async_tasks: Dict[str, dict] = {}

_DEFAULT_CHILD_CHUNK_SIZE = 500
_DEFAULT_PARENT_CHUNK_SIZE = 2000
_DEFAULT_CHILD_CHUNK_OVERLAP = 50


class DocumentProcessor:
    """Document processor interface for dependency injection."""

    async def process(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        child_chunk_size: int = _DEFAULT_CHILD_CHUNK_SIZE,
    ) -> dict:
        raise NotImplementedError("Implement in concrete class")


class GraphDocumentProcessor(DocumentProcessor):
    """DocumentProcessor implementation using LangGraph workflow.

    Creates a ParentChildStrategy per request using the given child_chunk_size.
    """

    def __init__(
        self,
        parser: PDFParserInterface,
        llm_provider: LLMProviderInterface,
        vectorstore: VectorStoreInterface,
        embedding: EmbeddingInterface,
        collection_name: str,
        parent_chunk_size: int = _DEFAULT_PARENT_CHUNK_SIZE,
        default_child_chunk_size: int = _DEFAULT_CHILD_CHUNK_SIZE,
        child_chunk_overlap: int = _DEFAULT_CHILD_CHUNK_OVERLAP,
    ):
        self._parser = parser
        self._llm_provider = llm_provider
        self._vectorstore = vectorstore
        self._embedding = embedding
        self._collection_name = collection_name
        self._parent_chunk_size = parent_chunk_size
        self._default_child_chunk_size = default_child_chunk_size
        self._child_chunk_overlap = child_chunk_overlap

    async def process(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        child_chunk_size: int = _DEFAULT_CHILD_CHUNK_SIZE,
    ) -> dict:
        effective_child_size = child_chunk_size or self._default_child_chunk_size

        chunking_strategy = ChunkingStrategyFactory.create_strategy(
            "parent_child",
            parent_chunk_size=self._parent_chunk_size,
            child_chunk_size=effective_child_size,
            child_chunk_overlap=self._child_chunk_overlap,
        )

        graph = create_document_processing_graph(
            parser=self._parser,
            llm_provider=self._llm_provider,
            chunking_strategy=chunking_strategy,
            vectorstore=self._vectorstore,
            embedding=self._embedding,
            collection_name=self._collection_name,
        )

        initial_state = create_initial_state(
            file_path="",
            filename=filename,
            user_id=user_id,
            file_bytes=file_bytes,
        )

        try:
            result = await graph.ainvoke(initial_state)

            chunking_config = {
                **result.get("chunking_config_used", {}),
                "child_chunk_size": effective_child_size,
                "parent_chunk_size": self._parent_chunk_size,
            }

            return {
                "document_id": result.get("document_id", ""),
                "filename": filename,
                "category": result.get("category"),
                "category_confidence": result.get("category_confidence", 0.0),
                "total_pages": result.get("total_pages", 0),
                "chunk_count": result.get("chunk_count", 0),
                "stored_ids": result.get("stored_ids", []),
                "status": result.get("status", "unknown"),
                "errors": result.get("errors", []),
                "processing_time_ms": result.get("processing_time_ms", 0),
                "chunking_config_used": chunking_config,
            }
        except Exception as e:
            logger.error(
                "Document processing failed",
                exception=e,
                file_name=filename,
                user_id=user_id,
            )
            raise


class AsyncTaskStatus(BaseModel):
    task_id: str
    status: str
    result: Optional[DocumentUploadResponse] = None
    error: Optional[str] = None


def get_document_processor() -> DocumentProcessor:
    raise NotImplementedError("Configure document processor dependency")


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Query(..., description="User ID for document ownership"),
    child_chunk_size: int = Query(
        _DEFAULT_CHILD_CHUNK_SIZE,
        ge=100,
        le=4000,
        description="Child chunk size in tokens (100–4000, default 500)",
    ),
    processor: DocumentProcessor = Depends(get_document_processor),
) -> DocumentUploadResponse:
    file_bytes = await file.read()
    filename = file.filename or "unknown.pdf"

    result = await processor.process(
        file_bytes=file_bytes,
        filename=filename,
        user_id=user_id,
        child_chunk_size=child_chunk_size,
    )

    if result.get("status") == "failed":
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Document processing failed",
                "errors": result.get("errors", []),
            },
        )

    return DocumentUploadResponse(
        document_id=result["document_id"],
        filename=result["filename"],
        category=result["category"],
        category_confidence=result["category_confidence"],
        total_pages=result["total_pages"],
        chunk_count=result["chunk_count"],
        stored_ids=result["stored_ids"],
        status=result["status"],
        errors=result["errors"],
    )


@router.post("/upload/async")
async def upload_document_async(
    file: UploadFile = File(...),
    user_id: str = Query(..., description="User ID for document ownership"),
) -> dict:
    task_id = str(uuid.uuid4())
    file_bytes = await file.read()
    filename = file.filename or "unknown.pdf"

    _async_tasks[task_id] = {
        "status": "pending",
        "filename": filename,
        "user_id": user_id,
        "file_bytes_size": len(file_bytes),
    }

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Document queued for processing",
    }


@router.get("/upload/status/{task_id}", response_model=AsyncTaskStatus)
async def get_upload_status(task_id: str) -> AsyncTaskStatus:
    task = _async_tasks.get(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return AsyncTaskStatus(
        task_id=task_id,
        status=task.get("status", "unknown"),
        result=task.get("result"),
        error=task.get("error"),
    )
