"""MCPToolAdapter PII 검사 테스트 — Design §4.6 (FR-10, FR-11), D-08.

인자·결과 값은 바꾸지 않고 타입별 건수만 로그에 남긴다. 원복 뒤에도 남은
placeholder(고아)는 서버에 보내지 않는다.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.domain.mcp.value_objects import (
    MCPServerConfig,
    MCPTransport,
    StdioServerConfig,
)
from src.domain.pii_masking.policies import (
    PII_ORPHAN_TOOL_ARG_NOTICE,
    PiiToolArgumentPolicy,
)
from src.domain.pii_masking.schemas import PiiType
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

PHONE = "010-1234-5678"


class _Inspector:
    """명시적 fake — 받은 값을 기록하고 고정 건수를 돌려준다."""

    def __init__(self, counts=None, blocks: bool = True) -> None:
        self.seen: list = []
        self._counts = counts if counts is not None else {PiiType.PHONE: 1}
        self._blocks = blocks

    def inspect(self, value):
        self.seen.append(value)
        return self._counts

    def find_orphan_argument(self, value):
        # on 모드 서비스처럼 형태만 본다. blocks=False 는 shadow 서비스.
        return PiiToolArgumentPolicy.find_orphan(value) if self._blocks else None


def _adapter(inspector=None) -> MCPToolAdapter:
    return MCPToolAdapter(
        name="srv_get_inquiry",
        description="문의 조회",
        server_config=MCPServerConfig(
            name="srv",
            transport=MCPTransport.STDIO,
            stdio=StdioServerConfig(command="python", args=["s.py"]),
        ),
        mcp_tool_name="get_inquiry",
        request_id="req-1",
        tool_id="srv",
        pii_inspector=inspector,
    )


def _session(text: str):
    item = MagicMock()
    item.text = text
    result = MagicMock()
    result.content = [item]
    session = AsyncMock()
    session.call_tool = AsyncMock(return_value=result)
    return session


async def _run(adapter, args, text=f"연락처 {PHONE}"):
    session = _session(text)
    with (
        patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as ctx,
        patch("src.infrastructure.mcp.tool_adapter.logger") as log,
    ):
        ctx.return_value.__aenter__ = AsyncMock(return_value=session)
        ctx.return_value.__aexit__ = AsyncMock(return_value=None)
        out = await adapter._arun(arguments=args)
    return out, session, log


class TestInspect:
    async def test_args_and_result_inspected_values_unchanged(self):
        inspector = _Inspector()
        out, session, _ = await _run(_adapter(inspector), {"phone": PHONE})
        assert out == f"연락처 {PHONE}"
        assert session.call_tool.call_args.kwargs["arguments"] == {"phone": PHONE}
        assert inspector.seen == [{"phone": PHONE}, f"연락처 {PHONE}"]

    async def test_counts_logged_without_values(self):
        _, _, log = await _run(_adapter(_Inspector()), {"phone": PHONE})
        calls = [c for c in log.info.call_args_list if c.args[0] == "MCP PII inspected"]
        assert [c.kwargs["direction"] for c in calls] == ["request", "response"]
        assert calls[0].kwargs["counts"] == {"phone": 1}
        assert PHONE not in repr(log.mock_calls)

    async def test_zero_counts_not_logged(self):
        _, _, log = await _run(_adapter(_Inspector(counts={})), {"q": "x"}, text="ok")
        assert not [
            c for c in log.info.call_args_list if c.args[0] == "MCP PII inspected"
        ]

    async def test_without_inspector_no_inspection(self):
        out, session, log = await _run(_adapter(), {"phone": PHONE})
        assert out == f"연락처 {PHONE}"
        assert not [
            c for c in log.info.call_args_list if c.args[0] == "MCP PII inspected"
        ]


class TestOrphanBlock:
    async def test_orphan_placeholder_arg_blocked_before_server(self):
        out, session, log = await _run(_adapter(_Inspector()), {"to": "[EMAIL_9]"})
        assert out == PII_ORPHAN_TOOL_ARG_NOTICE
        session.call_tool.assert_not_called()
        warned = [c for c in log.warning.call_args_list if "placeholder" in c.args[0]]
        assert warned and "[EMAIL_9]" not in repr(warned)

    async def test_shadow_inspector_passes_placeholder_shaped_arg(self):
        # Check G-3: shadow 는 인자를 바꾸지도 막지도 않는다. 검사·기록만 한다.
        inspector = _Inspector(blocks=False)
        args = {"subject": "[EMAIL_1] 회신 요청"}
        out, session, _ = await _run(_adapter(inspector), args)
        assert out == f"연락처 {PHONE}"
        assert session.call_tool.call_args.kwargs["arguments"] == args
        assert inspector.seen[0] == args

    async def test_without_inspector_orphan_not_blocked(self):
        # 해제(D-03) 시에는 placeholder가 만들어지지 않으므로 기존 동작 유지.
        _, session, _ = await _run(_adapter(), {"to": "[EMAIL_9]"})
        session.call_tool.assert_awaited_once()


@pytest.mark.parametrize("inspector", [None, _Inspector()])
def test_field_is_optional(inspector):
    assert _adapter(inspector).pii_inspector is inspector
