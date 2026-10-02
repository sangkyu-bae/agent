"""승인 필요 도구 컴파일 배선 — fail-closed 게이트·암묵 action·react 본문 키.

Design Ref: approval-gate-run-termination §4.1 (B11–B15, B21).
"""
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.approval.gate_middleware import ApprovalGateMiddleware
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.approval.entity import GateSettings
from tests.application.agent_builder.test_workflow_compiler_action import (
    _AGENT_PATH,
    _NODE_PATH,
    _make_compiler,
)
from tests.application.agent_builder.test_workflow_compiler_category import (
    _entry,
    _make_llm_model,
)

TOOL_ID = "mcp:6ea2f615-515e-4f65-aabe-388970dbafbe:submit_reply"
_REPLY_SCHEMA = {
    "type": "object",
    "properties": {"board": {}, "board_seq": {}, "reply_content": {}, "approver": {}},
}
_BODY_SCHEMA = {"type": "object", "properties": {"to": {}, "body": {}}}
_GATE_SETTINGS_PATH = "src.application.agent_builder.workflow_compiler._gate_settings"


def _gated_entry(category=None):
    return replace(_entry(TOOL_ID, category=category), requires_approval=True)


def _workflow(tool_config=None, category=None):
    return WorkflowDefinition(
        supervisor_prompt="당신은 AI 에이전트입니다.",
        workers=[
            WorkerDefinition(
                tool_id=TOOL_ID, worker_id="submit_reply_worker",
                description="답변 등록", sort_order=0,
                category=category, tool_config=tool_config,
            ),
            # 기존 불변식(워커 전부 실패면 컴파일 불가) 회피용 비게이트 워커
            WorkerDefinition(
                tool_id="mcp:6ea2f615-515e-4f65-aabe-388970dbafbe:get_inquiry",
                worker_id="get_inquiry_worker", description="조회", sort_order=1,
            ),
        ],
        flow_hint="test",
    )


def _logged(logger, level: str, event: str) -> list:
    return [c for c in getattr(logger, level).call_args_list if c.args and c.args[0] == event]


class TestFailClosedGate:
    @pytest.mark.asyncio
    async def test_게이트_미설정이어도_승인필요_도구는_게이트된다(self):
        """B11 — 미들웨어 계획 없음(에이전트에 approval_gate 없음)."""
        compiler, logger = _make_compiler([_gated_entry()], schema=_BODY_SCHEMA)
        with patch(_NODE_PATH, return_value=AsyncMock()) as mock_node, patch(
            _AGENT_PATH, return_value=MagicMock(),
        ):
            await compiler.compile(_workflow(), _make_llm_model(), "req-1")
        assert mock_node.call_args.kwargs["gated"] is True
        assert _logged(logger, "info", "approval gate applied by default")

    @pytest.mark.asyncio
    async def test_명시_off_는_게이트하지_않는다(self):
        """B12 — off 면 게이트도, 암묵 action 승격도 없다(react 유지)."""
        off = GateSettings.from_config({"mode": "off"}, is_enforced=False)
        compiler, logger = _make_compiler([_gated_entry()], schema=_BODY_SCHEMA)
        with patch(_GATE_SETTINGS_PATH, return_value=off), patch(
            _NODE_PATH,
        ) as mock_node, patch(_AGENT_PATH, return_value=MagicMock()) as mock_agent:
            await compiler.compile(_workflow(), _make_llm_model(), "req-1")
        mock_node.assert_not_called()
        for call in mock_agent.call_args_list:
            assert not any(
                isinstance(m, ApprovalGateMiddleware) for m in call.kwargs.get("middleware", [])
            )
        assert not _logged(logger, "info", "approval gate applied by default")

    @pytest.mark.asyncio
    async def test_승인필요_도구가_없으면_기본_게이트_로그도_없다(self):
        compiler, logger = _make_compiler([_entry(TOOL_ID)], schema=_BODY_SCHEMA)
        with patch(_AGENT_PATH, return_value=MagicMock()):
            await compiler.compile(_workflow(), _make_llm_model(), "req-1")
        assert not _logged(logger, "info", "approval gate applied by default")


class TestImplicitAction:
    @pytest.mark.asyncio
    async def test_미분류_승인필요_도구는_설정된_본문키로_action(self):
        """B13 / SC-6"""
        compiler, logger = _make_compiler([_gated_entry()], schema=_REPLY_SCHEMA)
        with patch(_NODE_PATH, return_value=AsyncMock()) as mock_node, patch(
            _AGENT_PATH, return_value=MagicMock(),
        ):
            graph = await compiler.compile(
                _workflow({"draft_arg_key": "reply_content"}), _make_llm_model(), "req-1",
            )
        assert "submit_reply_worker" in graph.nodes
        assert mock_node.call_args.kwargs["draft_key"] == "reply_content"
        assert _logged(logger, "info", "gated worker compiled as action")

    @pytest.mark.asyncio
    async def test_본문키_미확정이면_격리하지_않고_react_게이트로_폴백(self):
        """B14 / D-03"""
        compiler, logger = _make_compiler([_gated_entry()], schema=_REPLY_SCHEMA)
        with patch(_NODE_PATH) as mock_node, patch(
            _AGENT_PATH, return_value=MagicMock(),
        ) as mock_agent:
            graph = await compiler.compile(_workflow(None), _make_llm_model(), "req-1")
        assert "submit_reply_worker" in graph.nodes
        mock_node.assert_not_called()
        gated_calls = [
            c for c in mock_agent.call_args_list
            if any(isinstance(m, ApprovalGateMiddleware) for m in c.kwargs.get("middleware", []))
        ]
        assert len(gated_calls) == 1
        assert _logged(logger, "warning", "gated worker fallback to react")
        assert not _logged(logger, "error", "action worker isolated: draft key unresolved")

    @pytest.mark.asyncio
    async def test_명시_action_은_기존대로_격리(self):
        """B15 — 사용자가 action 을 지정했으면 폴백하지 않는다."""
        compiler, logger = _make_compiler(
            [_gated_entry(category="action")], schema=_REPLY_SCHEMA,
        )
        with patch(_NODE_PATH) as mock_node, patch(_AGENT_PATH, return_value=MagicMock()):
            graph = await compiler.compile(_workflow(None), _make_llm_model(), "req-1")
        assert "submit_reply_worker" not in graph.nodes
        mock_node.assert_not_called()
        assert not _logged(logger, "warning", "gated worker fallback to react")


class TestReactDraftKey:
    def test_react_게이트_미들웨어에_본문키를_전달한다(self):
        """B21 / D-04"""
        compiler, _ = _make_compiler([])
        gate = GateSettings.from_config({}, is_enforced=False)
        worker = WorkerDefinition(
            tool_id=TOOL_ID, worker_id="w", description="d",
            tool_config={"draft_arg_key": "reply_content"},
        )
        [middleware] = compiler._approval_gate_middleware(
            worker_def=worker, gate_settings=gate, gated_tool_ids={TOOL_ID},
        )
        assert isinstance(middleware, ApprovalGateMiddleware)
        assert middleware._draft_key == "reply_content"

    def test_react_게이트_마커_초안이_본문이다(self):
        middleware = ApprovalGateMiddleware(tool_id=TOOL_ID, worker_id="w", draft_key="reply_content")

        class _Req:
            tool_call = {
                "name": "x", "id": "tc1",
                "args": {"arguments": {"board": "customer", "reply_content": "본문"}},
            }

        from src.domain.approval.policies import ApprovalSignalPolicy

        signal = ApprovalSignalPolicy.extract([middleware.wrap_tool_call(_Req(), lambda _r: None)])
        assert signal.draft == "본문"


class TestGatedCollectCategory:
    """Analysis G2 — collect/search 노드는 게이트가 없어 무승인 실행되던 경로."""

    @pytest.mark.asyncio
    async def test_collect_승인필요_도구는_action_으로_게이트된다(self):
        compiler, _ = _make_compiler(
            [_gated_entry(category="collect")], schema=_REPLY_SCHEMA,
        )
        with patch(_NODE_PATH, return_value=AsyncMock()) as mock_node, patch(
            _AGENT_PATH, return_value=MagicMock(),
        ):
            await compiler.compile(
                _workflow({"draft_arg_key": "reply_content"}), _make_llm_model(), "req-1",
            )
        assert mock_node.call_args.kwargs["gated"] is True

    @pytest.mark.asyncio
    async def test_collect_본문키_미확정이면_react_게이트로_폴백(self):
        compiler, _ = _make_compiler(
            [_gated_entry(category="collect")], schema=_REPLY_SCHEMA,
        )
        with patch(_NODE_PATH) as mock_node, patch(
            _AGENT_PATH, return_value=MagicMock(),
        ) as mock_agent:
            await compiler.compile(_workflow(None), _make_llm_model(), "req-1")
        mock_node.assert_not_called()
        assert any(
            isinstance(m, ApprovalGateMiddleware)
            for c in mock_agent.call_args_list for m in c.kwargs.get("middleware", [])
        )
