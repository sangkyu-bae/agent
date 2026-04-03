"""LangChainSummarizer / LangChainConversationLLM 단위 테스트 (LLM mock)."""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.value_objects import MessageRole, SessionId, TurnIndex, UserId


def _make_message(turn: int, role: str, content: str) -> ConversationMessage:
    return ConversationMessage(
        id=None,
        user_id=UserId("u-1"),
        session_id=SessionId("s-1"),
        role=MessageRole.USER if role == "user" else MessageRole.ASSISTANT,
        content=content,
        turn_index=TurnIndex(turn),
        created_at=datetime(2026, 1, 1),
    )


# ─────────────────────────────────────────────
# LangChainSummarizer
# ─────────────────────────────────────────────

class TestLangChainSummarizer:
    @pytest.mark.asyncio
    async def test_summarize_returns_string(self):
        from src.infrastructure.conversation.langchain_summarizer import LangChainSummarizer

        mock_llm_response = MagicMock()
        mock_llm_response.content = "요약된 내용"

        with patch(
            "src.infrastructure.conversation.langchain_summarizer.ChatOpenAI"
        ) as MockChatOpenAI:
            mock_instance = AsyncMock()
            mock_instance.ainvoke.return_value = mock_llm_response
            MockChatOpenAI.return_value = mock_instance

            summarizer = LangChainSummarizer(
                model_name="gpt-4o-mini",
                api_key="test-key",
                logger=MagicMock(),
            )
            messages = [
                _make_message(1, "user", "첫 질문"),
                _make_message(2, "assistant", "첫 답변"),
            ]
            result = await summarizer.summarize(messages, "req-1")

        assert result == "요약된 내용"

    @pytest.mark.asyncio
    async def test_summarize_logs_start_and_complete(self):
        from src.infrastructure.conversation.langchain_summarizer import LangChainSummarizer

        mock_response = MagicMock()
        mock_response.content = "요약"

        with patch(
            "src.infrastructure.conversation.langchain_summarizer.ChatOpenAI"
        ) as MockChatOpenAI:
            mock_instance = AsyncMock()
            mock_instance.ainvoke.return_value = mock_response
            MockChatOpenAI.return_value = mock_instance

            logger = MagicMock()
            summarizer = LangChainSummarizer(
                model_name="gpt-4o-mini", api_key="key", logger=logger
            )
            await summarizer.summarize([_make_message(1, "user", "q")], "req-1")

        assert logger.info.call_count >= 2

    @pytest.mark.asyncio
    async def test_summarize_logs_error_and_reraises(self):
        from src.infrastructure.conversation.langchain_summarizer import LangChainSummarizer

        with patch(
            "src.infrastructure.conversation.langchain_summarizer.ChatOpenAI"
        ) as MockChatOpenAI:
            mock_instance = AsyncMock()
            mock_instance.ainvoke.side_effect = RuntimeError("LLM 오류")
            MockChatOpenAI.return_value = mock_instance

            logger = MagicMock()
            summarizer = LangChainSummarizer(
                model_name="gpt-4o-mini", api_key="key", logger=logger
            )
            with pytest.raises(RuntimeError):
                await summarizer.summarize([_make_message(1, "user", "q")], "req-1")

        logger.error.assert_called_once()


# ─────────────────────────────────────────────
# LangChainConversationLLM
# ─────────────────────────────────────────────

class TestLangChainConversationLLM:
    @pytest.mark.asyncio
    async def test_generate_returns_string(self):
        from src.infrastructure.conversation.langchain_llm import LangChainConversationLLM

        mock_response = MagicMock()
        mock_response.content = "LLM 응답입니다"

        with patch(
            "src.infrastructure.conversation.langchain_llm.ChatOpenAI"
        ) as MockChatOpenAI:
            mock_instance = AsyncMock()
            mock_instance.ainvoke.return_value = mock_response
            MockChatOpenAI.return_value = mock_instance

            llm = LangChainConversationLLM(
                model_name="gpt-4o-mini",
                api_key="test-key",
                logger=MagicMock(),
            )
            messages = [
                {"role": "user", "content": "안녕하세요"},
            ]
            result = await llm.generate(messages, "req-1")

        assert result == "LLM 응답입니다"

    @pytest.mark.asyncio
    async def test_generate_handles_system_user_assistant_roles(self):
        from src.infrastructure.conversation.langchain_llm import LangChainConversationLLM

        mock_response = MagicMock()
        mock_response.content = "응답"

        with patch(
            "src.infrastructure.conversation.langchain_llm.ChatOpenAI"
        ) as MockChatOpenAI:
            mock_instance = AsyncMock()
            mock_instance.ainvoke.return_value = mock_response
            MockChatOpenAI.return_value = mock_instance

            llm = LangChainConversationLLM(
                model_name="gpt-4o-mini", api_key="key", logger=MagicMock()
            )
            messages = [
                {"role": "system", "content": "요약"},
                {"role": "user", "content": "질문"},
                {"role": "assistant", "content": "이전 답변"},
                {"role": "user", "content": "새 질문"},
            ]
            result = await llm.generate(messages, "req-1")

        assert result == "응답"
        mock_instance.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_logs_error_and_reraises(self):
        from src.infrastructure.conversation.langchain_llm import LangChainConversationLLM

        with patch(
            "src.infrastructure.conversation.langchain_llm.ChatOpenAI"
        ) as MockChatOpenAI:
            mock_instance = AsyncMock()
            mock_instance.ainvoke.side_effect = RuntimeError("LLM 오류")
            MockChatOpenAI.return_value = mock_instance

            logger = MagicMock()
            llm = LangChainConversationLLM(
                model_name="gpt-4o-mini", api_key="key", logger=logger
            )
            with pytest.raises(RuntimeError):
                await llm.generate([{"role": "user", "content": "q"}], "req-1")

        logger.error.assert_called_once()
