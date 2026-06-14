"""웹 검색 필요 판단 LLM 어댑터.

LLM `with_structured_output(WebSearchDecision)`으로 구조화 판단을 받는다.
모든 실패는 보수적으로 needs_web_search=False로 graceful degrade 하여
본 분석 흐름을 막지 않는다. (HallucinationEvaluatorAdapter 패턴 미러링)
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.search_decision.interfaces import SearchDecisionInterface
from src.domain.search_decision.schemas import WebSearchDecision

_SYSTEM = (
    "당신은 데이터 분석 답변이 엑셀 데이터만으로 충분한지 판단하는 라우터입니다.\n"
    "최신 시세/뉴스/외부 통계 등 엑셀에 없는 정보가 답변에 필요하면 "
    "needs_web_search=True 로 판단하세요.\n"
    "엑셀 데이터만으로 답할 수 있으면 False. 애매하면 보수적으로 False."
)
_HUMAN = "[질문]\n{question}\n\n[현재 분석 답변]\n{analysis_text}"


class LLMSearchDecisionAdapter(SearchDecisionInterface):
    """LangChain ChatOpenAI structured output 기반 검색 필요 판단 어댑터."""

    def __init__(
        self,
        logger: LoggerInterface,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ) -> None:
        self._logger = logger
        llm = ChatOpenAI(model=model_name, temperature=temperature)
        prompt = ChatPromptTemplate.from_messages(
            [("system", _SYSTEM), ("human", _HUMAN)]
        )
        self._chain = prompt | llm.with_structured_output(WebSearchDecision)

    async def decide(
        self, question: str, analysis_text: str, request_id: str
    ) -> WebSearchDecision:
        try:
            return await self._chain.ainvoke(
                {"question": question, "analysis_text": analysis_text}
            )
        except Exception as e:
            self._logger.error(
                "search decision failed, fallback=False",
                exception=e,
                request_id=request_id,
            )
            return WebSearchDecision(needs_web_search=False)
