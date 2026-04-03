"""Ollama LLM client implementation using LangChain ChatOllama."""
import time
from typing import AsyncIterator

import httpx
from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.llm.ollama.exceptions import (
    OllamaConnectionError,
    OllamaLLMError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
)
from src.infrastructure.llm.ollama.schemas import OllamaModel, OllamaRequest, OllamaResponse


class OllamaClient:
    """Async Ollama LLM client using LangChain ChatOllama.

    Connects to a locally running Ollama server (default: http://localhost:11434).
    No API key is required; models must be pulled beforehand via `ollama pull`.
    """

    def __init__(
        self,
        base_url: str,
        logger: LoggerInterface,
        timeout: int = 120,
    ) -> None:
        self._base_url = base_url
        self._logger = logger
        self._timeout = timeout

    def _create_chat_model(self, request: OllamaRequest) -> ChatOllama:
        """Create a ChatOllama instance configured for the given request."""
        model_name = (
            request.model.value
            if isinstance(request.model, OllamaModel)
            else request.model
        )
        return ChatOllama(
            model=model_name,
            base_url=self._base_url,
            temperature=request.temperature,
            num_predict=request.max_tokens,
            timeout=self._timeout,
        )

    def _build_messages(
        self, request: OllamaRequest
    ) -> list[SystemMessage | HumanMessage | AIMessage]:
        """Convert OllamaRequest messages to LangChain message objects."""
        messages: list[SystemMessage | HumanMessage | AIMessage] = []
        if request.system:
            messages.append(SystemMessage(content=request.system))
        for msg in request.messages:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        return messages

    def _resolve_model_name(self, request: OllamaRequest) -> str:
        return (
            request.model.value
            if isinstance(request.model, OllamaModel)
            else request.model
        )

    async def complete(self, request: OllamaRequest) -> OllamaResponse:
        """Execute Ollama model call (non-streaming).

        Raises:
            OllamaConnectionError: Cannot connect to the Ollama server.
            OllamaTimeoutError: Request exceeded the configured timeout.
            OllamaModelNotFoundError: The requested model is not installed.
            OllamaLLMError: Any other Ollama error.
        """
        model_name = self._resolve_model_name(request)

        self._logger.info(
            "Ollama API request started",
            request_id=request.request_id,
            model=model_name,
            message_count=len(request.messages),
            max_tokens=request.max_tokens,
            stream=request.stream,
        )

        start_time = time.perf_counter()

        try:
            chat = self._create_chat_model(request)
            messages = self._build_messages(request)
            ai_message = await chat.ainvoke(messages)
        except httpx.ConnectError as e:
            self._logger.error(
                "Ollama server connection failed",
                exception=e,
                request_id=request.request_id,
                base_url=self._base_url,
            )
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self._base_url}"
            ) from e
        except httpx.TimeoutException as e:
            self._logger.error(
                "Ollama request timeout",
                exception=e,
                request_id=request.request_id,
            )
            raise OllamaTimeoutError(str(e)) from e
        except Exception as e:
            error_msg = str(e).lower()
            if "model" in error_msg and "not found" in error_msg:
                self._logger.error(
                    "Ollama model not found",
                    exception=e,
                    request_id=request.request_id,
                    model=model_name,
                )
                raise OllamaModelNotFoundError(str(e)) from e
            self._logger.error(
                "Ollama request failed",
                exception=e,
                request_id=request.request_id,
                model=model_name,
            )
            raise OllamaLLMError(str(e)) from e

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        usage = ai_message.usage_metadata or {}

        result = OllamaResponse(
            content=ai_message.content,
            model=ai_message.response_metadata.get("model", model_name),
            stop_reason=ai_message.response_metadata.get("done_reason", "unknown"),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            request_id=request.request_id,
            latency_ms=latency_ms,
        )

        self._logger.info(
            "Ollama API request completed",
            request_id=request.request_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
            stop_reason=result.stop_reason,
        )

        return result

    async def stream_complete(self, request: OllamaRequest) -> AsyncIterator[str]:
        """Execute Ollama model call (streaming).

        Yields:
            Content chunks as strings (empty chunks are skipped).

        Raises:
            OllamaConnectionError: Cannot connect to the Ollama server.
            OllamaTimeoutError: Request exceeded the configured timeout.
            OllamaModelNotFoundError: The requested model is not installed.
            OllamaLLMError: Any other Ollama error.
        """
        model_name = self._resolve_model_name(request)

        self._logger.info(
            "Ollama API streaming request started",
            request_id=request.request_id,
            model=model_name,
            message_count=len(request.messages),
        )

        input_tokens = 0
        output_tokens = 0

        try:
            chat = self._create_chat_model(request)
            messages = self._build_messages(request)

            async for chunk in chat.astream(messages):
                if chunk.content:
                    yield chunk.content
                if chunk.usage_metadata:
                    input_tokens = chunk.usage_metadata.get("input_tokens", input_tokens)
                    output_tokens = chunk.usage_metadata.get("output_tokens", output_tokens)

        except httpx.ConnectError as e:
            self._logger.error(
                "Ollama server connection failed during streaming",
                exception=e,
                request_id=request.request_id,
                base_url=self._base_url,
            )
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self._base_url}"
            ) from e
        except httpx.TimeoutException as e:
            self._logger.error(
                "Ollama streaming timeout",
                exception=e,
                request_id=request.request_id,
            )
            raise OllamaTimeoutError(str(e)) from e
        except Exception as e:
            error_msg = str(e).lower()
            if "model" in error_msg and "not found" in error_msg:
                self._logger.error(
                    "Ollama model not found during streaming",
                    exception=e,
                    request_id=request.request_id,
                    model=model_name,
                )
                raise OllamaModelNotFoundError(str(e)) from e
            self._logger.error(
                "Ollama streaming failed",
                exception=e,
                request_id=request.request_id,
                model=model_name,
            )
            raise OllamaLLMError(str(e)) from e

        self._logger.info(
            "Ollama API streaming completed",
            request_id=request.request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
