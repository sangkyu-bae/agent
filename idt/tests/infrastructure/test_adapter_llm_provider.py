"""어댑터의 UtilityLLMProviderPort 주입 동작 테스트.

Design Ref: admin-default-llm-routing §8.5 시나리오 A1~A6 + A7.

대상 (패턴 A / B — 생성자에서 chain 을 조립하던 5곳):
    hallucination · search_decision · eval_testset.qa_generator
    intent · prompt_composer

핵심 계약
    A1  llm_provider 미주입  → 기존 ChatOpenAI 경로 (하위호환, FR-9)
    A2  주입 + LLM 반환      → 주입된 LLM 으로 chain 구성
    A3  주입 + None 반환     → 기존 경로로 낙하
    A4  동일 LLM 2회         → chain 재조립 없음 (메모이제이션)
    A5  LLM 객체 변경        → chain 재조립
    A6  chain 명시 주입 우선 → chain > llm_provider > ChatOpenAI (DR-9)
    A7  provider 주입 시     → OPENAI_API_KEY 없이도 생성자가 성공해야 한다
"""
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables import RunnableLambda

from src.domain.llm.interfaces import UtilityLLMProviderPort


@pytest.fixture
def mock_logger() -> MagicMock:
    return MagicMock()


# ── 테스트 더블 ──────────────────────────────────────────────────────────


class FakeLLM:
    """BaseChatModel 스텁. with_structured_output 호출을 기록한다.

    `prompt | llm.with_structured_output(...)` 이 성립해야 하므로 반환값은
    실제 Runnable 이어야 한다 (LangChain 이 __or__ 에서 타입을 검사한다).
    """

    def __init__(self, name: str, response: Any = None) -> None:
        self.name = name
        self.response = response
        self.structured_calls = 0

    def with_structured_output(self, schema: Any, **kwargs: Any) -> RunnableLambda:
        self.structured_calls += 1
        response = self.response
        return RunnableLambda(lambda _payload: response)


class StubProvider(UtilityLLMProviderPort):
    """지정한 LLM 을 순서대로 돌려주는 provider."""

    def __init__(self, *llms: Any) -> None:
        self._llms = list(llms) or [None]
        self.get_calls = 0

    async def get(self, temperature: float = 0.0) -> Any:
        self.get_calls += 1
        idx = min(self.get_calls - 1, len(self._llms) - 1)
        return self._llms[idx]

    async def invalidate(self) -> None:
        return None


@pytest.fixture
def no_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """OPENAI_API_KEY 를 제거해 self-host 전용 환경을 흉내낸다."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)


# ── A7: 키 없는 환경에서의 생성 ──────────────────────────────────────────


class TestNpuOnlyBoot:
    """A7 — OPENAI_API_KEY 가 없어도 provider 주입 시 부팅해야 한다.

    ChatOpenAI 는 생성자에서 자격증명을 검증하고 OpenAIError 를 던진다.
    어댑터가 __init__ 에서 즉시 ChatOpenAI 를 만들면, self-host 전용
    배포(=이 기능의 목표)에서 서버가 부팅조차 못 한다.
    """

    def test_hallucination_constructs_without_openai_key(
        self, no_openai_key: None
    ) -> None:
        from src.infrastructure.hallucination.adapter import (
            HallucinationEvaluatorAdapter,
        )

        HallucinationEvaluatorAdapter(llm_provider=StubProvider(FakeLLM("npu")))

    def test_search_decision_constructs_without_openai_key(
        self, no_openai_key: None, mock_logger: Any
    ) -> None:
        from src.infrastructure.search_decision.adapter import (
            LLMSearchDecisionAdapter,
        )

        LLMSearchDecisionAdapter(
            logger=mock_logger, llm_provider=StubProvider(FakeLLM("npu"))
        )

    def test_intent_constructs_without_openai_key(
        self, no_openai_key: None, mock_logger: Any
    ) -> None:
        from src.infrastructure.intent.adapter import LLMIntentAnalyzerAdapter

        LLMIntentAnalyzerAdapter(
            logger=mock_logger, llm_provider=StubProvider(FakeLLM("npu"))
        )

    def test_prompt_composer_constructs_without_openai_key(
        self, no_openai_key: None, mock_logger: Any
    ) -> None:
        from src.infrastructure.prompt_composer.adapter import (
            LLMPromptGeneratorAdapter,
        )

        LLMPromptGeneratorAdapter(
            logger=mock_logger, llm_provider=StubProvider(FakeLLM("npu"))
        )

    def test_qa_generator_constructs_without_openai_key(
        self, no_openai_key: None
    ) -> None:
        from src.infrastructure.eval_testset.qa_generator import OpenAIQAGenerator

        OpenAIQAGenerator(llm_provider=StubProvider(FakeLLM("npu")))

    def test_eager_chatopenai_still_fails_without_key(
        self, no_openai_key: None
    ) -> None:
        """대조군: provider 미주입 + 키 없음이면 기존대로 실패한다 (동작 불변)."""
        from src.infrastructure.hallucination.adapter import (
            HallucinationEvaluatorAdapter,
        )

        with pytest.raises(Exception):
            HallucinationEvaluatorAdapter()


# ── A1~A5: 해석·메모이제이션 (search_decision 대표) ──────────────────────


class TestSearchDecisionProvider:
    async def test_a1_without_provider_uses_legacy_path(
        self, mock_logger: Any
    ) -> None:
        """A1: 미주입이면 기존 ChatOpenAI 경로를 그대로 쓴다."""
        from src.infrastructure.search_decision.adapter import (
            LLMSearchDecisionAdapter,
        )

        with patch(
            "src.infrastructure.search_decision.adapter.ChatOpenAI"
        ) as mock_cls:
            mock_cls.return_value = FakeLLM("legacy")
            adapter = LLMSearchDecisionAdapter(logger=mock_logger)

        mock_cls.assert_called_once()
        assert adapter._llm_provider is None

    async def test_a2_uses_injected_llm(self, mock_logger: Any) -> None:
        """A2: provider 가 준 LLM 으로 chain 을 만든다."""
        from src.domain.search_decision.schemas import WebSearchDecision
        from src.infrastructure.search_decision.adapter import (
            LLMSearchDecisionAdapter,
        )

        llm = FakeLLM("npu", response=WebSearchDecision(needs_web_search=True))
        adapter = LLMSearchDecisionAdapter(
            logger=mock_logger, llm_provider=StubProvider(llm)
        )

        result = await adapter.decide("q", "a", "req-a2")

        assert result.needs_web_search is True
        assert llm.structured_calls == 1

    async def test_a3_falls_back_when_provider_returns_none(
        self, mock_logger: Any
    ) -> None:
        """A3: provider 가 None 을 주면 기존 경로로 낙하한다."""
        from src.domain.search_decision.schemas import WebSearchDecision
        from src.infrastructure.search_decision.adapter import (
            LLMSearchDecisionAdapter,
        )

        legacy = FakeLLM("legacy", response=WebSearchDecision(needs_web_search=False))
        adapter = LLMSearchDecisionAdapter(
            logger=mock_logger, llm_provider=StubProvider(None)
        )

        with patch(
            "src.infrastructure.search_decision.adapter.ChatOpenAI",
            return_value=legacy,
        ):
            result = await adapter.decide("q", "a", "req-a3")

        assert result.needs_web_search is False
        assert legacy.structured_calls == 1

    async def test_a4_same_llm_reuses_chain(self, mock_logger: Any) -> None:
        """A4: 같은 LLM 객체가 오면 chain 을 재조립하지 않는다."""
        from src.domain.search_decision.schemas import WebSearchDecision
        from src.infrastructure.search_decision.adapter import (
            LLMSearchDecisionAdapter,
        )

        llm = FakeLLM("npu", response=WebSearchDecision(needs_web_search=True))
        adapter = LLMSearchDecisionAdapter(
            logger=mock_logger, llm_provider=StubProvider(llm, llm)
        )

        await adapter.decide("q", "a", "r1")
        await adapter.decide("q", "a", "r2")

        assert llm.structured_calls == 1  # 재조립 없음

    async def test_a5_changed_llm_rebuilds_chain(self, mock_logger: Any) -> None:
        """A5: LLM 객체가 바뀌면 chain 을 재조립한다 (관리자 모델 교체)."""
        from src.domain.search_decision.schemas import WebSearchDecision
        from src.infrastructure.search_decision.adapter import (
            LLMSearchDecisionAdapter,
        )

        old = FakeLLM("old", response=WebSearchDecision(needs_web_search=False))
        new = FakeLLM("new", response=WebSearchDecision(needs_web_search=True))
        adapter = LLMSearchDecisionAdapter(
            logger=mock_logger, llm_provider=StubProvider(old, new)
        )

        first = await adapter.decide("q", "a", "r1")
        second = await adapter.decide("q", "a", "r2")

        assert first.needs_web_search is False
        assert second.needs_web_search is True
        assert old.structured_calls == 1
        assert new.structured_calls == 1


# ── A6: 주입 우선순위 (패턴 B) ───────────────────────────────────────────


class TestExplicitChainWins:
    """A6 — chain 명시 주입은 provider 보다 우선한다 (DR-9).

    기존 테스트가 chain 을 주입해 LLM 호출을 차단하고 있다. provider 가
    이를 덮어쓰면 그 테스트들이 실제 네트워크를 타게 된다.
    """

    async def test_a6_intent_explicit_chain_wins(self, mock_logger: Any) -> None:
        from src.domain.intent.schemas import IntentDraft, IntentSpec, SlotSpec
        from src.infrastructure.intent.adapter import LLMIntentAnalyzerAdapter

        class ExplicitChain:
            def __init__(self) -> None:
                self.calls = 0

            async def ainvoke(self, payload: Any, **kwargs: Any) -> IntentDraft:
                self.calls += 1
                return IntentDraft(label="chat")

        explicit = ExplicitChain()
        provider = StubProvider(FakeLLM("npu"))
        adapter = LLMIntentAnalyzerAdapter(
            logger=mock_logger, chain=explicit, llm_provider=provider
        )

        spec = IntentSpec(slots=[SlotSpec(key="topic", description="주제")])
        await adapter.analyze("hi", spec, request_id="a6")

        assert explicit.calls == 1
        assert provider.get_calls == 0  # provider 를 아예 부르지 않는다
