"""Morph-Index API: Kiwi 형태소 분석 + Qdrant + ES 이중 색인."""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.application.morph_index.use_case import MorphAndDualIndexUseCase
from src.domain.morph_index.schemas import MorphIndexRequest

router = APIRouter(prefix="/api/v1/morph-index", tags=["morph-index"])

VALID_STRATEGY_TYPES = {"full_token", "parent_child", "semantic"}


class MorphIndexAPIRequest(BaseModel):
    """Kiwi 형태소 이중 색인 API 요청 스키마."""

    document_id: str = Field(..., description="문서 고유 ID")
    content: str = Field(..., description="청킹할 텍스트 내용")
    user_id: str = Field(..., description="사용자 ID")
    strategy_type: str = Field(default="parent_child", description="청킹 전략")
    chunk_size: int = Field(default=500, ge=100, description="청크 크기 (토큰)")
    chunk_overlap: int = Field(default=50, ge=0, description="청크 오버랩 (토큰)")
    source: str = Field(default="", description="원본 파일명 / 출처")
    metadata: dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터")


class DualIndexedChunkItem(BaseModel):
    """단일 이중 색인 청크 응답."""

    chunk_id: str
    chunk_type: str
    morph_keywords: list[str]
    content: str
    char_start: int
    char_end: int
    chunk_index: int


class MorphIndexAPIResponse(BaseModel):
    """Kiwi 형태소 이중 색인 API 응답 스키마."""

    document_id: str
    user_id: str
    total_chunks: int
    qdrant_indexed: int
    es_indexed: int
    indexed_chunks: list[DualIndexedChunkItem]
    request_id: str


def get_morph_index_use_case() -> MorphAndDualIndexUseCase:
    """Dependency placeholder — overridden in create_app()."""
    raise NotImplementedError("MorphAndDualIndexUseCase not initialized")


@router.post("/upload", response_model=MorphIndexAPIResponse)
async def morph_and_dual_index(
    request: MorphIndexAPIRequest,
    use_case: MorphAndDualIndexUseCase = Depends(get_morph_index_use_case),
) -> MorphIndexAPIResponse:
    """텍스트를 청킹하고 Kiwi 형태소 분석 후 Qdrant + ES에 이중 색인한다.

    - Qdrant: 청크 임베딩 + 전체 메타데이터(위치, 형태소 키워드 포함)
    - ES: 청크 텍스트 + NNG/NNP/VV원형/VA원형 형태소 키워드 + 문서 내 위치

    Args:
        request: 문서 내용, 청킹 전략, 출처 등.
        use_case: 주입된 MorphAndDualIndexUseCase.

    Returns:
        이중 색인된 청크 목록 (Qdrant + ES 색인 수 포함).
    """
    if request.strategy_type not in VALID_STRATEGY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"strategy_type must be one of: {sorted(VALID_STRATEGY_TYPES)}",
        )

    request_id = str(uuid.uuid4())
    domain_request = MorphIndexRequest(
        document_id=request.document_id,
        content=request.content,
        user_id=request.user_id,
        strategy_type=request.strategy_type,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        source=request.source,
        metadata=request.metadata,
    )
    try:
        result = await use_case.execute(domain_request, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return MorphIndexAPIResponse(
        document_id=result.document_id,
        user_id=result.user_id,
        total_chunks=result.total_chunks,
        qdrant_indexed=result.qdrant_indexed,
        es_indexed=result.es_indexed,
        indexed_chunks=[
            DualIndexedChunkItem(
                chunk_id=c.chunk_id,
                chunk_type=c.chunk_type,
                morph_keywords=c.morph_keywords,
                content=c.content,
                char_start=c.char_start,
                char_end=c.char_end,
                chunk_index=c.chunk_index,
            )
            for c in result.indexed_chunks
        ],
        request_id=result.request_id,
    )
