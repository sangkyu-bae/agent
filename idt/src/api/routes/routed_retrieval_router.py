"""Routed Retrieval API — 3계층 하강 라우팅 검색 (summary-routed-retrieval Design D7).

질의 → 문서 요약(1차) → 섹션 요약(2차, 벡터+BM25 RRF) → 조(parent) 본문(3차).
응답에 라우팅 근거·폴백 관측 필드를 동봉한다(튜닝/RAGAS 입력).
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.application.routed_retrieval.use_case import RoutedRetrievalUseCase
from src.domain.routed_retrieval.schemas import (
    RoutedChunk,
    RoutedParams,
    RoutedScope,
)

router = APIRouter(prefix="/api/v1/retrieval", tags=["retrieval"])


def get_routed_retrieval_use_case() -> RoutedRetrievalUseCase:
    """Dependency placeholder — overridden in create_app()."""
    raise NotImplementedError("RoutedRetrievalUseCase not initialized")


# ── Schemas ──────────────────────────────────────────────────────

class RoutedSearchAPIRequest(BaseModel):
    query: str = Field(..., description="검색 쿼리")
    collection_name: Optional[str] = Field(
        default=None, description="대상 컬렉션 (None=기본 컬렉션)"
    )
    kb_id: Optional[str] = Field(default=None, description="지식베이스 격리 필터")
    doc_top_k: int = Field(default=5, ge=1, le=20, description="1차 문서 후보 수")
    section_top_k: int = Field(
        default=10, ge=1, le=50, description="2차 섹션 후보 수"
    )
    top_k: int = Field(default=5, ge=1, le=30, description="최종 반환 수")
    rrf_k: int = Field(default=60, ge=1, description="RRF 상수 k")
    bm25_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0)


class RoutedDocumentEvidence(BaseModel):
    summary: str
    score: float
    filename: str
    keywords: list[str]


class RoutedSectionEvidence(BaseModel):
    summary: str
    clause_title: str
    keywords: list[str]
    score: float
    vector_rank: Optional[int]
    bm25_rank: Optional[int]
    source: str


class RoutedResultItem(BaseModel):
    content: str
    section_ref: str
    document_id: str
    clause_title: str
    score: float
    from_fallback: bool
    document: Optional[RoutedDocumentEvidence] = None
    section: Optional[RoutedSectionEvidence] = None


class RoutedSearchAPIResponse(BaseModel):
    query: str
    results: list[RoutedResultItem]
    total_found: int
    fallback_used: bool
    fallback_count: int
    document_candidates: int
    section_candidates: int
    request_id: str


def _to_item(chunk: RoutedChunk) -> RoutedResultItem:
    document = (
        RoutedDocumentEvidence(
            summary=chunk.document.summary,
            score=chunk.document.score,
            filename=chunk.document.filename,
            keywords=chunk.document.keywords,
        )
        if chunk.document is not None
        else None
    )
    section = (
        RoutedSectionEvidence(
            summary=chunk.section.summary,
            clause_title=chunk.section.clause_title,
            keywords=chunk.section.keywords,
            score=chunk.section.score,
            vector_rank=chunk.section.vector_rank,
            bm25_rank=chunk.section.bm25_rank,
            source=chunk.section.source,
        )
        if chunk.section is not None
        else None
    )
    return RoutedResultItem(
        content=chunk.content,
        section_ref=chunk.section_ref,
        document_id=chunk.document_id,
        clause_title=chunk.clause_title,
        score=chunk.score,
        from_fallback=chunk.from_fallback,
        document=document,
        section=section,
    )


@router.post(
    "/routed",
    response_model=RoutedSearchAPIResponse,
    description=(
        "3계층 하강 라우팅 검색: 문서 요약(1차 벡터) → 섹션 요약(2차 벡터+BM25 RRF) "
        "→ 조(parent) 본문 확장. 결과가 top_k 미만이면 기존 하이브리드 검색으로 "
        "보충한다(fallback_used). 요약 벡터는 업로드 시 기본 임베딩 모델로 생성되므로 "
        "검색 기본 임베딩 모델과 동일해야 한다 (summary-routed-retrieval D9)."
    ),
)
async def routed_search(
    request: RoutedSearchAPIRequest,
    use_case: RoutedRetrievalUseCase = Depends(get_routed_retrieval_use_case),
) -> RoutedSearchAPIResponse:
    request_id = str(uuid.uuid4())
    scope = RoutedScope(
        collection_name=request.collection_name, kb_id=request.kb_id
    )
    params = RoutedParams(
        doc_top_k=request.doc_top_k,
        section_top_n=request.section_top_k,
        top_k=request.top_k,
        rrf_k=request.rrf_k,
        bm25_weight=request.bm25_weight,
        vector_weight=request.vector_weight,
    )
    try:
        result = await use_case.execute(request.query, scope, params, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return RoutedSearchAPIResponse(
        query=result.query,
        results=[_to_item(chunk) for chunk in result.results],
        total_found=len(result.results),
        fallback_used=result.fallback_used,
        fallback_count=result.fallback_count,
        document_candidates=result.document_candidates,
        section_candidates=result.section_candidates,
        request_id=result.request_id,
    )
