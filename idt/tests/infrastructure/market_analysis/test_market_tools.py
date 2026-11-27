"""PlatformMarketTools — MCP 도구 직접 호출 · 뉴스 어댑터 (design §4 ②, U13)."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.domain.market_analysis.runtime import ToolSource
from src.infrastructure.market_analysis.adapters.market_tools import PlatformMarketTools


class FakeClient:
    def __init__(
        self, content: str = "{}", is_error: bool = False, fail: Exception | None = None
    ):
        self.calls: list[tuple[str, dict]] = []
        self.content = content
        self.is_error = is_error
        self.fail = fail

    async def call_tool(self, name, arguments, request_id=None):
        self.calls.append((name, arguments))
        if self.fail:
            raise self.fail
        return SimpleNamespace(content=self.content, is_error=self.is_error)


def _tools(client: FakeClient, *, active: bool = True, found: bool = True, news=None):
    made: list[tuple] = []

    async def find(server_id, request_id):
        return SimpleNamespace(id=server_id, is_active=active) if found else None

    def factory(registration, subject_user_id, request_id):
        made.append((registration.id, subject_user_id))
        return client

    def search(**kwargs):
        if news is None:
            raise RuntimeError("tavily down")
        return news(**kwargs)

    return PlatformMarketTools(
        server_finder=find,
        client_factory=factory,
        news_search=search,
        logger=MagicMock(),
    ), made


async def _call(tools, tool="get_quote", source=ToolSource.KIS):
    return await tools.call(
        source=source,
        server_id="kis-1",
        tool=tool,
        args={"symbol": "005930"},
        run_as_user_id="7",
        request_id="r",
    )


async def test_calls_mcp_and_parses_json():
    client = FakeClient(json.dumps({"symbol": "005930", "price": "70000"}))
    tools, made = _tools(client)
    out = await _call(tools)
    assert client.calls == [("get_quote", {"symbol": "005930"})]
    assert made == [("kis-1", "7")]  # 실행자 신원으로 연결 (mcp-identity-header)
    assert out.payload == {"symbol": "005930", "price": "70000"}
    assert out.is_error is False and out.source is ToolSource.KIS


async def test_order_tool_is_refused_before_any_connection():
    client = FakeClient()
    tools, made = _tools(client)
    out = await _call(tools, tool="place_order")
    assert out.is_error and out.error_code == "TOOL_NOT_ALLOWED"
    assert made == [] and client.calls == []


async def test_missing_or_inactive_server():
    for kwargs in ({"found": False}, {"active": False}):
        client = FakeClient()
        tools, _ = _tools(client, **kwargs)
        out = await _call(tools)
        assert out.is_error and out.error_code == "SERVER_UNAVAILABLE"
        assert client.calls == []


async def test_tool_error_keeps_the_server_code():
    client = FakeClient(
        "Error executing tool get_quote: RATE_LIMITED: 한도 초과", is_error=True
    )
    tools, _ = _tools(client)
    out = await _call(tools)
    assert out.is_error and out.error_code == "RATE_LIMITED"
    assert "한도 초과" in out.text


async def test_server_lookup_failure_is_an_outcome_not_an_exception_g7():
    """G7 — 레지스트리 조회(DB) 예외도 포트 계약대로 값으로 돌려준다."""

    async def broken_find(server_id, request_id):
        raise ConnectionError("db down")

    client = FakeClient()
    tools = PlatformMarketTools(
        server_finder=broken_find,
        client_factory=lambda *a: client,
        news_search=lambda **k: "",
        logger=MagicMock(),
    )
    out = await _call(tools)
    assert out.is_error and out.error_code == "SERVER_UNAVAILABLE"
    assert "ConnectionError" in out.text
    assert client.calls == []


async def test_transport_failure_is_an_outcome_not_an_exception():
    tools, _ = _tools(FakeClient(fail=ConnectionError("refused")))
    out = await _call(tools)
    assert out.is_error and out.error_code == "TOOL_CALL_FAILED"
    assert out.text.startswith("ConnectionError: refused")


async def test_timeout_is_its_own_code():
    """호출 전체 상한(MCPCallClient total) 초과는 TOOL_TIMEOUT 으로 구분한다."""
    tools, _ = _tools(FakeClient(fail=TimeoutError()))
    out = await _call(tools)
    assert out.is_error and out.error_code == "TOOL_TIMEOUT"
    assert "TimeoutError" in out.text


async def test_exception_group_records_the_inner_cause():
    """MCP SDK 는 anyio TaskGroup 안에서 돌아 원인이 ExceptionGroup 으로 감싸인다.
    근거에는 껍데기가 아닌 안쪽 예외를 남긴다 (2026-11-27 지씨지놈 근거 3건)."""
    nested = ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [ExceptionGroup("inner", [ConnectionError("peer closed")])],
    )
    tools, _ = _tools(FakeClient(fail=nested))
    out = await _call(tools)
    assert out.error_code == "TOOL_CALL_FAILED"
    assert out.text.startswith("ConnectionError: peer closed")
    assert "ExceptionGroup" not in out.text


async def test_exception_group_wrapping_timeout_is_a_timeout():
    group = ExceptionGroup("tg", [TimeoutError()])
    tools, _ = _tools(FakeClient(fail=group))
    out = await _call(tools)
    assert out.error_code == "TOOL_TIMEOUT"


class _GatedClient:
    """동시에 몇 개가 call_tool 안에 있는지 센다."""

    def __init__(self):
        self.active = 0
        self.peak = 0
        self.release = asyncio.Event()

    async def call_tool(self, name, arguments, request_id=None):
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await self.release.wait()
            return SimpleNamespace(content="{}", is_error=False)
        finally:
            self.active -= 1


def _gated_tools(client, limit: int):
    async def find(server_id, request_id):
        return SimpleNamespace(id=server_id, is_active=True)

    return PlatformMarketTools(
        server_finder=find,
        client_factory=lambda *a: client,
        news_search=lambda **k: "",
        logger=MagicMock(),
        max_concurrent_per_server=limit,
    )


async def _call_on(tools, server_id):
    return await tools.call(
        source=ToolSource.KIS,
        server_id=server_id,
        tool="get_quote",
        args={"symbol": "005930"},
        run_as_user_id="7",
        request_id="r",
    )


async def test_concurrent_calls_to_one_server_are_capped():
    """2026-11-27: 종목 2개 × 서버당 호출 4개가 한꺼번에 SSE 세션을 열어 연결 실패가
    났다. 같은 서버로 동시에 여는 세션 수를 제한한다."""
    client = _GatedClient()
    tools = _gated_tools(client, limit=2)
    tasks = [asyncio.ensure_future(_call_on(tools, "kis-1")) for _ in range(6)]
    for _ in range(20):
        await asyncio.sleep(0)
    assert client.active == 2
    client.release.set()
    outs = await asyncio.gather(*tasks)
    assert client.peak == 2
    assert all(not o.is_error for o in outs)


async def test_cap_is_per_server():
    client = _GatedClient()
    tools = _gated_tools(client, limit=1)
    tasks = [
        asyncio.ensure_future(_call_on(tools, sid)) for sid in ("kis-1", "dart-1")
    ]
    for _ in range(20):
        await asyncio.sleep(0)
    assert client.active == 2  # 서버가 다르면 서로 기다리지 않는다
    client.release.set()
    await asyncio.gather(*tasks)


async def test_slot_is_released_after_failure():
    tools = _gated_tools(FakeClient(fail=ConnectionError("x")), limit=1)
    for _ in range(3):  # 실패가 자리를 잡고 있으면 두 번째부터 영영 멈춘다
        out = await asyncio.wait_for(_call_on(tools, "kis-1"), 1)
        assert out.error_code == "TOOL_CALL_FAILED"


async def test_non_json_text_is_kept_as_text():
    tools, _ = _tools(FakeClient("plain text"))
    out = await _call(tools)
    assert out.payload is None and out.text == "plain text" and not out.is_error


async def test_perplexity_cost_is_lifted_from_usage():
    body = {"answer": "a", "sources": [], "usage": {"cost_usd": 0.0042}}
    tools, _ = _tools(FakeClient(json.dumps(body)))
    out = await _call(tools, tool="research", source=ToolSource.PERPLEXITY)
    assert out.cost_usd == Decimal("0.0042")


async def test_news_uses_tavily_news_topic():
    seen = {}

    def news(**kwargs):
        seen.update(kwargs)
        return json.dumps([{"title": "t", "url": "https://n/1"}])

    tools, _ = _tools(FakeClient(), news=news)
    out = await tools.news(query="삼성전자 주가", days=7, max_results=5, request_id="r")
    assert seen["topic"] == "news" and seen["days"] == 7 and seen["max_results"] == 5
    assert out.source is ToolSource.TAVILY and out.payload[0]["url"] == "https://n/1"


async def test_news_failure_is_an_outcome():
    tools, _ = _tools(FakeClient(), news=None)
    out = await tools.news(query="q", days=7, max_results=5, request_id="r")
    assert out.is_error and out.error_code == "NEWS_UNAVAILABLE"
