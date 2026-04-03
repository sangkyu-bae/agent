"""Unit tests for OllamaClient (TDD - written before implementation)."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.llm.ollama.ollama_client import OllamaClient
from src.infrastructure.llm.ollama.schemas import OllamaModel, OllamaRequest, OllamaResponse
from src.infrastructure.llm.ollama.exceptions import (
    OllamaConnectionError,
    OllamaLLMError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_logger() -> Mock:
    return Mock(spec=LoggerInterface)


@pytest.fixture
def ollama_client(mock_logger: Mock) -> OllamaClient:
    return OllamaClient(
        base_url="http://localhost:11434",
        logger=mock_logger,
        timeout=120,
    )


@pytest.fixture
def basic_request() -> OllamaRequest:
    return OllamaRequest(
        model=OllamaModel.LLAMA3_2,
        messages=[{"role": "user", "content": "Hello"}],
        request_id="test-request-id",
    )


def _make_ai_message(content: str = "Hello back!", model: str = "llama3.2") -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.response_metadata = {"model": model, "done_reason": "stop"}
    msg.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
    return msg


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------

class TestOllamaRequest:
    def test_default_request_id_generated(self):
        req = OllamaRequest(
            model=OllamaModel.LLAMA3_2,
            messages=[{"role": "user", "content": "hi"}],
        )
        assert req.request_id
        assert len(req.request_id) > 0

    def test_raises_on_empty_messages(self):
        with pytest.raises(ValueError, match="messages must not be empty"):
            OllamaRequest(model=OllamaModel.LLAMA3_2, messages=[])

    def test_raises_on_message_missing_role(self):
        with pytest.raises(ValueError, match="role"):
            OllamaRequest(
                model=OllamaModel.LLAMA3_2,
                messages=[{"content": "hi"}],
            )

    def test_raises_on_invalid_temperature(self):
        with pytest.raises(ValueError, match="temperature"):
            OllamaRequest(
                model=OllamaModel.LLAMA3_2,
                messages=[{"role": "user", "content": "hi"}],
                temperature=2.0,
            )

    def test_raises_on_invalid_max_tokens(self):
        with pytest.raises(ValueError, match="max_tokens"):
            OllamaRequest(
                model=OllamaModel.LLAMA3_2,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=0,
            )

    def test_string_model_allowed(self):
        req = OllamaRequest(
            model="custom-model:latest",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert req.model == "custom-model:latest"


# ---------------------------------------------------------------------------
# complete() Tests
# ---------------------------------------------------------------------------

class TestOllamaClientComplete:
    @pytest.mark.asyncio
    async def test_complete_success(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        ai_message = _make_ai_message("Hello back!", "llama3.2")

        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.ainvoke = AsyncMock(return_value=ai_message)
            mock_factory.return_value = mock_chat

            response = await ollama_client.complete(basic_request)

        assert isinstance(response, OllamaResponse)
        assert response.content == "Hello back!"
        assert response.model == "llama3.2"
        assert response.request_id == "test-request-id"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_complete_logs_request_start(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        ai_message = _make_ai_message()

        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.ainvoke = AsyncMock(return_value=ai_message)
            mock_factory.return_value = mock_chat

            await ollama_client.complete(basic_request)

        first_info_call = mock_logger.info.call_args_list[0]
        assert "Ollama API request started" in first_info_call[0][0]
        assert first_info_call[1]["request_id"] == "test-request-id"

    @pytest.mark.asyncio
    async def test_complete_logs_request_completion(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        ai_message = _make_ai_message()

        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.ainvoke = AsyncMock(return_value=ai_message)
            mock_factory.return_value = mock_chat

            await ollama_client.complete(basic_request)

        assert mock_logger.info.call_count == 2
        last_info_call = mock_logger.info.call_args_list[1]
        assert "Ollama API request completed" in last_info_call[0][0]

    @pytest.mark.asyncio
    async def test_complete_with_system_message(self, ollama_client: OllamaClient, mock_logger: Mock):
        request = OllamaRequest(
            model=OllamaModel.LLAMA3_2,
            messages=[{"role": "user", "content": "Hi"}],
            system="You are a helpful assistant.",
            request_id="test-system-id",
        )
        ai_message = _make_ai_message()

        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.ainvoke = AsyncMock(return_value=ai_message)
            mock_factory.return_value = mock_chat

            response = await ollama_client.complete(request)

        assert response.content == "Hello back!"

    @pytest.mark.asyncio
    async def test_complete_connection_error(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.ainvoke = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_factory.return_value = mock_chat

            with pytest.raises(OllamaConnectionError):
                await ollama_client.complete(basic_request)

        mock_logger.error.assert_called_once()
        assert "exception" in mock_logger.error.call_args[1]

    @pytest.mark.asyncio
    async def test_complete_timeout_error(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.ainvoke = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_factory.return_value = mock_chat

            with pytest.raises(OllamaTimeoutError):
                await ollama_client.complete(basic_request)

        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_model_not_found_error(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.ainvoke = AsyncMock(
                side_effect=Exception("model 'llama3.2' not found, try pulling it first")
            )
            mock_factory.return_value = mock_chat

            with pytest.raises(OllamaModelNotFoundError):
                await ollama_client.complete(basic_request)

    @pytest.mark.asyncio
    async def test_complete_generic_error(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.ainvoke = AsyncMock(side_effect=Exception("unexpected error"))
            mock_factory.return_value = mock_chat

            with pytest.raises(OllamaLLMError):
                await ollama_client.complete(basic_request)

    @pytest.mark.asyncio
    async def test_complete_with_string_model(self, ollama_client: OllamaClient, mock_logger: Mock):
        request = OllamaRequest(
            model="phi3:mini",
            messages=[{"role": "user", "content": "hi"}],
            request_id="string-model-id",
        )
        ai_message = _make_ai_message(model="phi3:mini")

        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.ainvoke = AsyncMock(return_value=ai_message)
            mock_factory.return_value = mock_chat

            response = await ollama_client.complete(request)

        assert response.model == "phi3:mini"

    @pytest.mark.asyncio
    async def test_complete_missing_usage_metadata(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        """usage_metadata가 None이어도 에러 없이 0으로 처리"""
        ai_message = MagicMock()
        ai_message.content = "OK"
        ai_message.response_metadata = {"model": "llama3.2", "done_reason": "stop"}
        ai_message.usage_metadata = None

        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.ainvoke = AsyncMock(return_value=ai_message)
            mock_factory.return_value = mock_chat

            response = await ollama_client.complete(basic_request)

        assert response.input_tokens == 0
        assert response.output_tokens == 0


# ---------------------------------------------------------------------------
# stream_complete() Tests
# ---------------------------------------------------------------------------

class TestOllamaClientStreamComplete:
    @pytest.mark.asyncio
    async def test_stream_complete_success(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        chunks = [
            MagicMock(content="Hello", usage_metadata=None),
            MagicMock(content=" back", usage_metadata=None),
            MagicMock(content="!", usage_metadata={"input_tokens": 10, "output_tokens": 3}),
        ]

        async def async_gen(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.astream = async_gen
            mock_factory.return_value = mock_chat

            collected = []
            async for token in ollama_client.stream_complete(basic_request):
                collected.append(token)

        assert collected == ["Hello", " back", "!"]

    @pytest.mark.asyncio
    async def test_stream_complete_logs_start_and_completion(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        async def async_gen(*args, **kwargs):
            yield MagicMock(content="hi", usage_metadata=None)

        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.astream = async_gen
            mock_factory.return_value = mock_chat

            async for _ in ollama_client.stream_complete(basic_request):
                pass

        assert mock_logger.info.call_count == 2
        assert "streaming request started" in mock_logger.info.call_args_list[0][0][0]
        assert "streaming completed" in mock_logger.info.call_args_list[1][0][0]

    @pytest.mark.asyncio
    async def test_stream_complete_connection_error(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        async def async_gen(*args, **kwargs):
            raise httpx.ConnectError("refused")
            yield  # make it a generator

        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.astream = async_gen
            mock_factory.return_value = mock_chat

            with pytest.raises(OllamaConnectionError):
                async for _ in ollama_client.stream_complete(basic_request):
                    pass

    @pytest.mark.asyncio
    async def test_stream_complete_skips_empty_chunks(self, ollama_client: OllamaClient, basic_request: OllamaRequest, mock_logger: Mock):
        chunks = [
            MagicMock(content="", usage_metadata=None),
            MagicMock(content="Hello", usage_metadata=None),
            MagicMock(content="", usage_metadata=None),
        ]

        async def async_gen(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        with patch.object(ollama_client, "_create_chat_model") as mock_factory:
            mock_chat = MagicMock()
            mock_chat.astream = async_gen
            mock_factory.return_value = mock_chat

            collected = []
            async for token in ollama_client.stream_complete(basic_request):
                collected.append(token)

        assert collected == ["Hello"]


# ---------------------------------------------------------------------------
# _create_chat_model() Tests
# ---------------------------------------------------------------------------

class TestOllamaClientCreateChatModel:
    def test_creates_model_with_enum(self, ollama_client: OllamaClient, basic_request: OllamaRequest):
        with patch("src.infrastructure.llm.ollama.ollama_client.ChatOllama") as mock_cls:
            ollama_client._create_chat_model(basic_request)
            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["model"] == "llama3.2"
            assert call_kwargs["base_url"] == "http://localhost:11434"

    def test_creates_model_with_string(self, ollama_client: OllamaClient):
        request = OllamaRequest(
            model="phi3:mini",
            messages=[{"role": "user", "content": "hi"}],
        )
        with patch("src.infrastructure.llm.ollama.ollama_client.ChatOllama") as mock_cls:
            ollama_client._create_chat_model(request)
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["model"] == "phi3:mini"


# ---------------------------------------------------------------------------
# Integration Tests (real Ollama server - skipped if OLLAMA_BASE_URL not set)
# ---------------------------------------------------------------------------

class TestOllamaClientIntegration:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_complete(self):
        """실제 Ollama 서버 호출 테스트 (OLLAMA_BASE_URL 환경변수 설정 시 실행)."""
        import os
        from src.infrastructure.logging.structured_logger import StructuredLogger

        base_url = os.getenv("OLLAMA_BASE_URL", "")
        if not base_url:
            pytest.skip("OLLAMA_BASE_URL not set — skipping integration test")

        model = os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2")
        logger = StructuredLogger(name="test-ollama-integration")
        client = OllamaClient(base_url=base_url, logger=logger, timeout=120)

        request = OllamaRequest(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly one word: hello"}],
            max_tokens=10,
            temperature=0.0,
        )

        response = await client.complete(request)

        assert response.content
        assert response.model
        assert response.latency_ms >= 0
        assert response.request_id == request.request_id

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_stream_complete(self):
        """실제 Ollama 서버 스트리밍 테스트 (OLLAMA_BASE_URL 환경변수 설정 시 실행)."""
        import os
        from src.infrastructure.logging.structured_logger import StructuredLogger

        base_url = os.getenv("OLLAMA_BASE_URL", "")
        if not base_url:
            pytest.skip("OLLAMA_BASE_URL not set — skipping integration test")

        model = os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2")
        logger = StructuredLogger(name="test-ollama-integration")
        client = OllamaClient(base_url=base_url, logger=logger, timeout=120)

        request = OllamaRequest(
            model=model,
            messages=[{"role": "user", "content": "Say hi"}],
            max_tokens=10,
            temperature=0.0,
        )

        chunks = []
        async for token in client.stream_complete(request):
            chunks.append(token)

        assert len(chunks) > 0
        assert "".join(chunks)
