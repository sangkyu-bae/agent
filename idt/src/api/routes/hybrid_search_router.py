"""Hybrid Search API: BM25(ES) + Vector(Qdrant) → RRF 병합 검색."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.application.hybrid_search.use_case import HybridSearchUseCase
from src.domain.hybrid_search.schemas import HybridSearchRequest

router = APIRouter(prefix="/api/v1/hybrid-search", tags=["hybrid-search"])


class HybridSearchAPIRequest(BaseModel):
    """하이브리드 검색 API 요청 스키마."""

    query: str = Field(..., description="검색 쿼리")
    top_k: int = Field(default=10, ge=1, le=50, description="최종 반환 문서 수")
    bm25_top_k: int = Field(default=20, ge=1, le=100, description="BM25 후보 수")
    vector_top_k: int = Field(default=20, ge=1, le=100, description="벡터 검색 후보 수")
    rrf_k: int = Field(default=60, ge=1, description="RRF 상수 k")
    bm25_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="BM25 가중치")
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="벡터 검색 가중치")


class HybridSearchResultItem(BaseModel):
    """단일 검색 결과."""

    id: str
    content: str
    score: float
    bm25_rank: Optional[int]
    bm25_score: Optional[float]
    vector_rank: Optional[int]
    vector_score: Optional[float]
    source: str
    metadata: dict[str, str]


class HybridSearchAPIResponse(BaseModel):
    """하이브리드 검색 API 응답 스키마."""

    query: str
    results: list[HybridSearchResultItem]
    total_found: int
    request_id: str


def get_hybrid_search_use_case() -> HybridSearchUseCase:
    """Dependency placeholder — overridden in create_app()."""
    raise NotImplementedError("HybridSearchUseCase not initialized")


@router.post("/search", response_model=HybridSearchAPIResponse)
async def hybrid_search(
    request: HybridSearchAPIRequest,
    use_case: HybridSearchUseCase = Depends(get_hybrid_search_use_case),
) -> HybridSearchAPIResponse:
    """BM25 + 벡터 검색 하이브리드 검색.

    ES BM25와 Qdrant 벡터 검색 결과를 RRF(Reciprocal Rank Fusion)로 병합하여
    최종 순위를 반환합니다.

    Args:
        request: 검색 쿼리 및 파라미터.
        use_case: 주입된 HybridSearchUseCase.

    Returns:
        RRF 병합된 검색 결과 목록.
    """
    request_id = str(uuid.uuid4())
    domain_request = HybridSearchRequest(
        query=request.query,
        top_k=request.top_k,
        bm25_top_k=request.bm25_top_k,
        vector_top_k=request.vector_top_k,
        rrf_k=request.rrf_k,
        bm25_weight=request.bm25_weight,
        vector_weight=request.vector_weight,
    )
    try:
        result = await use_case.execute(domain_request, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return HybridSearchAPIResponse(
        query=result.query,
        results=[
            HybridSearchResultItem(
                id=r.id,
                content=r.content,
                score=r.score,
                bm25_rank=r.bm25_rank,
                bm25_score=r.bm25_score,
                vector_rank=r.vector_rank,
                vector_score=r.vector_score,
                source=r.source,
                metadata=r.metadata,
            )
            for r in result.results
        ],
        total_found=result.total_found,
        request_id=result.request_id,
    )
