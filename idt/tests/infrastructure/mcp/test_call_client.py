"""MCPCallClient 테스트 — Mock 세션 사용, 네트워크 비의존."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import anyio
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


# ── 호출 전체 상한 (연결·초기화·실행·종료) ─────────────────────────────
# 2026-11-27 시장 분석 회차: SSE 세션 초기화가 응답 없이 멈춰 회차가 끝나지 않았다.
# total 은 실행(operation)에만 걸려 있었다 — 호출 한 건 전체에 건다.


@asynccontextmanager
async def _hang_on_enter_cm():
    await asyncio.Event().wait()  # 연결·initialize 가 영영 안 끝남
    yield  # pragma: no cover


@asynccontextmanager
async def _hang_on_exit_cm(session):
    yield session
    await asyncio.Event().wait()  # 세션 정리가 영영 안 끝남


@asynccontextmanager
async def _anyio_hang_cm():
    """실제 SDK 처럼 anyio TaskGroup 안에서 initialize 가 멈추는 세션."""
    async with anyio.create_task_group() as tg:
        tg.start_soon(anyio.sleep_forever)  # SSE 읽기 루프 자리
        await anyio.sleep_forever()  # initialize 응답 대기 자리
        yield  # pragma: no cover


async def _guard(coro):
    """바깥 보호 — 클라이언트가 상한을 못 지키면 TimeoutError 가 아닌
    테스트 실패로 드러낸다."""
    task = asyncio.ensure_future(coro)
    done, _ = await asyncio.wait({task}, timeout=3)
    if not done:
        task.cancel()
        pytest.fail("MCPCallClient 가 total 상한 안에 끝나지 않았다 (멈춤)")
    return task.result()


def _short_client(max_retries: int = 0):
    from src.domain.mcp.policy import MCPRetryPolicy
    from src.domain.mcp.value_objects import MCPTimeoutConfig
    from src.infrastructure.mcp.call_client import MCPCallClient

    return MCPCallClient(
        _server_config(),
        timeout=MCPTimeoutConfig(connect=0.1, read=0.1, total=0.2),
        retry=MCPRetryPolicy(max_retries=max_retries, base_backoff=0.01),
    )


class TestMCPCallClientTotalTimeout:

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cm_factory",
        [
            lambda: _hang_on_enter_cm(),
            lambda: _anyio_hang_cm(),
        ],
        ids=["plain", "anyio-taskgroup"],
    )
    async def test_session_setup_hang_raises_timeout(self, cm_factory):
        from src.infrastructure.mcp.call_client import MCPClientFactory

        client = _short_client()
        with patch.object(
            MCPClientFactory, "create_session", side_effect=lambda *a, **k: cm_factory()
        ):
            with pytest.raises(TimeoutError):
                await _guard(client.call_tool("t", {}, "req-h1"))

    @pytest.mark.asyncio
    async def test_session_teardown_hang_raises_timeout(self):
        from src.infrastructure.mcp.call_client import MCPClientFactory

        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=SimpleNamespace(content=[], isError=False)
        )
        client = _short_client()
        with patch.object(
            MCPClientFactory,
            "create_session",
            side_effect=lambda *a, **k: _hang_on_exit_cm(session),
        ):
            with pytest.raises(TimeoutError):
                await _guard(client.call_tool("t", {}, "req-h2"))

    @pytest.mark.asyncio
    async def test_setup_timeout_is_retried_as_connection_stage(self):
        from src.infrastructure.mcp.call_client import MCPClientFactory

        client = _short_client(max_retries=1)
        with patch.object(
            MCPClientFactory,
            "create_session",
            side_effect=lambda *a, **k: _hang_on_enter_cm(),
        ) as mock_cs:
            with pytest.raises(TimeoutError):
                await _guard(client.call_tool("t", {}, "req-h3"))
        assert mock_cs.call_count == 2  # 연결 단계 상한 초과는 재시도 후보

    @pytest.mark.asyncio
    async def test_slow_operation_still_bounded_by_total(self):
        from src.infrastructure.mcp.call_client import MCPClientFactory

        session = AsyncMock()

        async def slow(**kwargs):
            await asyncio.Event().wait()

        session.call_tool = slow
        client = _short_client()
        with patch.object(
            MCPClientFactory,
            "create_session",
            side_effect=lambda *a, **k: _ok_cm(session),
        ):
            with pytest.raises(TimeoutError):
                await _guard(client.call_tool("t", {}, "req-h4"))
