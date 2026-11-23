"""Adapter for hallucination evaluation using LLM."""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from src.domain.hallucination.citation_check import CitationCheck, CitationCheckRequest
from src.domain.hallucination.grounding import (
    INTERNAL_LLM_TAG,
    GroundingJudgePort,
    GroundingVerdict,
    HallucinationEvaluatorPort,
    UnsupportedClaim,
)
from src.domain.hallucination.value_objects import HallucinationEvaluationResult
from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.infrastructure.hallucination.prompts import (
    GROUNDING_CITATION_ADDENDUM,
    GROUNDING_CITATION_HUMAN_TEMPLATE,
    GROUNDING_JUDGE_HUMAN_TEMPLATE,
    GROUNDING_JUDGE_SYSTEM_PROMPT,
    HALLUCINATION_EVALUATION_SYSTEM_PROMPT,
    HALLUCINATION_EVALUATION_HUMAN_TEMPLATE,
)
from src.infrastructure.hallucination.schemas import (
    GroundingJudgeOutput,
    GroundingJudgeWithCitationsOutput,
    HallucinationOutput,
)
from src.infrastructure.logging import get_logger


class HallucinationEvaluatorAdapter(HallucinationEvaluatorPort, GroundingJudgePort):
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
        # draft-grounding-check v0.2 §4.3: 근거 판정 체인 캐시 (기존 체인과 분리)
        self._judge_llm: object | None = None
        self._judge_chain = None
        # answer-citation-verification D-04: 인용 검증 확장 체인 캐시
        self._citation_llm: object | None = None
        self._citation_chain = None

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

    # ── draft-grounding-check v0.2 §4.3: 주장 단위 근거 판정 ─────────────

    async def _resolve_judge_chain(self):
        """근거 판정 체인. 관리자 유틸리티 LLM 우선, 없으면 레거시 ChatOpenAI."""
        llm = None
        if self._llm_provider is not None:
            llm = await self._llm_provider.get(self._temperature)
        if llm is None:
            llm = self._llm or ChatOpenAI(model=self._model_name, temperature=self._temperature)
        if llm is not self._judge_llm or self._judge_chain is None:
            prompt = ChatPromptTemplate.from_messages([
                ("system", GROUNDING_JUDGE_SYSTEM_PROMPT),
                ("human", GROUNDING_JUDGE_HUMAN_TEMPLATE),
            ])
            self._judge_llm = llm
            self._judge_chain = prompt | llm.with_structured_output(GroundingJudgeOutput)
        return self._judge_chain

    async def _resolve_citation_chain(self):
        """근거 판정 + 인용 검증 체인 (answer-citation-verification D-04).

        같은 판정 모델·같은 기본 프롬프트에 인용 검증 문단만 덧붙인다.
        """
        llm = None
        if self._llm_provider is not None:
            llm = await self._llm_provider.get(self._temperature)
        if llm is None:
            llm = self._llm or ChatOpenAI(
                model=self._model_name, temperature=self._temperature
            )
        if llm is not self._citation_llm or self._citation_chain is None:
            prompt = ChatPromptTemplate.from_messages([
                ("system", GROUNDING_JUDGE_SYSTEM_PROMPT + GROUNDING_CITATION_ADDENDUM),
                ("human", GROUNDING_CITATION_HUMAN_TEMPLATE),
            ])
            self._citation_llm = llm
            self._citation_chain = prompt | llm.with_structured_output(
                GroundingJudgeWithCitationsOutput
            )
        return self._citation_chain

    async def judge(
        self, *, question: str, sources: str, generation: str,
        hints: list[str], request_id: str,
        citations: CitationCheckRequest | None = None,
    ) -> GroundingVerdict:
        """근거 없는 주장 목록. 실패는 그대로 재발생 — fail-open 은 호출측 몫(D-06).

        루프 안 호출이므로 INTERNAL_LLM_TAG 를 달아 채팅 토큰 스트림에서 뺀다(D-04).
        실패 로깅은 호출측 루프(GroundedGenerator) 한 곳에서 타입·스택만 남긴다
        (Analysis G-2/G-12) — 파싱 오류 메시지에 판정기 원출력이 실릴 수 있다.
        citations 가 비어 있지 않을 때만 인용 검증 확장 체인을 쓴다.
        """
        payload = {
            "question": question,
            "sources": sources,
            "hints": "\n".join(f"- {h}" for h in hints) if hints else "(없음)",
            "generation": generation,
        }
        if citations is not None and not citations.empty:
            return await self._judge_with_citations(payload, citations)
        chain = await self._resolve_judge_chain()
        output: GroundingJudgeOutput = await chain.ainvoke(
            payload, config={"tags": [INTERNAL_LLM_TAG]},
        )
        return GroundingVerdict(unsupported_claims=_claims(output.unsupported_claims))

    async def _judge_with_citations(
        self, payload: dict, citations: CitationCheckRequest
    ) -> GroundingVerdict:
        chain = await self._resolve_citation_chain()
        output: GroundingJudgeWithCitationsOutput = await chain.ainvoke(
            {
                **payload,
                "cited_sources": "\n\n".join(
                    f"[{n}]\n{text}"
                    for n, text in sorted(citations.cited_sources.items())
                ),
                "citations": "\n".join(
                    f"{p.pair_id} | [{p.marker}] | {p.sentence}"
                    for p in citations.pairs
                ),
            },
            config={"tags": [INTERNAL_LLM_TAG]},
        )
        return GroundingVerdict(
            unsupported_claims=_claims(output.unsupported_claims),
            citation_checks=tuple(
                CitationCheck(pair_id=c.id, supported=c.supported, evidence=c.evidence)
                for c in output.citation_checks
            ),
        )


def _claims(items) -> tuple[UnsupportedClaim, ...]:
    return tuple(
        UnsupportedClaim(span=c.span, reason=c.reason, severity=c.severity)
        for c in items
    )
