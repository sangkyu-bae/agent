from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.application.doc_browse.get_chunks_use_case import GetChunksUseCase
from src.application.doc_browse.list_documents_use_case import ListDocumentsUseCase

router = APIRouter(prefix="/api/v1/collections", tags=["Document Browse"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_list_documents_use_case() -> ListDocumentsUseCase:
    raise NotImplementedError


def get_chunks_use_case() -> GetChunksUseCase:
    raise NotImplementedError


# ── Response Schemas ─────────────────────────────────────────────

class DocumentSummaryResponse(BaseModel):
    document_id: str
    filename: str
    category: str
    chunk_count: int
    chunk_types: list[str]
    user_id: str


class DocumentListResponse(BaseModel):
    collection_name: str
    documents: list[DocumentSummaryResponse]
    total_documents: int
    offset: int
    limit: int


class ChunkDetailResponse(BaseModel):
    chunk_id: str
    chunk_index: int
    chunk_type: str
    content: str
    metadata: dict[str, str]


class ParentChunkGroupResponse(BaseModel):
    chunk_id: str
    chunk_index: int
    chunk_type: str
    content: str
    children: list[ChunkDetailResponse]


class ChunkListResponse(BaseModel):
    document_id: str
    filename: str
    chunk_strategy: str
    total_chunks: int
    chunks: list[ChunkDetailResponse] = []
    parents: list[ParentChunkGroupResponse] | None = None


# ── Endpoints ────────────────────────────────────────────────────

@router.get(
    "/{collection_name}/documents",
    response_model=DocumentListResponse,
)
async def list_documents(
    collection_name: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    use_case: ListDocumentsUseCase = Depends(get_list_documents_use_case),
):
    return await use_case.execute(collection_name, offset=offset, limit=limit)


@router.get(
    "/{collection_name}/documents/{document_id}/chunks",
    response_model=ChunkListResponse,
)
async def get_document_chunks(
    collection_name: str,
    document_id: str,
    include_parent: bool = Query(False),
    use_case: GetChunksUseCase = Depends(get_chunks_use_case),
):
    result = await use_case.execute(
        collection_name, document_id, include_parent=include_parent
    )
    return result
