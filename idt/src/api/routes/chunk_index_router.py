"""Chunk-and-Index API: 텍스트 청킹 + 키워드 추출 + ES 색인."""
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
from src.application.chunk_and_index.use_case import ChunkAndIndexUseCase

router = APIRouter(prefix="/api/v1/chunk-index", tags=["chunk-index"])

VALID_STRATEGY_TYPES = {"full_token", "parent_child", "semantic"}


class ChunkIndexAPIRequest(BaseModel):
    """청킹 + ES 색인 API 요청 스키마."""

    document_id: str = Field(..., description="문서 고유 ID")
    content: str = Field(..., description="청킹할 텍스트 내용")
    user_id: str = Field(..., description="사용자 ID")
    strategy_type: str = Field(default="parent_child", description="청킹 전략")
    metadata: dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터")
    chunk_size: int = Field(default=500, ge=100, description="청크 크기 (토큰)")
    chunk_overlap: int = Field(default=50, ge=0, description="청크 오버랩 (토큰)")
    top_keywords: int = Field(default=10, ge=1, le=50, description="추출할 키워드 수")


class IndexedChunkItem(BaseModel):
    """단일 색인된 청크 응답."""

    chunk_id: str
    chunk_type: str
    keywords: list[str]
    content: str


class ChunkIndexAPIResponse(BaseModel):
    """청킹 + ES 색인 API 응답 스키마."""

    document_id: str
    user_id: str
    total_chunks: int
    indexed_chunks: list[IndexedChunkItem]
    request_id: str


def get_chunk_index_use_case() -> ChunkAndIndexUseCase:
    """Dependency placeholder — overridden in create_app()."""
    raise NotImplementedError("ChunkAndIndexUseCase not initialized")


@router.post("/upload", response_model=ChunkIndexAPIResponse)
async def chunk_and_index(
    request: ChunkIndexAPIRequest,
    use_case: ChunkAndIndexUseCase = Depends(get_chunk_index_use_case),
) -> ChunkIndexAPIResponse:
    """텍스트를 청킹하고 키워드를 추출하여 Elasticsearch에 색인한다.

    각 청크에서 빈도 기반 키워드를 추출하여 `keywords` 필드와 함께
    ES에 저장함으로써 BM25 하이브리드 검색의 검색 품질을 높인다.

    Args:
        request: 문서 내용, 청킹 전략, 키워드 옵션 등.
        use_case: 주입된 ChunkAndIndexUseCase.

    Returns:
        색인된 청크 목록과 추출된 키워드.
    """
    if request.strategy_type not in VALID_STRATEGY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"strategy_type must be one of: {sorted(VALID_STRATEGY_TYPES)}",
        )

    request_id = str(uuid.uuid4())
    domain_request = ChunkAndIndexRequest(
        document_id=request.document_id,
        content=request.content,
        user_id=request.user_id,
        strategy_type=request.strategy_type,
        metadata=request.metadata,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        top_keywords=request.top_keywords,
    )
    try:
        result = await use_case.execute(domain_request, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ChunkIndexAPIResponse(
        document_id=result.document_id,
        user_id=result.user_id,
        total_chunks=result.total_chunks,
        indexed_chunks=[
            IndexedChunkItem(
                chunk_id=c.chunk_id,
                chunk_type=c.chunk_type,
                keywords=c.keywords,
                content=c.content,
            )
            for c in result.indexed_chunks
        ],
        request_id=result.request_id,
    )
