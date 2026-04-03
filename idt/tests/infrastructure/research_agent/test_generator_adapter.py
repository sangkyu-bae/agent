"""Tests for GeneratorAdapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.research_agent.generator_adapter import GeneratorAdapter


class TestGeneratorAdapter:
    """Tests for GeneratorAdapter."""

    @pytest.fixture
    def mock_chain(self) -> MagicMock:
        """Create a mock chain."""
        return AsyncMock()

    @pytest.fixture
    def adapter_with_mock(self, mock_chain: MagicMock) -> GeneratorAdapter:
        """Create adapter with mocked chain."""
        with patch("src.infrastructure.research_agent.generator_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            with patch.object(GeneratorAdapter, "_build_chain", return_value=mock_chain):
                adapter = GeneratorAdapter()
                adapter._chain = mock_chain
                return adapter

    async def test_generate_returns_string(
        self, adapter_with_mock: GeneratorAdapter, mock_chain: MagicMock
    ) -> None:
        """Generate should return a string answer."""
        mock_response = MagicMock()
        mock_response.content = "프랑스의 수도는 파리입니다."
        mock_chain.ainvoke.return_value = mock_response

        result = await adapter_with_mock.generate(
            question="프랑스의 수도는 어디인가요?",
            context="프랑스는 유럽에 있는 나라입니다. 수도는 파리입니다.",
            request_id="test-request-123"
        )

        assert isinstance(result, str)
        assert result == "프랑스의 수도는 파리입니다."

    async def test_generate_passes_question_and_context_to_chain(
        self, adapter_with_mock: GeneratorAdapter, mock_chain: MagicMock
    ) -> None:
        """Generate should pass question and context in correct format."""
        mock_response = MagicMock()
        mock_response.content = "답변입니다."
        mock_chain.ainvoke.return_value = mock_response

        await adapter_with_mock.generate(
            question="테스트 질문",
            context="테스트 컨텍스트",
            request_id="test-request-789"
        )

        mock_chain.ainvoke.assert_called_once()
        call_args = mock_chain.ainvoke.call_args[0][0]
        assert "question" in call_args
        assert "context" in call_args
        assert call_args["question"] == "테스트 질문"
        assert call_args["context"] == "테스트 컨텍스트"

    async def test_generate_propagates_llm_error(
        self, adapter_with_mock: GeneratorAdapter, mock_chain: MagicMock
    ) -> None:
        """Generate should propagate exceptions from LLM."""
        mock_chain.ainvoke.side_effect = Exception("LLM API error")

        with pytest.raises(Exception, match="LLM API error"):
            await adapter_with_mock.generate(
                question="질문",
                context="컨텍스트",
                request_id="test-request-error"
            )

    async def test_generate_handles_empty_context(
        self, adapter_with_mock: GeneratorAdapter, mock_chain: MagicMock
    ) -> None:
        """Generate should handle empty context."""
        mock_response = MagicMock()
        mock_response.content = "컨텍스트가 없어 답변을 드릴 수 없습니다."
        mock_chain.ainvoke.return_value = mock_response

        result = await adapter_with_mock.generate(
            question="질문",
            context="",
            request_id="test-request-empty"
        )

        assert isinstance(result, str)


class TestGeneratorAdapterInit:
    """Tests for GeneratorAdapter initialization."""

    def test_default_model_name(self) -> None:
        """Adapter should use gpt-4o-mini as default model."""
        with patch("src.infrastructure.research_agent.generator_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = GeneratorAdapter()
            mock_chat.assert_called_once()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o-mini"

    def test_default_temperature(self) -> None:
        """Adapter should use temperature=0.0 as default."""
        with patch("src.infrastructure.research_agent.generator_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = GeneratorAdapter()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.0

    def test_custom_model_name(self) -> None:
        """Adapter should accept custom model name."""
        with patch("src.infrastructure.research_agent.generator_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = GeneratorAdapter(model_name="gpt-4o")
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o"

    def test_custom_temperature(self) -> None:
        """Adapter should accept custom temperature."""
        with patch("src.infrastructure.research_agent.generator_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = GeneratorAdapter(temperature=0.7)
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.7
