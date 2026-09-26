"""헤더 공급자 실패의 분류 — 신원 불가 외 실패도 '연결 전'임을 드러낸다.

mcp-identity-header Check G-2 / G-4.
- G-2: 서명 오류·배선 오류처럼 공급자 단계에서 난 실패는 HeaderProviderError 로
  감싸 호출자가 '서버에 보내지 않았다'를 알 수 있게 한다 (집행기 blocked).
- G-4: 신원 차단 WARN 로그에 실행 주체(identity_sub)를 남긴다.
"""
from unittest.mock import AsyncMock, patch

import pytest

from src.domain.mcp.policy import MCPRetryPolicy
from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, SSEServerConfig
from src.domain.mcp_registry.identity import ClaimSource, IdentityUnavailableError
from src.infrastructure.mcp.call_client import MCPCallClient
from src.infrastructure.mcp.client_factory import HeaderProviderError, MCPClientFactory
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

_FACTORY = "src.infrastructure.mcp.client_factory"


def _sse() -> MCPServerConfig:
    return MCPServerConfig(
        name="mcp_srv", transport=MCPTransport.SSE,
        sse=SSEServerConfig(url="http://localhost:8006/sse"),
    )


class TestProviderFailureWrapping:
    @pytest.mark.asyncio
    async def test_공급자의_일반_예외는_HeaderProviderError로_감싸고_연결하지_않는다(self):
        provider = AsyncMock(side_effect=RuntimeError("bad signing key"))
        with patch(f"{_FACTORY}.sse_client") as sse:
            with pytest.raises(HeaderProviderError) as e:
                async with MCPClientFactory.create_session(_sse(), header_provider=provider):
                    pass
        assert isinstance(e.value.__cause__, RuntimeError)
        sse.assert_not_called()

    @pytest.mark.asyncio
    async def test_신원_불가는_감싸지_않는다(self):
        provider = AsyncMock(side_effect=IdentityUnavailableError("no_subject"))
        with pytest.raises(IdentityUnavailableError):
            async with MCPClientFactory.create_session(_sse(), header_provider=provider):
                pass

    @pytest.mark.asyncio
    async def test_call_client는_공급자_실패를_재시도하지_않는다(self):
        provider = AsyncMock(side_effect=RuntimeError("boom"))
        client = MCPCallClient(
            _sse(), retry=MCPRetryPolicy(max_retries=3), call_header_provider=provider
        )
        with patch(f"{_FACTORY}.sse_client"):
            with pytest.raises(HeaderProviderError):
                await client.call_tool("send_mail", {}, "r")
        assert provider.await_count == 1


class TestBlockedLogSubject:
    @pytest.mark.asyncio
    async def test_신원_차단_로그에_주체가_남는다(self):
        err = IdentityUnavailableError("claim_empty", ClaimSource.MAILBOX_UPN, subject="8")
        adapter = MCPToolAdapter(
            name="mcp_srv_list_messages", description="d", server_config=_sse(),
            mcp_tool_name="list_messages", header_provider=AsyncMock(side_effect=err),
        )
        with patch("src.infrastructure.mcp.tool_adapter.logger") as log, \
             patch(f"{_FACTORY}.sse_client"):
            await adapter._arun(arguments={})
        assert log.warning.call_args.kwargs["identity_sub"] == "8"
