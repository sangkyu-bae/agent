"""Adapter for hallucination evaluation using LLM."""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from src.domain.hallucination.value_objects import HallucinationEvaluationResult
from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.infrastructure.hallucination.prompts import (
    HALLUCINATION_EVALUATION_SYSTEM_PROMPT,
    HALLUCINATION_EVALUATION_HUMAN_TEMPLATE,
)
from src.infrastructure.hallucination.schemas import HallucinationOutput
from src.infrastructure.logging import get_logger


class HallucinationEvaluatorAdapter:
    """Adapter for evaluating hallucination using LLM with structured output.

    Uses ChatOpenAI with structured output to determine if an LLM generation
    is grounded in the provided reference documents.
    """

    DOCUMENT_SEPARATOR = "\n---\n"

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        llm_provider: UtilityLLMProviderPort | None = None,
    ) -> None:
        """Initialize the hallucination evaluator adapter.

        Args:
            model_name: The OpenAI model to use for evaluation.
            temperature: Temperature setting for the LLM (0.0 for deterministic output).
            llm_provider: 관리자 설정 LLM 공급자. 주입 시 호출 시점마다 해석한다
                (admin-default-llm-routing AD-2). 미주입이면 기존 동작 유지.
        """
        self._logger = get_logger(__name__)
        self._model_name = model_name
        self._temperature = temperature
        # A7: provider 주입 시 ChatOpenAI 를 즉시 만들지 않는다 —
        # OPENAI_API_KEY 없는 self-host 전용 배포에서 생성자가 죽는다.
        self._llm_provider = llm_provider
        self._llm = None
        self._chain = None if llm_provider is not None else self._build_chain()
        self._cached_llm: object | None = None
        self._cached_chain = None

    def _build_chain_from(self, llm):
        """Build the LangChain chain for hallucination evaluation."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", HALLUCINATION_EVALUATION_SYSTEM_PROMPT),
            ("human", HALLUCINATION_EVALUATION_HUMAN_TEMPLATE),
        ])
        return prompt | llm.with_structured_output(HallucinationOutput)

    def _build_chain(self):
        """기존(레거시) ChatOpenAI 경로. 하위호환 유지용."""
        self._llm = ChatOpenAI(
            model=self._model_name, temperature=self._temperature
        )
        return self._build_chain_from(self._llm)

    async def _resolve_chain(self):
        """호출 시점에 유효한 chain. 우선순위: llm_provider > ChatOpenAI (DR-9)."""
        if self._llm_provider is not None:
            llm = await self._llm_provider.get(self._temperature)
            if llm is not None:
                if llm is not self._cached_llm:
                    self._cached_llm = llm
                    self._cached_chain = self._build_chain_from(llm)
                return self._cached_chain
        if self._chain is None:
            self._chain = self._build_chain()
        return self._chain

    async def evaluate(
        self,
        documents: list[str],
        generation: str,
        request_id: str
    ) -> HallucinationEvaluationResult:
        """Evaluate if a generation is hallucinated.

        Args:
            documents: List of reference documents to check against.
            generation: The LLM-generated text to evaluate.
            request_id: Request ID for logging context.

        Returns:
            HallucinationEvaluationResult with is_hallucinated field.

        Raises:
            Exception: If LLM API call fails.
        """
        joined_documents = self.DOCUMENT_SEPARATOR.join(documents)

        try:
            chain = await self._resolve_chain()
            output: HallucinationOutput = await chain.ainvoke({
                "documents": joined_documents,
                "generation": generation,
            })
            return HallucinationEvaluationResult(is_hallucinated=output.is_hallucinated)
        except Exception as e:
            self._logger.error(
                "Hallucination evaluation failed",
                exception=e,
                request_id=request_id
            )
            raise
