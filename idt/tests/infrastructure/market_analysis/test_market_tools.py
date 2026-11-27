"""PlatformMarketTools — MCP 도구 직접 호출 · 뉴스 어댑터 (design §4 ②, U13)."""

from __future__ import annotations

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
    tools, _ = _tools(FakeClient(fail=TimeoutError("slow")))
    out = await _call(tools)
    assert out.is_error and out.error_code == "TOOL_CALL_FAILED"


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
