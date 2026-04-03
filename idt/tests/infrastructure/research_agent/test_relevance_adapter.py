"""Tests for RelevanceEvaluatorAdapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.research_agent.relevance_adapter import RelevanceEvaluatorAdapter
from src.infrastructure.research_agent.schemas import RelevanceOutput
from src.domain.research_agent.value_objects import RelevanceResult


class TestRelevanceEvaluatorAdapter:
    """Tests for RelevanceEvaluatorAdapter."""

    @pytest.fixture
    def mock_chain(self) -> MagicMock:
        """Create a mock chain."""
        return AsyncMock()

    @pytest.fixture
    def adapter_with_mock(self, mock_chain: MagicMock) -> RelevanceEvaluatorAdapter:
        """Create adapter with mocked chain."""
        with patch("src.infrastructure.research_agent.relevance_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            with patch.object(
                RelevanceEvaluatorAdapter, "_build_chain", return_value=mock_chain
            ):
                adapter = RelevanceEvaluatorAdapter()
                adapter._chain = mock_chain
                return adapter

    async def test_evaluate_returns_relevant(
        self, adapter_with_mock: RelevanceEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should return is_relevant=True when LLM says relevant."""
        mock_chain.ainvoke.return_value = RelevanceOutput(is_relevant=True)

        result = await adapter_with_mock.evaluate(
            question="프랑스의 수도는 어디인가요?",
            answer="프랑스의 수도는 파리입니다.",
            request_id="test-request-123"
        )

        assert isinstance(result, RelevanceResult)
        assert result.is_relevant is True

    async def test_evaluate_returns_not_relevant(
        self, adapter_with_mock: RelevanceEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should return is_relevant=False when LLM says not relevant."""
        mock_chain.ainvoke.return_value = RelevanceOutput(is_relevant=False)

        result = await adapter_with_mock.evaluate(
            question="프랑스의 수도는 어디인가요?",
            answer="오늘 날씨가 좋습니다.",
            request_id="test-request-456"
        )

        assert isinstance(result, RelevanceResult)
        assert result.is_relevant is False

    async def test_evaluate_passes_question_and_answer_to_chain(
        self, adapter_with_mock: RelevanceEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should pass question and answer in correct format."""
        mock_chain.ainvoke.return_value = RelevanceOutput(is_relevant=True)

        await adapter_with_mock.evaluate(
            question="테스트 질문",
            answer="테스트 답변",
            request_id="test-request-789"
        )

        mock_chain.ainvoke.assert_called_once()
        call_args = mock_chain.ainvoke.call_args[0][0]
        assert "question" in call_args
        assert "answer" in call_args
        assert call_args["question"] == "테스트 질문"
        assert call_args["answer"] == "테스트 답변"

    async def test_evaluate_propagates_llm_error(
        self, adapter_with_mock: RelevanceEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should propagate exceptions from LLM."""
        mock_chain.ainvoke.side_effect = Exception("LLM API error")

        with pytest.raises(Exception, match="LLM API error"):
            await adapter_with_mock.evaluate(
                question="질문",
                answer="답변",
                request_id="test-request-error"
            )


class TestRelevanceEvaluatorAdapterInit:
    """Tests for RelevanceEvaluatorAdapter initialization."""

    def test_default_model_name(self) -> None:
        """Adapter should use gpt-4o-mini as default model."""
        with patch("src.infrastructure.research_agent.relevance_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = RelevanceEvaluatorAdapter()
            mock_chat.assert_called_once()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o-mini"

    def test_default_temperature(self) -> None:
        """Adapter should use temperature=0.0 as default."""
        with patch("src.infrastructure.research_agent.relevance_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = RelevanceEvaluatorAdapter()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.0

    def test_custom_model_name(self) -> None:
        """Adapter should accept custom model name."""
        with patch("src.infrastructure.research_agent.relevance_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = RelevanceEvaluatorAdapter(model_name="gpt-4o")
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o"

    def test_custom_temperature(self) -> None:
        """Adapter should accept custom temperature."""
        with patch("src.infrastructure.research_agent.relevance_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = RelevanceEvaluatorAdapter(temperature=0.5)
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.5
