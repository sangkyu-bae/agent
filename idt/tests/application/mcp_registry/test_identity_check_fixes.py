"""Check 단계 수정 — G-2(집행기), G-3(읽을 수 없는 신원 설정), G-4(주체 동봉),
일반 채팅 도구 목록에서 신원 서버 제외.

mcp-identity-header analysis §3.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.mcp_registry.load_mcp_tools_use_case import LoadMCPToolsUseCase
from src.application.mcp_registry.schemas import UpdateMCPServerRequest
from src.application.mcp_registry.update_mcp_server_use_case import (
    UpdateMCPServerUseCase,
)
from src.domain.mcp.value_objects import MCPToolDescriptor
from src.domain.mcp_registry.identity import IdentityHeaderConfig
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.infrastructure.approval.mcp_executor import McpActionExecutor
from src.infrastructure.mcp.client_factory import HeaderProviderError
from src.infrastructure.mcp_registry.identity_headers import (
    IdentityConfigUnreadableError,
    IdentityHeaderProviderFactory,
)

_NOW = datetime(2026, 9, 26)


def _reg(*, identity=None, unreadable=False, id="srv-1") -> MCPServerRegistration:
    return MCPServerRegistration(
        id=id, user_id="7", name="Outlook", description="d",
        endpoint="http://localhost:8006/sse", transport=MCPTransportType.SSE,
        input_schema=None, is_active=True, created_at=_NOW, updated_at=_NOW,
        identity_config=identity, identity_config_unreadable=unreadable,
    )


class TestUnreadableIdentity:
    """G-3 — 읽을 수 없는 설정은 '없음'이 아니라 '있는데 못 읽음'이다 (fail-closed)."""

    def test_읽을_수_없으면_신원이_필요한_서버로_본다(self):
        assert _reg(unreadable=True).requires_identity is True

    @pytest.mark.asyncio
    async def test_공급자는_헤더_없이_보내지_않고_실패한다(self):
        factory = IdentityHeaderProviderFactory(
            user_reader=MagicMock(), signer=MagicMock(), logger=MagicMock()
        )
        provide = factory.for_registration(_reg(unreadable=True), "7")
        with pytest.raises(IdentityConfigUnreadableError):
            await provide()

    def _uc(self, existing):
        repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        repo.find_by_id.return_value = existing
        repo.update.side_effect = lambda reg, _rid: reg
        return UpdateMCPServerUseCase(repository=repo, logger=MagicMock()), repo

    @pytest.mark.asyncio
    async def test_필드_없이_수정하면_저장된_설정을_지우지_않도록_거부한다(self):
        uc, repo = self._uc(_reg(unreadable=True))
        with pytest.raises(ValueError, match="신원 헤더 설정을 읽을 수 없습니다"):
            await uc.execute("srv-1", UpdateMCPServerRequest(name="새 이름"), "r")
        repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_null로_해제하는_것은_허용한다(self):
        uc, repo = self._uc(_reg(unreadable=True))
        await uc.execute("srv-1", UpdateMCPServerRequest(identity_config=None), "r")
        saved = repo.update.call_args.args[0]
        assert saved.identity_config is None
        assert saved.identity_config_unreadable is False

    @pytest.mark.asyncio
    async def test_비밀까지_새로_입력하면_교체를_허용한다(self):
        uc, repo = self._uc(_reg(unreadable=True))
        await uc.execute(
            "srv-1",
            UpdateMCPServerRequest(identity_config={"audience": "a", "secret": "n" * 32}),
            "r",
        )
        saved = repo.update.call_args.args[0]
        assert saved.identity_config.secret == "n" * 32
        assert saved.identity_config_unreadable is False


class TestExecutorProviderFailure:
    """G-2 — 공급자 단계 실패는 대상 시스템에 아무것도 보내지 않았다."""

    @pytest.mark.asyncio
    async def test_HeaderProviderError는_blocked(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=MagicMock(id="srv-1", is_active=True))
        client = MagicMock()
        client.list_tools = AsyncMock(return_value=[
            MCPToolDescriptor(name="send_mail", input_schema={"properties": {}})
        ])
        client.call_tool = AsyncMock(side_effect=HeaderProviderError("signing failed"))
        executor = McpActionExecutor(
            server_repo=repo, client_factory=MagicMock(return_value=client),
            max_output_chars=100, logger=MagicMock(),
        )
        result = await executor.execute(
            tool_id="mcp:srv-1:send_mail", tool_args={}, request_id="r",
            subject_user_id="7",
        )
        assert result.error_message.startswith("[집행 불가]")


class TestGeneralChatExclusion:
    """일반 채팅 — 전 사용자 공용 캐시이므로 신원 서버 도구를 싣지 않는다."""

    def _uc(self, exclude: bool):
        repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        identity = IdentityHeaderConfig.from_dict({"audience": "a", "secret": "s" * 32})
        repo.find_all_active.return_value = [
            _reg(id="plain"), _reg(id="mail", identity=identity),
            _reg(id="broken", unreadable=True),
        ]
        loader = MagicMock()
        loader.load = AsyncMock(side_effect=lambda reg, rid: [f"tool-of-{reg.id}"])
        uc = LoadMCPToolsUseCase(
            repository=repo, mcp_tool_loader=loader, logger=MagicMock(),
            exclude_identity_servers=exclude,
        )
        return uc, loader

    @pytest.mark.asyncio
    async def test_제외_옵션이면_신원_서버를_로드하지_않는다(self):
        uc, loader = self._uc(exclude=True)
        tools = await uc.execute("r")
        assert tools == ["tool-of-plain"]
        assert [c.args[0].id for c in loader.load.call_args_list] == ["plain"]

    @pytest.mark.asyncio
    async def test_기본값은_기존과_같다(self):
        uc, _ = self._uc(exclude=False)
        assert len(await uc.execute("r")) == 3
