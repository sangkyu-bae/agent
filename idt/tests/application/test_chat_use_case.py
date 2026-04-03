from unittest.mock import AsyncMock

import pytest

from src.application.chat_use_case import ChatUseCase
from src.infrastructure.llm_adapter import LLMAdapter


class TestChatUseCase:
    @pytest.fixture
    def mock_llm_adapter(self) -> AsyncMock:
        adapter = AsyncMock(spec=LLMAdapter)
        adapter.generate.return_value = "I'm an AI assistant. How can I help?"
        return adapter

    @pytest.fixture
    def use_case(self, mock_llm_adapter: AsyncMock) -> ChatUseCase:
        return ChatUseCase(llm_adapter=mock_llm_adapter)

    async def test_chat_returns_llm_response(
        self, use_case: ChatUseCase, mock_llm_adapter: AsyncMock
    ) -> None:
        result = await use_case.execute(
            user_id="user-1",
            session_id="session-1",
            message="Hello",
        )

        assert result == "I'm an AI assistant. How can I help?"
        mock_llm_adapter.generate.assert_called_once_with("Hello")

    async def test_chat_passes_message_to_adapter(
        self, use_case: ChatUseCase, mock_llm_adapter: AsyncMock
    ) -> None:
        await use_case.execute(
            user_id="user-1",
            session_id="session-1",
            message="What is Python?",
        )

        mock_llm_adapter.generate.assert_called_once_with("What is Python?")
