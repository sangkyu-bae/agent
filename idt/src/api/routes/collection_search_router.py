import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.application.collection_search.use_case import (
    CollectionNotFoundError,
    CollectionSearchUseCase,
)
from src.application.collection_search.search_history_use_case import (
    SearchHistoryUseCase,
)
from src.domain.auth.entities import User
from src.domain.collection_search.schemas import CollectionSearchRequest
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(
    prefix="/api/v1/collections",
    tags=["collection-search"],
)


class CollectionSearchAPIRequest(BaseModel):
    query: str = Field(..., min_length=1, description="검색 쿼리")
    top_k: int = Field(default=10, ge=1, le=50)
    bm25_top_k: int = Field(default=20, ge=1, le=100)
    vector_top_k: int = Field(default=20, ge=1, le=100)
    rrf_k: int = Field(default=60, ge=1)
    bm25_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0)


class SearchResultItem(BaseModel):
    id: str
    content: str
    score: float
    bm25_rank: Optional[int]
    bm25_score: Optional[float]
    vector_rank: Optional[int]
    vector_score: Optional[float]
    source: str
    metadata: dict[str, str]


class CollectionSearchAPIResponse(BaseModel):
    query: str
    collection_name: str
    results: list[SearchResultItem]
    total_found: int
    bm25_weight: float
    vector_weight: float
    request_id: str
    document_id: Optional[str] = None


class SearchHistoryItem(BaseModel):
    id: int
    query: str
    document_id: Optional[str]
    bm25_weight: float
    vector_weight: float
    top_k: int
    result_count: int
    created_at: str


class SearchHistoryAPIResponse(BaseModel):
    collection_name: str
    histories: list[SearchHistoryItem]
    total: int
    limit: int
    offset: int


def get_collection_search_use_case() -> CollectionSearchUseCase:
    raise NotImplementedError


def get_search_history_use_case() -> SearchHistoryUseCase:
    raise NotImplementedError


@router.post(
    "/{collection_name}/search",
    response_model=CollectionSearchAPIResponse,
)
async def search_in_collection(
    collection_name: str,
    request: CollectionSearchAPIRequest,
    current_user: User = Depends(get_current_user),
    use_case: CollectionSearchUseCase = Depends(get_collection_search_use_case),
) -> CollectionSearchAPIResponse:
    request_id = str(uuid.uuid4())
    domain_request = CollectionSearchRequest(
        collection_name=collection_name,
        query=request.query,
        top_k=request.top_k,
        bm25_top_k=request.bm25_top_k,
        vector_top_k=request.vector_top_k,
        rrf_k=request.rrf_k,
        bm25_weight=request.bm25_weight,
        vector_weight=request.vector_weight,
    )
    try:
        result = await use_case.execute(domain_request, current_user, request_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="No read access")
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Collection not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return _to_api_response(result)


@router.post(
    "/{collection_name}/documents/{document_id}/search",
    response_model=CollectionSearchAPIResponse,
)
async def search_in_document(
    collection_name: str,
    document_id: str,
    request: CollectionSearchAPIRequest,
    current_user: User = Depends(get_current_user),
    use_case: CollectionSearchUseCase = Depends(get_collection_search_use_case),
) -> CollectionSearchAPIResponse:
    request_id = str(uuid.uuid4())
    domain_request = CollectionSearchRequest(
        collection_name=collection_name,
        query=request.query,
        top_k=request.top_k,
        bm25_top_k=request.bm25_top_k,
        vector_top_k=request.vector_top_k,
        rrf_k=request.rrf_k,
        bm25_weight=request.bm25_weight,
        vector_weight=request.vector_weight,
        document_id=document_id,
    )
    try:
        result = await use_case.execute(domain_request, current_user, request_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="No read access")
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Collection not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return _to_api_response(result)


@router.get(
    "/{collection_name}/search-history",
    response_model=SearchHistoryAPIResponse,
)
async def get_search_history(
    collection_name: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    use_case: SearchHistoryUseCase = Depends(get_search_history_use_case),
) -> SearchHistoryAPIResponse:
    request_id = str(uuid.uuid4())
    result = await use_case.execute(
        user_id=str(current_user.id),
        collection_name=collection_name,
        limit=limit,
        offset=offset,
        request_id=request_id,
    )
    return SearchHistoryAPIResponse(
        collection_name=result.collection_name,
        histories=[
            SearchHistoryItem(
                id=h.id,
                query=h.query,
                document_id=h.document_id,
                bm25_weight=h.bm25_weight,
                vector_weight=h.vector_weight,
                top_k=h.top_k,
                result_count=h.result_count,
                created_at=h.created_at.isoformat(),
            )
            for h in result.histories
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


def _to_api_response(result) -> CollectionSearchAPIResponse:
    return CollectionSearchAPIResponse(
        query=result.query,
        collection_name=result.collection_name,
        results=[
            SearchResultItem(
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
        bm25_weight=result.bm25_weight,
        vector_weight=result.vector_weight,
        request_id=result.request_id,
        document_id=result.document_id,
    )
