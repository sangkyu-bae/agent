"""MCPToolAdapter 플레이스홀더 인자 가드 테스트.

Design Ref: worker-context-injection §6.1 / §8.4 L3 #1~2 —
LLM이 지어낸 예시 URL은 MCP 서버에 도달하기 전에 차단되어야 한다.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def stdio_server_config():
    from src.domain.mcp.value_objects import (
        MCPServerConfig, MCPTransport, StdioServerConfig,
    )
    return MCPServerConfig(
        name="scrape_server",
        transport=MCPTransport.STDIO,
        stdio=StdioServerConfig(command="python", args=["server.py"]),
    )


@pytest.fixture
def adapter(stdio_server_config):
    from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
    return MCPToolAdapter(
        name="scrape_server_fetch",
        description="Fetch a web page",
        server_config=stdio_server_config,
        mcp_tool_name="fetch",
        request_id="req-1",
        tool_id="mcp:scrape_server:fetch",
    )


def _patched_session():
    """call_tool 을 감시하는 세션 목 컨텍스트."""
    mock_result = MagicMock()
    mock_result.content = [MagicMock(text="ok")]
    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=mock_result)
    ctx = patch(
        "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
    )
    return ctx, mock_session


class TestPlaceholderArgumentGuard:

    @pytest.mark.asyncio
    async def test_blocks_placeholder_url_without_calling_server(self, adapter):
        """재현 시나리오 — 서버 호출이 일어나지 않아야 한다."""
        ctx, mock_session = _patched_session()
        dummy = "https://www.example.com/financial-market-2026-09-03"

        with ctx as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await adapter._arun(arguments={"url": dummy})

        mock_session.call_tool.assert_not_called()
        assert dummy in result
        assert "차단" in result

    @pytest.mark.asyncio
    async def test_blocked_result_is_string_not_exception(self, adapter):
        """예외가 아닌 문자열이어야 워커가 자기 교정할 기회를 얻는다."""
        ctx, mock_session = _patched_session()

        with ctx as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await adapter._arun(arguments={"url": "https://example.org/x"})

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_blocks_placeholder_nested_in_arguments(self, adapter):
        ctx, mock_session = _patched_session()

        with ctx as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            await adapter._arun(
                arguments={"targets": [{"link": "https://example.net/a"}]}
            )

        mock_session.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_real_url_and_calls_server(self, adapter):
        """정상 인자는 기존 경로 그대로 통과한다."""
        ctx, mock_session = _patched_session()
        real = "https://finance.naver.com/marketindex"

        with ctx as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await adapter._arun(arguments={"url": real})

        mock_session.call_tool.assert_called_once_with(
            name="fetch", arguments={"url": real},
        )
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_allows_empty_arguments(self, adapter):
        ctx, mock_session = _patched_session()

        with ctx as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            await adapter._arun()

        mock_session.call_tool.assert_called_once_with(name="fetch", arguments={})

    @pytest.mark.asyncio
    async def test_logs_warning_with_tracking_fields_on_block(self, adapter):
        """§6.3 — 차단 사실이 관측 가능해야 재발을 추적할 수 있다."""
        ctx, mock_session = _patched_session()

        with ctx as mock_ctx, patch(
            "src.infrastructure.mcp.tool_adapter.logger"
        ) as mock_logger:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            await adapter._arun(arguments={"url": "https://example.com/x"})

        mock_logger.warning.assert_called_once()
        _, kwargs = mock_logger.warning.call_args
        assert kwargs["request_id"] == "req-1"
        assert kwargs["tool_id"] == "mcp:scrape_server:fetch"
        assert kwargs["server"] == "scrape_server"
        assert kwargs["tool"] == "fetch"
        assert kwargs["reason"] == "placeholder_url"
        assert kwargs["blocked_value"] == "https://example.com/x"


class TestBlockDoesNotLoop:
    """GAP-03 / Design §8.4 #3 — 차단이 반복돼도 루프·예외 없이 종료된다."""

    @pytest.mark.asyncio
    async def test_repeated_blocks_never_reach_server(self, adapter):
        ctx, mock_session = _patched_session()

        with ctx as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            results = [
                await adapter._arun(arguments={"url": f"https://example.com/{i}"})
                for i in range(3)
            ]

        mock_session.call_tool.assert_not_called()
        assert len(results) == 3
        assert all(isinstance(r, str) and r for r in results)

    @pytest.mark.asyncio
    async def test_worker_can_recover_after_block(self, adapter):
        """차단은 종착이 아니다 — 교정된 인자는 정상적으로 서버에 도달한다."""
        ctx, mock_session = _patched_session()
        real = "https://finance.naver.com/marketindex"

        with ctx as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            blocked = await adapter._arun(arguments={"url": "https://example.com/x"})
            recovered = await adapter._arun(arguments={"url": real})

        assert "차단" in blocked
        assert recovered == "ok"
        mock_session.call_tool.assert_called_once_with(
            name="fetch", arguments={"url": real},
        )
