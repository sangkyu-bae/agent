"""Tests for HallucinationEvaluatorAdapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter
from src.infrastructure.hallucination.schemas import HallucinationOutput
from src.domain.hallucination.value_objects import HallucinationEvaluationResult


class TestHallucinationEvaluatorAdapter:
    """Tests for HallucinationEvaluatorAdapter."""

    @pytest.fixture
    def mock_chain(self) -> MagicMock:
        """Create a mock chain."""
        return AsyncMock()

    @pytest.fixture
    def adapter_with_mock(self, mock_chain: MagicMock) -> HallucinationEvaluatorAdapter:
        """Create adapter with mocked chain."""
        with patch("src.infrastructure.hallucination.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            with patch.object(HallucinationEvaluatorAdapter, "_build_chain", return_value=mock_chain):
                adapter = HallucinationEvaluatorAdapter()
                adapter._chain = mock_chain
                return adapter

    async def test_evaluate_returns_not_hallucinated(
        self, adapter_with_mock: HallucinationEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should return is_hallucinated=False when LLM says not hallucinated."""
        mock_chain.ainvoke.return_value = HallucinationOutput(is_hallucinated=False)

        result = await adapter_with_mock.evaluate(
            documents=["The capital of France is Paris."],
            generation="Paris is the capital of France.",
            request_id="test-request-123"
        )

        assert isinstance(result, HallucinationEvaluationResult)
        assert result.is_hallucinated is False

    async def test_evaluate_returns_hallucinated(
        self, adapter_with_mock: HallucinationEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should return is_hallucinated=True when LLM detects hallucination."""
        mock_chain.ainvoke.return_value = HallucinationOutput(is_hallucinated=True)

        result = await adapter_with_mock.evaluate(
            documents=["The capital of France is Paris."],
            generation="Berlin is the capital of France.",
            request_id="test-request-456"
        )

        assert isinstance(result, HallucinationEvaluationResult)
        assert result.is_hallucinated is True

    async def test_evaluate_joins_multiple_documents(
        self, adapter_with_mock: HallucinationEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should join multiple documents with '---' separator."""
        mock_chain.ainvoke.return_value = HallucinationOutput(is_hallucinated=False)

        await adapter_with_mock.evaluate(
            documents=["Document 1 content.", "Document 2 content.", "Document 3 content."],
            generation="Some answer.",
            request_id="test-request-789"
        )

        call_args = mock_chain.ainvoke.call_args[0][0]
        assert "Document 1 content." in call_args["documents"]
        assert "Document 2 content." in call_args["documents"]
        assert "Document 3 content." in call_args["documents"]
        assert "---" in call_args["documents"]

    async def test_evaluate_propagates_llm_error(
        self, adapter_with_mock: HallucinationEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should propagate exceptions from LLM."""
        mock_chain.ainvoke.side_effect = Exception("LLM API error")

        with pytest.raises(Exception, match="LLM API error"):
            await adapter_with_mock.evaluate(
                documents=["Some document."],
                generation="Some answer.",
                request_id="test-request-error"
            )

    async def test_evaluate_passes_correct_input_format(
        self, adapter_with_mock: HallucinationEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should pass documents and generation in correct format."""
        mock_chain.ainvoke.return_value = HallucinationOutput(is_hallucinated=False)

        await adapter_with_mock.evaluate(
            documents=["Reference doc."],
            generation="Generated answer.",
            request_id="test-request-format"
        )

        mock_chain.ainvoke.assert_called_once()
        call_args = mock_chain.ainvoke.call_args[0][0]
        assert "documents" in call_args
        assert "generation" in call_args
        assert call_args["generation"] == "Generated answer."


class TestHallucinationEvaluatorAdapterInit:
    """Tests for HallucinationEvaluatorAdapter initialization."""

    def test_default_model_name(self) -> None:
        """Adapter should use gpt-4o-mini as default model."""
        with patch("src.infrastructure.hallucination.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = HallucinationEvaluatorAdapter()
            mock_chat.assert_called_once()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o-mini"

    def test_default_temperature(self) -> None:
        """Adapter should use temperature=0.0 as default."""
        with patch("src.infrastructure.hallucination.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = HallucinationEvaluatorAdapter()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.0

    def test_custom_model_name(self) -> None:
        """Adapter should accept custom model name."""
        with patch("src.infrastructure.hallucination.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = HallucinationEvaluatorAdapter(model_name="gpt-4o")
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o"

    def test_custom_temperature(self) -> None:
        """Adapter should accept custom temperature."""
        with patch("src.infrastructure.hallucination.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = HallucinationEvaluatorAdapter(temperature=0.5)
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.5
