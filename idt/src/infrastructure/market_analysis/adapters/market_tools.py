"""MCP 시장 도구 직접 호출 · 뉴스 어댑터 (application.ports.MarketTools 구현).

Design Ref: stock-analysis-agents §4 ②, DD7, §11 — LLM 을 거치지 않는 prefetch 경로.
- 허용목록(domain.tool_policy) 밖 도구는
**서버를 찾기도 전에** 거부한다 (주문 도구 차단)
- 레지스트리에서 서버를 찾고, 실행자 신원 헤더를 단
`MCPCallClient.call_tool` 을 1회 호출 (승인 집행기와 같은 코어)
- MCP 서버 오류 `"{CODE}: 설명"` 의 코드를 살린다.
실패는 예외가 아니라 `ToolOutcome(is_error=True)`
- 뉴스는 플랫폼 Tavily(`topic="news"`)를 쓴다 — 동기 함수라 스레드로 돌린다
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.runtime import ToolOutcome, ToolSource
from src.domain.market_analysis.tool_policy import (
    ToolNotAllowedError,
    ToolPolicy,
    parse_error_code,
)

ServerFinder = Callable[[str, str], Awaitable[Any]]
ClientFactory = Callable[[Any, str, str], Any]

# 서버 하나에 동시에 여는 MCP 세션 수. 2026-11-27 회차에서 종목 2개 × 호출 4개가
# 한꺼번에 SSE 세션을 열어 연결 단계 실패가 났다. 실측상 서버는 요청을 거의 하나씩
# 처리해 동시 세션을 늘려도 빨라지지 않는다.
DEFAULT_MAX_CONCURRENT_PER_SERVER = 3


class PlatformMarketTools:
    def __init__(
        self,
        *,
        server_finder: ServerFinder,
        client_factory: ClientFactory,
        news_search: Callable[..., str],
        logger: LoggerInterface,
        max_concurrent_per_server: int = DEFAULT_MAX_CONCURRENT_PER_SERVER,
    ) -> None:
        self._find = server_finder
        self._client_factory = client_factory
        self._news_search = news_search
        self._logger = logger
        self._slot_limit = max(1, max_concurrent_per_server)
        self._slots: dict[str, asyncio.Semaphore] = {}

    def _slot(self, server_id: str) -> asyncio.Semaphore:
        slot = self._slots.get(server_id)
        if slot is None:
            slot = self._slots[server_id] = asyncio.Semaphore(self._slot_limit)
        return slot

    async def call(
        self,
        *,
        source: ToolSource,
        server_id: str,
        tool: str,
        args: dict[str, Any],
        run_as_user_id: str,
        request_id: str,
    ) -> ToolOutcome:
        def fail(code: str, text: str = "") -> ToolOutcome:
            return ToolOutcome(
                source=source,
                tool=tool,
                args=args,
                text=text,
                is_error=True,
                error_code=code,
            )

        try:
            ToolPolicy.check(source, tool)
        except ToolNotAllowedError:
            self._logger.warning(
                "market_analysis tool refused",
                request_id=request_id,
                tool=f"{source}:{tool}",
            )
            return fail(
                "TOOL_NOT_ALLOWED", f"허용되지 않은 도구: {source.value}:{tool}"
            )

        try:
            registration = await self._find(server_id, request_id)
        except Exception as e:  # noqa: BLE001 — 조회 실패도 값으로 (포트 계약, G7)
            self._logger.warning(
                "market_analysis server lookup failed",
                exception=e,
                request_id=request_id,
                server_id=server_id,
            )
            return fail(
                "SERVER_UNAVAILABLE",
                f"MCP 서버 조회 실패: {type(e).__name__}: {str(e)[:200]}",
            )
        if registration is None or not getattr(registration, "is_active", False):
            return fail("SERVER_UNAVAILABLE", f"MCP 서버를 쓸 수 없습니다: {server_id}")

        try:
            client = self._client_factory(registration, run_as_user_id, request_id)
            async with self._slot(server_id):
                result = await client.call_tool(tool, args, request_id)
        except Exception as e:  # noqa: BLE001 — 전송 실패도 값으로 돌려준다
            self._logger.warning(
                "market_analysis tool call failed",
                exception=e,
                request_id=request_id,
                tool=f"{source}:{tool}",
            )
            cause = _root_cause(e)
            timed_out = isinstance(cause, TimeoutError)
            code = "TOOL_TIMEOUT" if timed_out else "TOOL_CALL_FAILED"
            return fail(code, f"{type(cause).__name__}: {str(cause)[:200]}")

        text = str(getattr(result, "content", "") or "")
        if getattr(result, "is_error", False):
            return fail(parse_error_code(text) or "TOOL_ERROR", text)
        payload = _json_or_none(text)
        return ToolOutcome(
            source=source,
            tool=tool,
            args=args,
            payload=payload,
            text=text,
            cost_usd=_reported_cost(payload),
        )

    async def news(
        self, *, query: str, days: int, max_results: int, request_id: str
    ) -> ToolOutcome:
        args = {"query": query, "days": days, "max_results": max_results}
        try:
            text = await asyncio.to_thread(
                self._news_search,
                query=query,
                request_id=request_id,
                topic="news",
                days=days,
                max_results=max_results,
            )
        except Exception as e:  # noqa: BLE001
            self._logger.warning(
                "market_analysis news search failed", exception=e, request_id=request_id
            )
            return ToolOutcome(
                source=ToolSource.TAVILY,
                tool="search",
                args=args,
                text=f"{type(e).__name__}",
                is_error=True,
                error_code="NEWS_UNAVAILABLE",
            )
        return ToolOutcome(
            source=ToolSource.TAVILY,
            tool="search",
            args=args,
            payload=_json_or_none(text),
            text=text,
        )


def _root_cause(exc: BaseException) -> BaseException:
    """MCP SDK 는 anyio TaskGroup 안에서 돌아 원인이 ExceptionGroup 으로 감싸인다.
    근거에 껍데기 이름만 남으면 원인을 알 수 없다 — 첫 안쪽 예외까지 내려간다."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def _json_or_none(text: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _reported_cost(payload: Any) -> Decimal:
    """Perplexity `research` 응답의 usage.cost_usd (추정치). 없으면 0."""
    if not isinstance(payload, dict):
        return Decimal("0")
    usage = payload.get("usage")
    value = usage.get("cost_usd") if isinstance(usage, dict) else None
    try:
        return Decimal(str(value)) if value is not None else Decimal("0")
    except InvalidOperation:
        return Decimal("0")
