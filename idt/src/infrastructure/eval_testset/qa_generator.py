"""문서→QA 쌍 생성 LLM 어댑터 (eval-hub Design A6).

hallucination adapter 패턴: ChatOpenAI + with_structured_output.
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.infrastructure.logging import get_logger

_SYSTEM_PROMPT = (
    "당신은 문서 기반 QA 평가 데이터셋 생성 전문가입니다. "
    "주어진 문서 내용에서만 답할 수 있는 질문-정답 쌍을 만드세요.\n"
    "규칙:\n"
    "- 질문은 문서를 읽지 않은 사용자가 실제로 물어볼 법한 자연스러운 한국어 문장\n"
    "- 정답(ground_truth)은 문서 내용만 근거로 작성하고, 문서에 없는 내용을 지어내지 않는다\n"
    "- 서로 다른 주제를 다루도록 다양하게 생성한다\n"
    "- 정확히 {max_pairs}개 이하로 생성한다"
)

_HUMAN_TEMPLATE = "문서 내용:\n---\n{text}\n---\n위 문서에서 QA 쌍을 생성하세요."


class _QAPair(BaseModel):
    question: str = Field(description="문서 기반 질문")
    ground_truth: str = Field(description="문서 근거 정답")


class _QADraft(BaseModel):
    pairs: list[_QAPair] = Field(description="생성된 QA 쌍 목록")


class OpenAIQAGenerator:
    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.2,
        llm_provider: UtilityLLMProviderPort | None = None,
    ) -> None:
        self._logger = get_logger(__name__)
        self._model_name = model_name
        self._temperature = temperature
        # A7: provider 주입 시 ChatOpenAI 지연 생성 (키 없는 배포 대비).
        self._llm_provider = llm_provider
        self._chain = None if llm_provider is not None else self._build_legacy_chain()
        self._cached_llm: object | None = None
        self._cached_chain = None

    def _build_chain_from(self, llm):
        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_PROMPT),
            ("human", _HUMAN_TEMPLATE),
        ])
        return prompt | llm.with_structured_output(_QADraft)

    def _build_legacy_chain(self):
        return self._build_chain_from(
            ChatOpenAI(model=self._model_name, temperature=self._temperature)
        )

    async def _resolve_chain(self):
        """호출 시점에 유효한 chain (DR-9)."""
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

    async def generate(
        self, text: str, max_pairs: int, request_id: str
    ) -> list[dict]:
        self._logger.info(
            "QA draft generation start",
            request_id=request_id,
            text_chars=len(text),
            max_pairs=max_pairs,
        )
        try:
            chain = await self._resolve_chain()
            draft: _QADraft = await chain.ainvoke(
                {"text": text, "max_pairs": max_pairs}
            )
        except Exception:
            self._logger.exception(
                "QA draft generation failed", request_id=request_id
            )
            raise
        pairs = [
            {"question": p.question, "ground_truth": p.ground_truth}
            for p in draft.pairs[:max_pairs]
        ]
        self._logger.info(
            "QA draft generation done", request_id=request_id, count=len(pairs)
        )
        return pairs
