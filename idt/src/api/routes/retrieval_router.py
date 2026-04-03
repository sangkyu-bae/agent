"""Retrieval API endpoints.

Provides document search based on user queries using RAG pipeline.
"""
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.application.retrieval.retrieval_use_case import RetrievalUseCase
from src.domain.retrieval.schemas import RetrievalRequest

router = APIRouter(prefix="/api/v1/retrieval", tags=["retrieval"])


class SearchRequest(BaseModel):
    """Request schema for document search."""

    query: str = Field(..., description="User question for document search")
    user_id: str = Field(..., description="User identifier for filtering")
    top_k: int = Field(default=10, ge=1, le=50, description="Max documents to return")
    document_id: Optional[str] = Field(default=None, description="Filter by document ID")
    use_query_rewrite: bool = Field(default=False, description="Rewrite query before search")
    use_compression: bool = Field(default=True, description="Apply LLM relevance filtering")
    use_parent_context: bool = Field(default=True, description="Include parent document context")


class DocumentItem(BaseModel):
    """Single retrieved document."""

    id: str
    content: str
    score: float
    metadata: Dict[str, str]
    parent_content: Optional[str] = None


class SearchResponse(BaseModel):
    """Response schema for document search."""

    query: str
    rewritten_query: Optional[str]
    documents: List[DocumentItem]
    total_found: int
    request_id: str


def get_retrieval_use_case() -> RetrievalUseCase:
    """Dependency placeholder — overridden in create_app()."""
    raise NotImplementedError("RetrievalUseCase not initialized")


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    use_case: RetrievalUseCase = Depends(get_retrieval_use_case),
) -> SearchResponse:
    """Search documents based on user query.

    Performs vector similarity search with optional:
    - Query rewriting for better results
    - LLM-based relevance compression
    - Parent document context enrichment

    Args:
        request: Search options including query and filters.
        use_case: Injected RetrievalUseCase.

    Returns:
        SearchResponse with matching documents and metadata.
    """
    request_id = str(uuid.uuid4())

    domain_request = RetrievalRequest(
        query=request.query,
        user_id=request.user_id,
        request_id=request_id,
        top_k=request.top_k,
        document_id=request.document_id,
        use_query_rewrite=request.use_query_rewrite,
        use_compression=request.use_compression,
        use_parent_context=request.use_parent_context,
    )

    try:
        result = await use_case.execute(domain_request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return SearchResponse(
        query=result.query,
        rewritten_query=result.rewritten_query,
        documents=[
            DocumentItem(
                id=doc.id,
                content=doc.content,
                score=doc.score,
                metadata=doc.metadata,
                parent_content=doc.parent_content,
            )
            for doc in result.documents
        ],
        total_found=result.total_found,
        request_id=result.request_id,
    )
