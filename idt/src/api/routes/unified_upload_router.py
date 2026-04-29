import uuid

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, Depends
from pydantic import BaseModel

from src.application.unified_upload.schemas import UnifiedUploadRequest
from src.application.unified_upload.use_case import UnifiedUploadUseCase
from src.config import settings


router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


class QdrantResult(BaseModel):
    collection_name: str
    stored_ids: list[str]
    embedding_model: str
    status: str
    error: str | None = None


class EsResult(BaseModel):
    index_name: str
    indexed_count: int
    status: str
    error: str | None = None


class ChunkingConfigResponse(BaseModel):
    strategy: str
    parent_chunk_size: int
    child_chunk_size: int
    child_chunk_overlap: int


class UnifiedUploadResponse(BaseModel):
    document_id: str
    filename: str
    total_pages: int
    chunk_count: int
    qdrant: QdrantResult
    es: EsResult
    chunking_config: ChunkingConfigResponse
    status: str


def get_unified_upload_use_case() -> UnifiedUploadUseCase:
    raise NotImplementedError("Must be overridden via dependency_overrides")


@router.post("/upload-all", response_model=UnifiedUploadResponse)
async def upload_all(
    file: UploadFile = File(...),
    user_id: str = Query(...),
    collection_name: str = Query(..., description="대상 Qdrant 컬렉션명"),
    child_chunk_size: int = Query(500, ge=100, le=4000),
    child_chunk_overlap: int = Query(50, ge=0, le=500),
    use_case: UnifiedUploadUseCase = Depends(get_unified_upload_use_case),
) -> UnifiedUploadResponse:
    request_id = str(uuid.uuid4())
    file_bytes = await file.read()
    filename = file.filename or "unknown.pdf"

    domain_request = UnifiedUploadRequest(
        file_bytes=file_bytes,
        filename=filename,
        user_id=user_id,
        collection_name=collection_name,
        child_chunk_size=child_chunk_size,
        child_chunk_overlap=child_chunk_overlap,
    )

    try:
        result = await use_case.execute(domain_request, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return UnifiedUploadResponse(
        document_id=result.document_id,
        filename=result.filename,
        total_pages=result.total_pages,
        chunk_count=result.chunk_count,
        qdrant=QdrantResult(
            collection_name=result.collection_name,
            stored_ids=result.qdrant.stored_ids,
            embedding_model=result.qdrant.embedding_model,
            status="success" if not result.qdrant.error else "failed",
            error=result.qdrant.error,
        ),
        es=EsResult(
            index_name=settings.es_index,
            indexed_count=result.es.indexed_count,
            status="success" if not result.es.error else "failed",
            error=result.es.error,
        ),
        chunking_config=ChunkingConfigResponse(
            strategy="parent_child",
            parent_chunk_size=2000,
            child_chunk_size=result.chunking_config["child_chunk_size"],
            child_chunk_overlap=result.chunking_config["child_chunk_overlap"],
        ),
        status=result.status,
    )
