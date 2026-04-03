"""InternalDocumentSearchTool: 내부 문서 BM25 + Vector 5:5 하이브리드 검색 LangChain 도구."""
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import ConfigDict, Field

from src.domain.hybrid_search.schemas import HybridSearchRequest
from src.domain.rag_agent.schemas import DocumentSource


class InternalDocumentSearchTool(BaseTool):
    """MORPH-IDX-001 색인 문서 대상 BM25(ES) + Vector(Qdrant) 5:5 하이브리드 검색 도구.

    LangGraph ReAct 에이전트에서 사용. 질문과 관련된 내부 문서를 검색하여
    출처(source) 메타데이터와 함께 반환한다.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "internal_document_search"
    description: str = (
        "내부 문서에서 관련 정보를 검색합니다. "
        "질문에 대한 내부 문서 정보가 필요할 때 사용하세요. "
        "입력은 검색할 한국어 쿼리 문자열입니다."
    )

    hybrid_search_use_case: Any
    top_k: int = 5
    request_id: str = ""
    collected_sources: list[DocumentSource] = Field(default_factory=list)

    def _run(self, query: str) -> str:
        raise NotImplementedError("비동기 _arun을 사용하세요.")

    async def _arun(self, query: str) -> str:
        """BM25(ES) + Vector(Qdrant) 5:5 하이브리드 검색 실행.

        bm25_top_k == vector_top_k 로 설정하여 동등 가중치(5:5) 보장.
        """
        request = HybridSearchRequest(
            query=query,
            top_k=self.top_k,
            bm25_top_k=self.top_k * 2,
            vector_top_k=self.top_k * 2,
            rrf_k=60,
        )
        result = await self.hybrid_search_use_case.execute(request, self.request_id)

        if not result.results:
            return "관련 내부 문서를 찾지 못했습니다."

        lines: list[str] = []
        for hit in result.results:
            source = hit.metadata.get("source", "unknown")
            self.collected_sources.append(
                DocumentSource(
                    content=hit.content,
                    source=source,
                    chunk_id=hit.id,
                    score=hit.score,
                )
            )
            lines.append(f"[출처: {source}]\n{hit.content}")

        return "\n\n".join(lines)
