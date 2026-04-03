"""RAG Agent 도메인 스키마: 순수 Value Object."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RAGAgentRequest:
    """ReAct RAG Agent 질의 요청."""

    query: str
    user_id: str
    top_k: int = 5


@dataclass(frozen=True)
class DocumentSource:
    """검색된 출처 문서 정보."""

    content: str
    source: str       # 출처 파일명 (ES/Qdrant metadata["source"])
    chunk_id: str
    score: float


@dataclass(frozen=True)
class RAGAgentResponse:
    """ReAct RAG Agent 최종 응답."""

    query: str
    answer: str
    sources: list[DocumentSource]
    used_internal_docs: bool
    request_id: str
