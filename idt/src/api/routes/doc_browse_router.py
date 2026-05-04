from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from src.application.doc_browse.delete_document_use_case import (
    DeleteDocumentUseCase,
)
from src.application.doc_browse.get_chunks_use_case import GetChunksUseCase
from src.application.doc_browse.list_documents_use_case import ListDocumentsUseCase

router = APIRouter(prefix="/api/v1/collections", tags=["Document Browse"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_list_documents_use_case() -> ListDocumentsUseCase:
    raise NotImplementedError


def get_chunks_use_case() -> GetChunksUseCase:
    raise NotImplementedError


def get_delete_document_use_case() -> DeleteDocumentUseCase:
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


# ── Delete Schemas ───────────────────────────────────────────────


class DeleteDocumentResponse(BaseModel):
    document_id: str
    collection_name: str
    filename: str
    deleted_qdrant_chunks: int
    deleted_es_chunks: int


class BatchDeleteRequest(BaseModel):
    document_ids: list[str]


class BatchDeleteItemResponse(BaseModel):
    document_id: str
    status: str
    deleted_qdrant_chunks: int = 0
    deleted_es_chunks: int = 0
    filename: str = ""
    error: str | None = None


class BatchDeleteResponse(BaseModel):
    total: int
    success_count: int
    failure_count: int
    results: list[BatchDeleteItemResponse]


# ── Delete Endpoints ─────────────────────────────────────────────


@router.delete(
    "/{collection_name}/documents/{document_id}",
    response_model=DeleteDocumentResponse,
)
async def delete_document(
    collection_name: str,
    document_id: str,
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_user_role: str = Header("user", alias="X-User-Role"),
    use_case: DeleteDocumentUseCase = Depends(get_delete_document_use_case),
):
    try:
        return await use_case.execute_single(
            collection_name=collection_name,
            document_id=document_id,
            user_id=x_user_id,
            user_role=x_user_role,
        )
    except use_case.DocumentNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {document_id}",
        )
    except use_case.PermissionDeniedError:
        raise HTTPException(
            status_code=403,
            detail="No permission to delete document",
        )


@router.delete(
    "/{collection_name}/documents",
    response_model=BatchDeleteResponse,
)
async def batch_delete_documents(
    collection_name: str,
    body: BatchDeleteRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_user_role: str = Header("user", alias="X-User-Role"),
    use_case: DeleteDocumentUseCase = Depends(get_delete_document_use_case),
):
    try:
        return await use_case.execute_batch(
            collection_name=collection_name,
            document_ids=body.document_ids,
            user_id=x_user_id,
            user_role=x_user_role,
        )
    except use_case.PermissionDeniedError:
        raise HTTPException(
            status_code=403,
            detail="No permission to delete documents",
        )
