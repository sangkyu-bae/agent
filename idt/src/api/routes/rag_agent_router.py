"""RAG Agent API: LangGraph ReAct 에이전트 기반 내부 문서 질의응답."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.application.rag_agent.use_case import RAGAgentUseCase
from src.domain.rag_agent.schemas import RAGAgentRequest

router = APIRouter(prefix="/api/v1/rag-agent", tags=["rag-agent"])


class RAGAgentAPIRequest(BaseModel):
    """RAG Agent 질의 API 요청 스키마."""

    query: str = Field(..., min_length=1, description="질의 내용")
    user_id: str = Field(..., description="사용자 ID")
    top_k: int = Field(default=5, ge=1, le=20, description="하이브리드 검색 결과 수")


class DocumentSourceItem(BaseModel):
    """참조 출처 문서 응답."""

    content: str
    source: str       # 출처 파일명 (metadata["source"])
    chunk_id: str
    score: float


class RAGAgentAPIResponse(BaseModel):
    """RAG Agent 응답 스키마."""

    query: str
    answer: str
    sources: list[DocumentSourceItem]
    used_internal_docs: bool
    request_id: str


def get_rag_agent_use_case() -> RAGAgentUseCase:
    """Dependency placeholder — overridden in create_app()."""
    raise NotImplementedError("RAGAgentUseCase not initialized")


@router.post("/query", response_model=RAGAgentAPIResponse)
async def rag_agent_query(
    request: RAGAgentAPIRequest,
    use_case: RAGAgentUseCase = Depends(get_rag_agent_use_case),
) -> RAGAgentAPIResponse:
    """LangGraph ReAct 에이전트 기반 내부 문서 질의응답.

    BM25(ES) + Vector(Qdrant) 5:5 하이브리드 검색으로 관련 문서를 찾고,
    LangChain ChatOpenAI ReAct 에이전트가 내부 문서 필요 여부를 판단하여 답변합니다.
    - 내부 문서가 필요하면: internal_document_search 도구 호출 → 관련 문서 검색 → 답변 생성
    - 내부 문서가 불필요하면: 직접 답변 생성

    Args:
        request: 질의 내용, 사용자 ID, 검색 결과 수.
        use_case: 주입된 RAGAgentUseCase.

    Returns:
        LLM 생성 답변 + 참조 출처 문서 목록 + 내부 문서 사용 여부.
    """
    request_id = str(uuid.uuid4())
    domain_request = RAGAgentRequest(
        query=request.query,
        user_id=request.user_id,
        top_k=request.top_k,
    )
    try:
        result = await use_case.execute(domain_request, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return RAGAgentAPIResponse(
        query=result.query,
        answer=result.answer,
        sources=[
            DocumentSourceItem(
                content=s.content,
                source=s.source,
                chunk_id=s.chunk_id,
                score=s.score,
            )
            for s in result.sources
        ],
        used_internal_docs=result.used_internal_docs,
        request_id=result.request_id,
    )
