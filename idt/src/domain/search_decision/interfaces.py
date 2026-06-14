"""웹 검색 필요 판단 도메인 포트."""

from abc import ABC, abstractmethod

from src.domain.search_decision.schemas import WebSearchDecision


class SearchDecisionInterface(ABC):
    """웹 검색 필요 판단 포트.

    application 레이어는 이 인터페이스에만 의존하고,
    구체 구현(LLM structured output)은 infrastructure에서 제공한다.
    실패 시 보수적으로 needs_web_search=False를 반환해 본 흐름을 막지 않는다.
    """

    @abstractmethod
    async def decide(
        self, question: str, analysis_text: str, request_id: str
    ) -> WebSearchDecision:
        """질문 + 분석 텍스트로 웹 검색 필요 여부를 판단한다."""
        raise NotImplementedError
