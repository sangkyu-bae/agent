"""Tests for Claude LLM client (LangChain-based)."""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.llm.exceptions import (
    ClaudeAPIError,
    ClaudeInvalidRequestError,
    ClaudeRateLimitError,
    ClaudeTimeoutError,
)
from src.infrastructure.llm.schemas import ClaudeModel, ClaudeRequest, ClaudeResponse


@pytest.fixture
def mock_logger():
    return Mock(spec=LoggerInterface)


@pytest.fixture
def make_request():
    def _make(**kwargs):
        defaults = {
            "model": ClaudeModel.SONNET_4_5,
            "messages": [{"role": "user", "content": "Hello"}],
            "request_id": "test-req-id",
        }
        defaults.update(kwargs)
        return ClaudeRequest(**defaults)
    return _make


def _mock_ai_message(
    content="Hi there!",
    model="claude-sonnet-4-5-20250929",
    stop_reason="end_turn",
    input_tokens=10,
    output_tokens=5,
):
    return AIMessage(
        content=content,
        response_metadata={"model": model, "stop_reason": stop_reason},
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


class TestClaudeClientInit:
    def test_creates_with_api_key_and_logger(self, mock_logger):
        from src.infrastructure.llm.claude_client import ClaudeClient

        client = ClaudeClient(api_key="test-key", logger=mock_logger)
        assert client._logger is mock_logger

    def test_stores_api_key(self, mock_logger):
        from src.infrastructure.llm.claude_client import ClaudeClient

        client = ClaudeClient(api_key="test-key", logger=mock_logger)
        assert client._api_key == "test-key"


class TestClaudeClientComplete:
    @pytest.fixture
    def client(self, mock_logger):
        from src.infrastructure.llm.claude_client import ClaudeClient

        return ClaudeClient(api_key="test-key", logger=mock_logger)

    async def test_returns_claude_response(self, client, make_request):
        request = make_request()
        mock_chat = AsyncMock()
        mock_chat.ainvoke = AsyncMock(return_value=_mock_ai_message())

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            response = await client.complete(request)

        assert isinstance(response, ClaudeResponse)
        assert response.content == "Hi there!"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.stop_reason == "end_turn"
        assert response.request_id == "test-req-id"

    async def test_creates_chat_model_with_request_params(self, client, make_request):
        request = make_request(max_tokens=2048, temperature=0.3)

        with patch(
            "src.infrastructure.llm.claude_client.ChatAnthropic"
        ) as MockChatAnthropic:
            mock_chat = AsyncMock()
            mock_chat.ainvoke = AsyncMock(return_value=_mock_ai_message())
            MockChatAnthropic.return_value = mock_chat

            await client.complete(request)

        MockChatAnthropic.assert_called_once_with(
            model=ClaudeModel.SONNET_4_5.value,
            api_key="test-key",
            max_tokens=2048,
            temperature=0.3,
            max_retries=3,
            timeout=60,
            stream_usage=True,
        )

    async def test_builds_messages_with_system(self, client, make_request):
        request = make_request(system="Be helpful")
        mock_chat = AsyncMock()
        mock_chat.ainvoke = AsyncMock(return_value=_mock_ai_message())

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            await client.complete(request)

        call_messages = mock_chat.ainvoke.call_args[0][0]
        assert isinstance(call_messages[0], SystemMessage)
        assert call_messages[0].content == "Be helpful"
        assert isinstance(call_messages[1], HumanMessage)
        assert call_messages[1].content == "Hello"

    async def test_builds_messages_without_system(self, client, make_request):
        request = make_request()
        mock_chat = AsyncMock()
        mock_chat.ainvoke = AsyncMock(return_value=_mock_ai_message())

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            await client.complete(request)

        call_messages = mock_chat.ainvoke.call_args[0][0]
        assert len(call_messages) == 1
        assert isinstance(call_messages[0], HumanMessage)

    async def test_logs_request_start(self, client, mock_logger, make_request):
        request = make_request()
        mock_chat = AsyncMock()
        mock_chat.ainvoke = AsyncMock(return_value=_mock_ai_message())

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            await client.complete(request)

        first_info_call = mock_logger.info.call_args_list[0]
        assert "Claude API request started" in first_info_call[0][0]
        assert first_info_call[1]["request_id"] == "test-req-id"
        assert first_info_call[1]["model"] == ClaudeModel.SONNET_4_5.value

    async def test_logs_request_completion(self, client, mock_logger, make_request):
        request = make_request()
        mock_chat = AsyncMock()
        mock_chat.ainvoke = AsyncMock(return_value=_mock_ai_message())

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            await client.complete(request)

        second_info_call = mock_logger.info.call_args_list[1]
        assert "Claude API request completed" in second_info_call[0][0]
        assert second_info_call[1]["input_tokens"] == 10
        assert second_info_call[1]["output_tokens"] == 5
        assert "latency_ms" in second_info_call[1]

    async def test_calculates_latency(self, client, make_request):
        request = make_request()
        mock_chat = AsyncMock()
        mock_chat.ainvoke = AsyncMock(return_value=_mock_ai_message())

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            response = await client.complete(request)

        assert response.latency_ms >= 0

    async def test_rate_limit_error(self, client, mock_logger, make_request):
        from anthropic import RateLimitError

        request = make_request()
        mock_chat = AsyncMock()
        mock_resp = Mock(status_code=429, headers={})
        mock_chat.ainvoke = AsyncMock(
            side_effect=RateLimitError(
                message="Rate limit exceeded", response=mock_resp, body=None
            )
        )

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            with pytest.raises(ClaudeRateLimitError):
                await client.complete(request)

        mock_logger.error.assert_called()
        assert mock_logger.error.call_args[1]["request_id"] == "test-req-id"

    async def test_timeout_error(self, client, mock_logger, make_request):
        from anthropic import APITimeoutError

        request = make_request()
        mock_chat = AsyncMock()
        mock_chat.ainvoke = AsyncMock(
            side_effect=APITimeoutError(request=Mock())
        )

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            with pytest.raises(ClaudeTimeoutError):
                await client.complete(request)

        mock_logger.error.assert_called()

    async def test_bad_request_error(self, client, mock_logger, make_request):
        from anthropic import BadRequestError

        request = make_request()
        mock_chat = AsyncMock()
        mock_resp = Mock(status_code=400, headers={})
        mock_chat.ainvoke = AsyncMock(
            side_effect=BadRequestError(
                message="Invalid model", response=mock_resp, body=None
            )
        )

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            with pytest.raises(ClaudeInvalidRequestError):
                await client.complete(request)

        mock_logger.error.assert_called()

    async def test_generic_api_error(self, client, mock_logger, make_request):
        from anthropic import APIError

        request = make_request()
        mock_chat = AsyncMock()
        mock_chat.ainvoke = AsyncMock(
            side_effect=APIError(
                message="Internal server error", request=Mock(), body=None
            )
        )

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            with pytest.raises(ClaudeAPIError):
                await client.complete(request)

        mock_logger.error.assert_called()

    async def test_error_log_includes_exception(self, client, mock_logger, make_request):
        from anthropic import APITimeoutError

        request = make_request()
        mock_chat = AsyncMock()
        mock_chat.ainvoke = AsyncMock(
            side_effect=APITimeoutError(request=Mock())
        )

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            with pytest.raises(ClaudeTimeoutError):
                await client.complete(request)

        error_call = mock_logger.error.call_args
        assert "exception" in error_call[1]
        assert error_call[1]["exception"] is not None


class TestClaudeClientStream:
    @pytest.fixture
    def client(self, mock_logger):
        from src.infrastructure.llm.claude_client import ClaudeClient

        return ClaudeClient(api_key="test-key", logger=mock_logger)

    async def test_stream_yields_chunks(self, client, mock_logger, make_request):
        request = make_request()
        chunks = [
            AIMessageChunk(content="Hello"),
            AIMessageChunk(content=" "),
            AIMessageChunk(content="world"),
            AIMessageChunk(
                content="",
                usage_metadata={"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            ),
        ]

        mock_chat = AsyncMock()
        mock_chat.astream = Mock(return_value=_async_iter(chunks))

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            result = []
            async for chunk in client.stream_complete(request):
                result.append(chunk)

        assert result == ["Hello", " ", "world"]

    async def test_stream_logs_start(self, client, mock_logger, make_request):
        request = make_request()
        chunks = [
            AIMessageChunk(
                content="hi",
                usage_metadata={"input_tokens": 5, "output_tokens": 1, "total_tokens": 6},
            ),
        ]

        mock_chat = AsyncMock()
        mock_chat.astream = Mock(return_value=_async_iter(chunks))

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            async for _ in client.stream_complete(request):
                pass

        first_info_call = mock_logger.info.call_args_list[0]
        assert "streaming request started" in first_info_call[0][0]

    async def test_stream_logs_completion_with_tokens(self, client, mock_logger, make_request):
        request = make_request()
        chunks = [
            AIMessageChunk(content="hi"),
            AIMessageChunk(
                content="",
                usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
            ),
        ]

        mock_chat = AsyncMock()
        mock_chat.astream = Mock(return_value=_async_iter(chunks))

        with patch.object(client, "_create_chat_model", return_value=mock_chat):
            async for _ in client.stream_complete(request):
                pass

        last_info_call = mock_logger.info.call_args_list[-1]
        assert "streaming completed" in last_info_call[0][0]
        assert last_info_call[1]["input_tokens"] == 5
        assert last_info_call[1]["output_tokens"] == 2


async def _async_iter(items):
    for item in items:
        yield item
