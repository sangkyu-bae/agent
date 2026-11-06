"""McpActionExecutor PII 검사 테스트 — Design §4.6 (FR-11), D-08.

승인 후 집행은 MCPToolAdapter를 거치지 않는다. 같은 검사를 이 경로에도 둔다.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.domain.pii_masking.policies import PiiToolArgumentPolicy
from src.domain.pii_masking.schemas import PiiType
from src.infrastructure.approval.mcp_executor import McpActionExecutor

from tests.infrastructure.approval.test_mcp_executor import (
    SERVER_ID,
    TOOL_ID,
    _descriptor,
    _registration,
    _result,
)

EMAIL = "kim@customer.co.kr"


class _Inspector:
    def __init__(self, blocks: bool = True) -> None:
        self.seen: list = []
        self._blocks = blocks

    def inspect(self, value):
        self.seen.append(value)
        return {PiiType.EMAIL: 1}

    def find_orphan_argument(self, value):
        # blocks=False 는 shadow 서비스 — 차단하지 않는다.
        return PiiToolArgumentPolicy.find_orphan(value) if self._blocks else None


def _build(inspector=None):
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=_registration())
    client = MagicMock()
    client.list_tools = AsyncMock(return_value=[_descriptor()])
    client.call_tool = AsyncMock(return_value=_result(f"sent to {EMAIL}"))
    logger = MagicMock()
    executor = McpActionExecutor(
        server_repo=repo,
        client_factory=MagicMock(return_value=client),
        max_output_chars=1000,
        logger=logger,
        pii_inspector=inspector,
    )
    return executor, SimpleNamespace(repo=repo, client=client, logger=logger)


async def _run(executor, args):
    return await executor.execute(tool_id=TOOL_ID, tool_args=args, request_id="r1")


async def test_orphan_placeholder_blocked_before_connecting():
    executor, deps = _build(_Inspector())
    result = await _run(executor, {"arguments": {"to": "[EMAIL_9]", "body": "b"}})
    assert result.ok is False
    deps.repo.find_by_id.assert_not_called()
    deps.client.call_tool.assert_not_called()
    assert "[EMAIL_9]" not in repr(deps.logger.mock_calls)


async def test_args_and_result_inspected_values_unchanged():
    inspector = _Inspector()
    executor, deps = _build(inspector)
    result = await _run(executor, {"arguments": {"to": EMAIL, "body": "b"}})
    assert result.ok is True
    sent = deps.client.call_tool.call_args.kwargs["arguments"]
    assert sent["to"] == EMAIL
    assert inspector.seen[0] == sent
    assert inspector.seen[1] == f"sent to {EMAIL}"
    logged = [
        c for c in deps.logger.info.call_args_list if c.args[0] == "MCP PII inspected"
    ]
    assert [c.kwargs["direction"] for c in logged] == ["request", "response"]
    assert EMAIL not in repr(deps.logger.mock_calls)


async def test_shadow_inspector_passes_placeholder_shaped_arg():
    # Check G-3: shadow 모드 집행기는 인자를 막지 않는다.
    executor, deps = _build(_Inspector(blocks=False))
    result = await _run(executor, {"arguments": {"to": "[EMAIL_1]", "body": "b"}})
    assert result.ok is True
    assert deps.client.call_tool.call_args.kwargs["arguments"]["to"] == "[EMAIL_1]"


async def test_without_inspector_behavior_unchanged():
    executor, deps = _build()
    result = await _run(executor, {"arguments": {"to": "[EMAIL_9]", "body": "b"}})
    assert result.ok is True
    deps.client.call_tool.assert_awaited_once()
    assert SERVER_ID
