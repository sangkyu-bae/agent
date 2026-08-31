"""웹 검색 필요 판단 LLM 어댑터.

LLM `with_structured_output(WebSearchDecision)`으로 구조화 판단을 받는다.
모든 실패는 보수적으로 needs_web_search=False로 graceful degrade 하여
본 분석 흐름을 막지 않는다. (HallucinationEvaluatorAdapter 패턴 미러링)
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.domain.llm.interfaces import UtilityLLMProviderPort
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
        llm_provider: UtilityLLMProviderPort | None = None,
    ) -> None:
        self._logger = logger
        self._model_name = model_name
        self._temperature = temperature
        # admin-default-llm-routing AD-2 / A7: provider 주입 시 ChatOpenAI 를
        # 즉시 만들지 않는다 — OPENAI_API_KEY 가 없는 self-host 전용 배포에서
        # 생성자가 OpenAIError 로 죽기 때문이다. 폴백 시점에 지연 생성한다.
        self._llm_provider = llm_provider
        self._chain = None if llm_provider is not None else self._build_legacy_chain()
        self._cached_llm: object | None = None
        self._cached_chain = None

    def _build_chain_from(self, llm):
        prompt = ChatPromptTemplate.from_messages(
            [("system", _SYSTEM), ("human", _HUMAN)]
        )
        return prompt | llm.with_structured_output(WebSearchDecision)

    def _build_legacy_chain(self):
        return self._build_chain_from(
            ChatOpenAI(model=self._model_name, temperature=self._temperature)
        )

    async def _resolve_chain(self):
        """호출 시점에 유효한 chain. DR-9 우선순위: llm_provider > ChatOpenAI."""
        if self._llm_provider is not None:
            llm = await self._llm_provider.get(self._temperature)
            if llm is not None:
                if llm is not self._cached_llm:
                    self._cached_llm = llm
                    self._cached_chain = self._build_chain_from(llm)
                return self._cached_chain
        if self._chain is None:
            self._chain = self._build_legacy_chain()
        return self._chain

    async def decide(
        self, question: str, analysis_text: str, request_id: str
    ) -> WebSearchDecision:
        try:
            chain = await self._resolve_chain()
            return await chain.ainvoke(
                {"question": question, "analysis_text": analysis_text}
            )
        except Exception as e:
            self._logger.error(
                "search decision failed, fallback=False",
                exception=e,
                request_id=request_id,
            )
            return WebSearchDecision(needs_web_search=False)
