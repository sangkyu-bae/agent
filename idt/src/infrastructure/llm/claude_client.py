"""Claude LLM client implementation using LangChain."""
import time
from typing import AsyncIterator

from anthropic import (
    APIError,
    APITimeoutError,
    BadRequestError,
    RateLimitError,
)
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.llm.exceptions import (
    ClaudeAPIError,
    ClaudeInvalidRequestError,
    ClaudeRateLimitError,
    ClaudeTimeoutError,
)
from src.infrastructure.llm.schemas import ClaudeRequest, ClaudeResponse


class ClaudeClient:
    """Async Claude LLM client using LangChain ChatAnthropic."""

    def __init__(
        self,
        api_key: str,
        logger: LoggerInterface,
        max_retries: int = 3,
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key
        self._logger = logger
        self._max_retries = max_retries
        self._timeout = timeout

    def _create_chat_model(self, request: ClaudeRequest) -> ChatAnthropic:
        """Create ChatAnthropic instance with request-specific params."""
        return ChatAnthropic(
            model=request.model.value,
            api_key=self._api_key,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            max_retries=self._max_retries,
            timeout=self._timeout,
            stream_usage=True,
        )

    def _build_messages(
        self, request: ClaudeRequest
    ) -> list[SystemMessage | HumanMessage | AIMessage]:
        """Convert ClaudeRequest messages to LangChain messages."""
        messages: list[SystemMessage | HumanMessage | AIMessage] = []
        if request.system:
            messages.append(SystemMessage(content=request.system))
        for msg in request.messages:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        return messages

    async def complete(self, request: ClaudeRequest) -> ClaudeResponse:
        """Execute Claude API call (non-streaming).

        Raises:
            ClaudeAPIError: API call failure (5xx).
            ClaudeRateLimitError: Rate limit exceeded.
            ClaudeTimeoutError: Request timeout.
            ClaudeInvalidRequestError: Invalid request (4xx).
        """
        self._logger.info(
            "Claude API request started",
            request_id=request.request_id,
            model=request.model.value,
            message_count=len(request.messages),
            max_tokens=request.max_tokens,
            stream=request.stream,
        )

        start_time = time.perf_counter()

        try:
            chat = self._create_chat_model(request)
            messages = self._build_messages(request)
            ai_message = await chat.ainvoke(messages)
        except RateLimitError as e:
            self._logger.error(
                "Rate limit exceeded",
                exception=e,
                request_id=request.request_id,
            )
            raise ClaudeRateLimitError(str(e)) from e
        except APITimeoutError as e:
            self._logger.error(
                "API timeout",
                exception=e,
                request_id=request.request_id,
            )
            raise ClaudeTimeoutError(str(e)) from e
        except BadRequestError as e:
            self._logger.error(
                "Invalid request",
                exception=e,
                request_id=request.request_id,
            )
            raise ClaudeInvalidRequestError(str(e)) from e
        except APIError as e:
            self._logger.error(
                "API error",
                exception=e,
                request_id=request.request_id,
            )
            raise ClaudeAPIError(
                str(e), getattr(e, "status_code", None)
            ) from e

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        usage = ai_message.usage_metadata or {}

        result = ClaudeResponse(
            content=ai_message.content,
            model=ai_message.response_metadata.get(
                "model", request.model.value
            ),
            stop_reason=ai_message.response_metadata.get(
                "stop_reason", "end_turn"
            ),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            request_id=request.request_id,
            latency_ms=latency_ms,
        )

        self._logger.info(
            "Claude API request completed",
            request_id=request.request_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
            stop_reason=result.stop_reason,
        )

        return result

    async def stream_complete(
        self, request: ClaudeRequest
    ) -> AsyncIterator[str]:
        """Execute Claude API call (streaming).

        Yields:
            Content chunks as strings.
        """
        self._logger.info(
            "Claude API streaming request started",
            request_id=request.request_id,
            model=request.model.value,
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
                    input_tokens = chunk.usage_metadata.get(
                        "input_tokens", input_tokens
                    )
                    output_tokens = chunk.usage_metadata.get(
                        "output_tokens", output_tokens
                    )
        except RateLimitError as e:
            self._logger.error(
                "Rate limit exceeded during streaming",
                exception=e,
                request_id=request.request_id,
            )
            raise ClaudeRateLimitError(str(e)) from e
        except APITimeoutError as e:
            self._logger.error(
                "Timeout during streaming",
                exception=e,
                request_id=request.request_id,
            )
            raise ClaudeTimeoutError(str(e)) from e
        except BadRequestError as e:
            self._logger.error(
                "Invalid request for streaming",
                exception=e,
                request_id=request.request_id,
            )
            raise ClaudeInvalidRequestError(str(e)) from e
        except APIError as e:
            self._logger.error(
                "API error during streaming",
                exception=e,
                request_id=request.request_id,
            )
            raise ClaudeAPIError(
                str(e), getattr(e, "status_code", None)
            ) from e

        self._logger.info(
            "Claude API streaming completed",
            request_id=request.request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
