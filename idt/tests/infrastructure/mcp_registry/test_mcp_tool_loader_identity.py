"""MCPToolLoader — 실행 주체를 받아 신원 헤더 공급자를 도구에 연결한다.

Design Ref: mcp-identity-header §2.1, §8.2 (#10). 미설정 서버는 공급자가 없다
(FR-08). 신원이 필요한 서버인데 공급자 팩토리가 배선되지 않았으면 헤더 없이
보내지 않고 호출 시점에 배선 오류로 실패한다.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.mcp_registry.identity import IdentityHeaderConfig
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.infrastructure.mcp_registry.mcp_tool_loader import (
    McpIdentityWiringError,
    MCPToolLoader,
)

_NOW = datetime(2026, 9, 26)
_REGISTRY = "src.infrastructure.mcp_registry.mcp_tool_loader.MCPToolRegistry"


def _registration(identity: bool) -> MCPServerRegistration:
    cfg = (
        IdentityHeaderConfig.from_dict({"audience": "a", "secret": "k" * 40})
        if identity else None
    )
    return MCPServerRegistration(
        id="srv-1", user_id="7", name="Outlook", description="d",
        endpoint="http://localhost:8006/sse", transport=MCPTransportType.SSE,
        input_schema=None, is_active=True, created_at=_NOW, updated_at=_NOW,
        identity_config=cfg,
    )


def _patched_registry():
    registry = MagicMock()
    registry.get_tools = AsyncMock(return_value=[])
    return patch(_REGISTRY, return_value=registry)


class TestLoad:
    @pytest.mark.asyncio
    async def test_미설정_서버는_공급자_없이_로드한다(self):
        headers = MagicMock()
        loader = MCPToolLoader(logger=MagicMock(), identity_headers=headers)
        with _patched_registry() as registry_cls:
            await loader.load(_registration(identity=False), "r", subject_user_id="7")
        assert registry_cls.call_args.kwargs["header_providers"] == {"mcp_srv-1": None}
        headers.for_registration.assert_not_called()

    @pytest.mark.asyncio
    async def test_신원_서버는_주체로_공급자를_만들어_넘긴다(self):
        provider = AsyncMock()
        headers = MagicMock()
        headers.for_registration = MagicMock(return_value=provider)
        loader = MCPToolLoader(logger=MagicMock(), identity_headers=headers)
        registration = _registration(identity=True)
        with _patched_registry() as registry_cls:
            await loader.load(registration, "req-1", subject_user_id="7")
        headers.for_registration.assert_called_once_with(registration, "7", "req-1")
        assert registry_cls.call_args.kwargs["header_providers"] == {"mcp_srv-1": provider}

    @pytest.mark.asyncio
    async def test_팩토리_미배선이면_호출_시점에_배선_오류(self):
        loader = MCPToolLoader(logger=MagicMock())
        with _patched_registry() as registry_cls:
            await loader.load(_registration(identity=True), "r", subject_user_id="7")
        provider = registry_cls.call_args.kwargs["header_providers"]["mcp_srv-1"]
        with pytest.raises(McpIdentityWiringError):
            await provider()

    @pytest.mark.asyncio
    async def test_load_by_tool_id가_주체를_전달한다(self):
        loader = MCPToolLoader(logger=MagicMock())
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_registration(identity=False))
        with patch.object(loader, "load", AsyncMock(return_value=[])) as load:
            await loader.load_by_tool_id("mcp_srv-1", repo, "r", subject_user_id="7")
        assert load.call_args.kwargs["subject_user_id"] == "7"
