"""MCPCallClient 테스트 — Mock 세션 사용, 네트워크 비의존."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _server_config():
    from src.domain.mcp.value_objects import (
        MCPServerConfig,
        MCPTransport,
        StreamableHTTPServerConfig,
    )
    return MCPServerConfig(
        name="http_server",
        transport=MCPTransport.STREAMABLE_HTTP,
        streamable_http=StreamableHTTPServerConfig(url="http://localhost:8080/mcp"),
    )


@asynccontextmanager
async def _ok_cm(session):
    yield session


@asynccontextmanager
async def _fail_cm(exc):
    raise exc
    yield  # pragma: no cover


class TestMCPCallClientCallTool:

    @pytest.mark.asyncio
    async def test_call_tool_happy_path(self):
        from src.infrastructure.mcp.call_client import MCPCallClient, MCPClientFactory

        session = AsyncMock()
        result = SimpleNamespace(content=[SimpleNamespace(text="hello")], isError=False)
        session.call_tool = AsyncMock(return_value=result)

        client = MCPCallClient(_server_config())
        with patch.object(MCPClientFactory, "create_session", return_value=_ok_cm(session)):
            out = await client.call_tool("read_file", {"path": "/x"}, "req-1")

        assert out.tool_name == "read_file"
        assert out.server_name == "http_server"
        assert out.content == "hello"
        assert out.is_error is False
        session.call_tool.assert_awaited_once_with(name="read_file", arguments={"path": "/x"})

    @pytest.mark.asyncio
    async def test_call_tool_returns_error_result_without_raising(self):
        from src.infrastructure.mcp.call_client import MCPCallClient, MCPClientFactory

        session = AsyncMock()
        result = SimpleNamespace(content=[SimpleNamespace(text="not found")], isError=True)
        session.call_tool = AsyncMock(return_value=result)

        client = MCPCallClient(_server_config())
        with patch.object(MCPClientFactory, "create_session", return_value=_ok_cm(session)):
            out = await client.call_tool("read_file", {}, "req-2")

        assert out.is_error is True
        assert out.content == "not found"

    @pytest.mark.asyncio
    async def test_call_tool_retries_then_succeeds(self):
        from src.domain.mcp.policy import MCPRetryPolicy
        from src.infrastructure.mcp.call_client import MCPCallClient, MCPClientFactory

        session = AsyncMock()
        result = SimpleNamespace(content=[SimpleNamespace(text="ok")], isError=False)
        session.call_tool = AsyncMock(return_value=result)

        retry = MCPRetryPolicy(max_retries=2, base_backoff=0.01)
        client = MCPCallClient(_server_config(), retry=retry)

        cms = [
            _fail_cm(ConnectionError("net")),
            _fail_cm(ConnectionError("net")),
            _ok_cm(session),
        ]
        with patch.object(MCPClientFactory, "create_session", side_effect=cms) as mock_cs, \
             patch("src.infrastructure.mcp.call_client.asyncio.sleep", new=AsyncMock()):
            out = await client.call_tool("read_file", {}, "req-3")

        assert out.content == "ok"
        assert mock_cs.call_count == 3

    @pytest.mark.asyncio
    async def test_call_tool_raises_after_exhausting_retries(self):
        from src.domain.mcp.policy import MCPRetryPolicy
        from src.infrastructure.mcp.call_client import MCPCallClient, MCPClientFactory

        retry = MCPRetryPolicy(max_retries=2, base_backoff=0.01)
        client = MCPCallClient(_server_config(), retry=retry)

        cms = [_fail_cm(ConnectionError("net")) for _ in range(3)]
        with patch.object(MCPClientFactory, "create_session", side_effect=cms) as mock_cs, \
             patch("src.infrastructure.mcp.call_client.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(ConnectionError):
                await client.call_tool("read_file", {}, "req-4")

        assert mock_cs.call_count == 3  # 1 + 2 retries

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self):
        from src.domain.mcp.policy import MCPRetryPolicy
        from src.infrastructure.mcp.call_client import MCPCallClient, MCPClientFactory

        retry = MCPRetryPolicy(max_retries=3, base_backoff=0.01)
        client = MCPCallClient(_server_config(), retry=retry)

        cms = [_fail_cm(ValueError("bad config"))]
        with patch.object(MCPClientFactory, "create_session", side_effect=cms) as mock_cs, \
             patch("src.infrastructure.mcp.call_client.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(ValueError):
                await client.call_tool("read_file", {}, "req-5")

        assert mock_cs.call_count == 1  # no retry for non-retryable

    @pytest.mark.asyncio
    async def test_tool_execution_error_not_retried_by_default(self):
        """연결은 성공하나 tool 실행이 ConnectionError → 기본은 재시도 안 함."""
        from src.domain.mcp.policy import MCPRetryPolicy
        from src.infrastructure.mcp.call_client import MCPCallClient, MCPClientFactory

        session = AsyncMock()
        session.call_tool = AsyncMock(side_effect=ConnectionError("mid-call"))

        retry = MCPRetryPolicy(max_retries=3, base_backoff=0.01, retry_tool_execution=False)
        client = MCPCallClient(_server_config(), retry=retry)

        # 매 호출마다 정상 연결되는 세션 제공
        with patch.object(
            MCPClientFactory, "create_session", side_effect=lambda *a, **k: _ok_cm(session)
        ) as mock_cs, \
             patch("src.infrastructure.mcp.call_client.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(ConnectionError):
                await client.call_tool("read_file", {}, "req-6")

        assert mock_cs.call_count == 1  # tool-stage 실패는 재시도 안 함


class TestMCPCallClientListTools:

    @pytest.mark.asyncio
    async def test_list_tools_returns_descriptors(self):
        from src.infrastructure.mcp.call_client import MCPCallClient, MCPClientFactory

        session = AsyncMock()
        tools = SimpleNamespace(
            tools=[
                SimpleNamespace(name="read", description="read file", inputSchema={"type": "object"}),
                SimpleNamespace(name="write", description="", inputSchema={}),
            ]
        )
        session.list_tools = AsyncMock(return_value=tools)

        client = MCPCallClient(_server_config())
        with patch.object(MCPClientFactory, "create_session", return_value=_ok_cm(session)):
            out = await client.list_tools("req-7")

        assert len(out) == 2
        assert out[0].name == "read"
        assert out[0].description == "read file"
        assert out[0].input_schema == {"type": "object"}
        assert out[1].name == "write"
