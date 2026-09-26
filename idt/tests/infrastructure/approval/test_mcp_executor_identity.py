"""승인 집행 경로의 신원 — 요청자 전달·네트워크 전 차단.

Design Ref: mcp-identity-header §6.2 (집행 경로), §8.2 (#12, #13), Appendix B (#3, #4).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.mcp.value_objects import MCPToolDescriptor, MCPToolResult
from src.domain.mcp_registry.identity import ClaimSource, IdentityUnavailableError
from src.infrastructure.approval.composite_executor import CompositeActionExecutor
from src.infrastructure.approval.mcp_executor import McpActionExecutor

SERVER_ID = "11111111-2222-3333-4444-555555555555"
TOOL_ID = f"mcp:{SERVER_ID}:send_mail"


def _executor(call_error: Exception | None = None):
    registration = SimpleNamespace(id=SERVER_ID, is_active=True, name="outlook")
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=registration)
    client = MagicMock()
    client.list_tools = AsyncMock(return_value=[MCPToolDescriptor(
        name="send_mail", input_schema={"type": "object", "properties": {}}
    )])
    client.call_tool = AsyncMock(
        return_value=MCPToolResult(tool_name="send_mail", server_name="s", content="ok"),
        side_effect=call_error,
    )
    factory = MagicMock(return_value=client)
    executor = McpActionExecutor(
        server_repo=repo, client_factory=factory, max_output_chars=1000,
        logger=MagicMock(),
    )
    return executor, factory, client, registration


class TestMcpActionExecutor:
    @pytest.mark.asyncio
    async def test_클라이언트_팩토리에_요청자와_request_id를_넘긴다(self):
        executor, factory, _, registration = _executor()
        await executor.execute(
            tool_id=TOOL_ID, tool_args={}, request_id="req-1", subject_user_id="7"
        )
        factory.assert_called_once_with(registration, "7", "req-1")

    @pytest.mark.asyncio
    async def test_신원_불가는_보내지_않았으므로_blocked(self):
        err = IdentityUnavailableError("claim_empty", ClaimSource.MAILBOX_UPN)
        executor, _, client, _ = _executor(call_error=err)
        result = await executor.execute(
            tool_id=TOOL_ID, tool_args={}, request_id="r", subject_user_id="7"
        )
        assert result.ok is False
        # 공급자는 세션을 열기 전에 실패한다 — 대상 시스템엔 아무것도 가지 않았다.
        assert result.error_message.startswith("[집행 불가]")
        assert "메일함이 등록되지 않았습니다" in result.error_message
        client.call_tool.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_그_외_호출_오류는_기존대로_unknown(self):
        executor, _, _, _ = _executor(call_error=RuntimeError("boom"))
        result = await executor.execute(
            tool_id=TOOL_ID, tool_args={}, request_id="r", subject_user_id="7"
        )
        assert result.error_message.startswith("[집행 여부 불명]")


class TestComposite:
    @pytest.mark.asyncio
    async def test_요청자를_하위_집행기로_전달한다(self):
        inner = MagicMock()
        inner.supports = MagicMock(return_value=True)
        inner.execute = AsyncMock(return_value=MagicMock())
        composite = CompositeActionExecutor(executors=[inner], logger=MagicMock())
        await composite.execute(
            tool_id=TOOL_ID, tool_args={}, request_id="r", subject_user_id="7"
        )
        assert inner.execute.call_args.kwargs["subject_user_id"] == "7"
