"""호출 시점 신원 헤더 주입 — client_factory / tool_adapter / call_client / registry.

Design Ref: mcp-identity-header §1.1 (단일 주입 지점·호출 시점 발급),
§6.2 (네트워크 전 실패), §8.2 (#6~#9, #12).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.mcp.value_objects import (
    MCPAuthConfig,
    MCPServerConfig,
    MCPTransport,
    SSEServerConfig,
    StdioServerConfig,
    StreamableHTTPServerConfig,
)
from src.domain.mcp.policy import MCPRetryPolicy
from src.domain.mcp_registry.identity import ClaimSource, IdentityUnavailableError
from src.infrastructure.mcp.call_client import MCPCallClient
from src.infrastructure.mcp.client_factory import MCPClientFactory
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from src.infrastructure.mcp.tool_registry import MCPToolRegistry

_FACTORY = "src.infrastructure.mcp.client_factory"


def _sse(headers=None) -> MCPServerConfig:
    return MCPServerConfig(
        name="mcp_srv", transport=MCPTransport.SSE,
        sse=SSEServerConfig(url="http://localhost:8006/sse", headers=headers),
    )


def _http(headers=None) -> MCPServerConfig:
    return MCPServerConfig(
        name="mcp_srv", transport=MCPTransport.STREAMABLE_HTTP,
        streamable_http=StreamableHTTPServerConfig(url="http://x/mcp", headers=headers),
    )


def _wire(mock_transport, yields):
    mock_transport.return_value.__aenter__ = AsyncMock(return_value=yields)
    mock_transport.return_value.__aexit__ = AsyncMock(return_value=None)


def _wire_session(mock_cls, session):
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)


def _provider(headers: dict):
    return AsyncMock(return_value=headers)


def _unavailable(reason="claim_empty"):
    return AsyncMock(side_effect=IdentityUnavailableError(reason, ClaimSource.MAILBOX_UPN))


class TestClientFactoryMerge:
    @pytest.mark.asyncio
    async def test_SSE에_발급_헤더를_싣는다(self):
        with patch(f"{_FACTORY}.sse_client") as sse, patch(f"{_FACTORY}.ClientSession") as cls:
            _wire(sse, (AsyncMock(), AsyncMock()))
            _wire_session(cls, AsyncMock())
            async with MCPClientFactory.create_session(
                _sse({"X-Static": "s"}), header_provider=_provider({"X-MCP-Identity": "tok"})
            ):
                pass
        headers = sse.call_args.kwargs["headers"]
        assert headers == {"X-Static": "s", "X-MCP-Identity": "tok"}

    @pytest.mark.asyncio
    async def test_발급_헤더가_정적_auth_헤더를_대소문자_무시하고_덮는다(self):
        """§7 — 정적 헤더로 같은 이름을 심어도 발급 값만 나간다."""
        with patch(f"{_FACTORY}.streamablehttp_client") as http, \
             patch(f"{_FACTORY}.ClientSession") as cls:
            _wire(http, (AsyncMock(), AsyncMock(), MagicMock()))
            _wire_session(cls, AsyncMock())
            async with MCPClientFactory.create_session(
                _http({"x-mcp-identity": "evil"}),
                auth=MCPAuthConfig(extra_headers={"X-MCP-IDENTITY": "evil2"}),
                header_provider=_provider({"X-MCP-Identity": "good"}),
            ):
                pass
        headers = http.call_args.kwargs["headers"]
        assert headers == {"X-MCP-Identity": "good"}

    @pytest.mark.asyncio
    async def test_공급자가_없으면_기존과_같다(self):
        """FR-08 — 미설정 서버는 헤더 dict 가 바뀌지 않는다."""
        with patch(f"{_FACTORY}.sse_client") as sse, patch(f"{_FACTORY}.ClientSession") as cls:
            _wire(sse, (AsyncMock(), AsyncMock()))
            _wire_session(cls, AsyncMock())
            async with MCPClientFactory.create_session(_sse({"X-Static": "s"})):
                pass
        assert sse.call_args.kwargs["headers"] == {"X-Static": "s"}

    @pytest.mark.asyncio
    async def test_신원_불가면_연결을_시도하지_않는다(self):
        with patch(f"{_FACTORY}.sse_client") as sse:
            with pytest.raises(IdentityUnavailableError):
                async with MCPClientFactory.create_session(
                    _sse(), header_provider=_unavailable()
                ):
                    pass
        sse.assert_not_called()

    @pytest.mark.asyncio
    async def test_HTTP가_아닌_transport에는_신원_헤더를_실을_수_없다(self):
        stdio = MCPServerConfig(
            name="s", transport=MCPTransport.STDIO,
            stdio=StdioServerConfig(command="python"),
        )
        with patch(f"{_FACTORY}.stdio_client") as client:
            with pytest.raises(ValueError):
                async with MCPClientFactory.create_session(
                    stdio, header_provider=_provider({"X-MCP-Identity": "t"})
                ):
                    pass
        client.assert_not_called()


def _adapter(provider=None) -> MCPToolAdapter:
    return MCPToolAdapter(
        name="mcp_srv_list_messages", description="d", server_config=_sse(),
        mcp_tool_name="list_messages", header_provider=provider,
    )


class TestToolAdapter:
    @pytest.mark.asyncio
    async def test_세션_생성에_공급자를_넘긴다(self):
        provider = _provider({"X-MCP-Identity": "t"})
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=MagicMock(content=[]))
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=None)
        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session",
            return_value=cm,
        ) as create:
            await _adapter(provider)._arun(arguments={"top": 3})
        assert create.call_args.kwargs["header_provider"] is provider

    @pytest.mark.asyncio
    async def test_신원_불가는_안내문을_도구_결과로_돌려준다(self):
        with patch(f"{_FACTORY}.sse_client") as sse:
            result = await _adapter(_unavailable())._arun(arguments={})
        assert "메일함이 등록되지 않았습니다" in result
        sse.assert_not_called()

    @pytest.mark.asyncio
    async def test_신원_불가는_경고_로그만_남기고_예외를_올리지_않는다(self):
        with patch("src.infrastructure.mcp.tool_adapter.logger") as log, \
             patch(f"{_FACTORY}.sse_client"):
            await _adapter(_unavailable("no_subject"))._arun(arguments={})
        log.warning.assert_called_once()
        assert log.warning.call_args.kwargs["reason"] == "no_subject"
        log.error.assert_not_called()


class TestCallClient:
    def _client(self, provider):
        return MCPCallClient(
            _sse(), retry=MCPRetryPolicy(max_retries=2), logger=MagicMock(),
            call_header_provider=provider,
        )

    @pytest.mark.asyncio
    async def test_call_tool만_공급자를_쓰고_list_tools는_쓰지_않는다(self):
        provider = _provider({"X-MCP-Identity": "t"})
        client = self._client(provider)
        session = AsyncMock()
        session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        session.call_tool = AsyncMock(return_value=MagicMock(content=[], isError=False))
        seen = []

        def fake_create(config, request_id, **kwargs):
            seen.append(kwargs.get("header_provider"))
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=session)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        with patch(
            "src.infrastructure.mcp.call_client.MCPClientFactory.create_session",
            side_effect=fake_create,
        ):
            await client.list_tools("r")
            await client.call_tool("send_mail", {}, "r")
        assert seen == [None, provider]

    @pytest.mark.asyncio
    async def test_신원_오류는_재시도하지_않는다(self):
        provider = _unavailable()
        with patch(f"{_FACTORY}.sse_client") as sse:
            with pytest.raises(IdentityUnavailableError):
                await self._client(provider).call_tool("send_mail", {}, "r")
        assert provider.await_count == 1
        sse.assert_not_called()


class TestRegistry:
    @pytest.mark.asyncio
    async def test_서버별_공급자를_어댑터에_붙인다(self):
        provider = _provider({"X-MCP-Identity": "t"})
        tool = MagicMock()
        tool.name = "list_messages"
        tool.description = "d"
        tool.inputSchema = {}
        session = AsyncMock()
        session.list_tools = AsyncMock(return_value=MagicMock(tools=[tool]))
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=None)
        with patch(
            "src.infrastructure.mcp.tool_registry.MCPClientFactory.create_session",
            return_value=cm,
        ) as create:
            tools = await MCPToolRegistry(
                [_sse()], header_providers={"mcp_srv": provider}
            ).get_tools("r")
        assert tools[0].header_provider is provider
        # 도구 목록 조회에는 신원을 싣지 않는다 (Plan Out of Scope).
        assert create.call_args.kwargs.get("header_provider") is None
