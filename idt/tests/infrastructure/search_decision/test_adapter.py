"""Tests for LLMSearchDecisionAdapter."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.domain.search_decision.schemas import WebSearchDecision
from src.infrastructure.search_decision.adapter import LLMSearchDecisionAdapter


def _build_adapter() -> LLMSearchDecisionAdapter:
    # ChatOpenAI 생성 시 실제 네트워크/키 불필요하도록 패치
    with patch(
        "src.infrastructure.search_decision.adapter.ChatOpenAI"
    ):
        return LLMSearchDecisionAdapter(logger=Mock())


class TestLLMSearchDecisionAdapter:
    @pytest.mark.asyncio
    async def test_returns_structured_decision(self):
        adapter = _build_adapter()
        adapter._chain = Mock()
        adapter._chain.ainvoke = AsyncMock(
            return_value=WebSearchDecision(needs_web_search=True, reason="외부 정보")
        )

        result = await adapter.decide("질문", "분석", "req-1")

        assert result.needs_web_search is True
        adapter._chain.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_graceful_fallback_on_exception(self):
        adapter = _build_adapter()
        adapter._chain = Mock()
        adapter._chain.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))

        result = await adapter.decide("질문", "분석", "req-1")

        assert result.needs_web_search is False
