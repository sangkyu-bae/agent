"""Tests for RouterAdapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.research_agent.router_adapter import RouterAdapter
from src.infrastructure.research_agent.schemas import RouterOutput
from src.domain.research_agent.value_objects import RouteDecision, RouteType


class TestRouterAdapter:
    """Tests for RouterAdapter."""

    @pytest.fixture
    def mock_chain(self) -> MagicMock:
        """Create a mock chain."""
        return AsyncMock()

    @pytest.fixture
    def adapter_with_mock(self, mock_chain: MagicMock) -> RouterAdapter:
        """Create adapter with mocked chain."""
        with patch("src.infrastructure.research_agent.router_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            with patch.object(RouterAdapter, "_build_chain", return_value=mock_chain):
                adapter = RouterAdapter()
                adapter._chain = mock_chain
                return adapter

    async def test_route_returns_web_search(
        self, adapter_with_mock: RouterAdapter, mock_chain: MagicMock
    ) -> None:
        """Route should return WEB_SEARCH when LLM says web_search."""
        mock_chain.ainvoke.return_value = RouterOutput(route="web_search")

        result = await adapter_with_mock.route(
            question="최신 AI 동향은 무엇인가요?",
            request_id="test-request-123"
        )

        assert isinstance(result, RouteDecision)
        assert result.route == RouteType.WEB_SEARCH

    async def test_route_returns_rag(
        self, adapter_with_mock: RouterAdapter, mock_chain: MagicMock
    ) -> None:
        """Route should return RAG when LLM says rag."""
        mock_chain.ainvoke.return_value = RouterOutput(route="rag")

        result = await adapter_with_mock.route(
            question="회사 정책에 대해 설명해주세요",
            request_id="test-request-456"
        )

        assert isinstance(result, RouteDecision)
        assert result.route == RouteType.RAG

    async def test_route_passes_question_to_chain(
        self, adapter_with_mock: RouterAdapter, mock_chain: MagicMock
    ) -> None:
        """Route should pass question in correct format."""
        mock_chain.ainvoke.return_value = RouterOutput(route="rag")

        await adapter_with_mock.route(
            question="테스트 질문입니다",
            request_id="test-request-789"
        )

        mock_chain.ainvoke.assert_called_once()
        call_args = mock_chain.ainvoke.call_args[0][0]
        assert "question" in call_args
        assert call_args["question"] == "테스트 질문입니다"

    async def test_route_propagates_llm_error(
        self, adapter_with_mock: RouterAdapter, mock_chain: MagicMock
    ) -> None:
        """Route should propagate exceptions from LLM."""
        mock_chain.ainvoke.side_effect = Exception("LLM API error")

        with pytest.raises(Exception, match="LLM API error"):
            await adapter_with_mock.route(
                question="질문입니다",
                request_id="test-request-error"
            )

    async def test_route_includes_reason_in_result(
        self, adapter_with_mock: RouterAdapter, mock_chain: MagicMock
    ) -> None:
        """Route should include a reason in the result."""
        mock_chain.ainvoke.return_value = RouterOutput(route="web_search")

        result = await adapter_with_mock.route(
            question="최신 뉴스",
            request_id="test-request-reason"
        )

        assert result.reason is not None
        assert len(result.reason) > 0


class TestRouterAdapterInit:
    """Tests for RouterAdapter initialization."""

    def test_default_model_name(self) -> None:
        """Adapter should use gpt-4o-mini as default model."""
        with patch("src.infrastructure.research_agent.router_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = RouterAdapter()
            mock_chat.assert_called_once()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o-mini"

    def test_default_temperature(self) -> None:
        """Adapter should use temperature=0.0 as default."""
        with patch("src.infrastructure.research_agent.router_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = RouterAdapter()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.0

    def test_custom_model_name(self) -> None:
        """Adapter should accept custom model name."""
        with patch("src.infrastructure.research_agent.router_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = RouterAdapter(model_name="gpt-4o")
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o"

    def test_custom_temperature(self) -> None:
        """Adapter should accept custom temperature."""
        with patch("src.infrastructure.research_agent.router_adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = RouterAdapter(temperature=0.5)
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.5
