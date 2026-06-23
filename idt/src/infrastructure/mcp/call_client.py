"""MCP Call Client.

LangChain 비의존 순수 MCP 호출 코어. 호출당 stateless 세션을 생성하고
재시도 정책으로 감싸 list_tools()/call_tool()을 제공한다.
timeout·auth·retry·logger를 생성자 주입으로 받는다.
infrastructure 레이어 — 비즈니스 규칙 없음.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import uuid4

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp.policy import MCPRetryPolicy
from src.domain.mcp.value_objects import (
    MCPAuthConfig,
    MCPServerConfig,
    MCPTimeoutConfig,
    MCPToolDescriptor,
    MCPToolResult,
)
from src.infrastructure.logging import get_logger
from src.infrastructure.mcp.client_factory import MCPClientFactory

T = TypeVar("T")


def _extract_content(result: Any) -> str:
    """MCP 실행 결과에서 텍스트 콘텐츠를 추출한다."""
    if hasattr(result, "content") and result.content:
        parts = []
        for item in result.content:
            if hasattr(item, "text"):
                parts.append(item.text)
            elif hasattr(item, "data"):
                parts.append(str(item.data))
        return "\n".join(parts)
    return ""


def _to_descriptor(tool: Any) -> MCPToolDescriptor:
    """SDK tool 객체를 도메인 MCPToolDescriptor VO로 변환한다."""
    return MCPToolDescriptor(
        name=tool.name,
        description=getattr(tool, "description", "") or "",
        input_schema=getattr(tool, "inputSchema", {}) or {},
    )


class MCPCallClient:
    """순수 MCP 호출 코어 (async-first)."""

    def __init__(
        self,
        config: MCPServerConfig,
        *,
        timeout: MCPTimeoutConfig | None = None,
        auth: MCPAuthConfig | None = None,
        retry: MCPRetryPolicy | None = None,
        logger: LoggerInterface | None = None,
    ) -> None:
        self._config = config
        self._timeout = timeout or MCPTimeoutConfig()
        self._auth = auth
        self._retry = retry or MCPRetryPolicy()
        self._logger = logger or get_logger(__name__)

    async def list_tools(
        self, request_id: str | None = None
    ) -> list[MCPToolDescriptor]:
        """설정된 서버의 tool 목록을 조회한다 (멱등 → operation 재시도 허용)."""
        request_id = request_id or uuid4().hex

        async def _op(session) -> list[MCPToolDescriptor]:
            result = await session.list_tools()
            return [_to_descriptor(tool) for tool in result.tools]

        return await self._execute(
            _op, "list_tools", retry_operation=True, request_id=request_id
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        request_id: str | None = None,
    ) -> MCPToolResult:
        """tool을 실행한다. 도구 논리 에러는 예외 대신 is_error 결과로 반환한다."""
        request_id = request_id or uuid4().hex

        async def _op(session) -> MCPToolResult:
            raw = await session.call_tool(name=name, arguments=arguments)
            return self._to_tool_result(name, raw, request_id)

        return await self._execute(
            _op,
            name,
            retry_operation=self._retry.retry_tool_execution,
            request_id=request_id,
        )

    def _to_tool_result(self, name: str, raw: Any, request_id: str) -> MCPToolResult:
        is_error = bool(getattr(raw, "isError", False))
        if is_error:
            self._logger.warning(
                "MCP tool returned error result",
                request_id=request_id,
                server=self._config.name,
                tool=name,
            )
        return MCPToolResult(
            tool_name=name,
            server_name=self._config.name,
            content=_extract_content(raw),
            is_error=is_error,
        )

    async def _execute(
        self,
        operation: Callable[[Any], Awaitable[T]],
        label: str,
        *,
        retry_operation: bool,
        request_id: str,
    ) -> T:
        """세션 생성 → operation 실행을 재시도 정책으로 감싼다."""
        log_extra = {
            "request_id": request_id,
            "server": self._config.name,
            "tool": label,
        }
        self._logger.info("MCP call started", **log_extra)

        attempt = 0
        while True:
            connected = False
            started = time.perf_counter()
            try:
                async with MCPClientFactory.create_session(
                    self._config,
                    request_id,
                    timeout=self._timeout,
                    auth=self._auth,
                ) as session:
                    connected = True
                    result = await asyncio.wait_for(
                        operation(session), timeout=self._timeout.total
                    )
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                self._logger.info(
                    "MCP call completed", elapsed_ms=elapsed_ms, **log_extra
                )
                return result
            except Exception as e:
                if self._should_retry(e, connected, retry_operation, attempt):
                    backoff = self._retry.compute_backoff(attempt)
                    self._logger.warning(
                        "MCP call retrying",
                        attempt=attempt,
                        backoff=backoff,
                        error=str(e),
                        **log_extra,
                    )
                    await asyncio.sleep(backoff)
                    attempt += 1
                    continue
                self._logger.error("MCP call failed", exception=e, **log_extra)
                raise

    def _should_retry(
        self,
        exc: Exception,
        connected: bool,
        retry_operation: bool,
        attempt: int,
    ) -> bool:
        """재시도 여부 판단.

        연결 단계 실패는 항상 재시도 후보, operation 단계 실패는 retry_operation일 때만.
        """
        stage_retryable = retry_operation if connected else True
        return (
            stage_retryable
            and self._retry.is_retryable(exc)
            and attempt < self._retry.max_retries
        )
