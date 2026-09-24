"""WorkflowCompiler action 카테고리 배선 테스트.

Design Ref: action-category-compose-node §8.2 #18~#21 / D-03·D-09·D-11
  - 명시 action → create_agent가 아닌 create_action_node (함수 노드)
  - 본문 키를 정할 수 없으면 워커만 격리하고 에이전트는 컴파일된다
  - action 워커는 WorkerRunCapHooks capped 목록에 들어간다 (재개 이중 발송 방지)
  - 게이트 판정은 미들웨어 부착과 같은 함수(_should_gate_worker)를 쓴다
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.approval.entity import GateSettings
from src.domain.llm.interfaces import LLMFactoryInterface
from tests.application.agent_builder.test_workflow_compiler_category import (
    FakeCatalogRepo,
    _entry,
    _make_llm_model,
)

TOOL_ID = "mcp:3f2a1b4c-0000-1111-2222-333344445555:send_mail"
_MAIL_SCHEMA = {"type": "object", "properties": {"to": {}, "subject": {}, "body": {}}}
_NODE_PATH = "src.application.agent_builder.workflow_compiler.create_action_node"
_AGENT_PATH = "src.application.agent_builder.workflow_compiler.create_agent"
_CAP_PATH = "src.application.agent_builder.workflow_compiler.WorkerRunCapHooks"


def _make_compiler(catalog_entries, schema=_MAIL_SCHEMA):
    tool = MagicMock()
    tool.name = "send_mail"
    tool.description = "메일 발송"
    tool.mcp_tool_name = "send_mail"
    tool.mcp_input_schema = schema
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=tool)
    tool_factory.create_all_async = AsyncMock(return_value=[tool])
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    logger = MagicMock()
    compiler = WorkflowCompiler(
        tool_factory=tool_factory, llm_factory=llm_factory, logger=logger,
        hooks=DefaultHooks(), tool_catalog_repository=FakeCatalogRepo(catalog_entries),
    )
    return compiler, logger


def _workflow(tool_config=None):
    return WorkflowDefinition(
        supervisor_prompt="당신은 AI 에이전트입니다.",
        workers=[WorkerDefinition(
            tool_id=TOOL_ID, worker_id="mailer", description="회신 메일 발송",
            sort_order=0, category="action", tool_config=tool_config,
        )],
        flow_hint="test",
    )


class TestActionBranch:
    @pytest.mark.asyncio
    async def test_action_worker_is_function_node_not_react_agent(self):
        compiler, _ = _make_compiler([_entry(TOOL_ID, category="action")])
        with patch(_AGENT_PATH) as mock_agent, patch(
            _NODE_PATH, return_value=AsyncMock(),
        ) as mock_node:
            graph = await compiler.compile(
                _workflow({"draft_arg_key": "body"}), _make_llm_model(), "req-1",
            )

        assert "mailer" in graph.nodes
        mock_agent.assert_not_called()
        kwargs = mock_node.call_args.kwargs
        assert kwargs["worker_id"] == "mailer"
        assert kwargs["tool_id"] == TOOL_ID
        assert kwargs["draft_key"] == "body"
        assert kwargs["gated"] is False

    @pytest.mark.asyncio
    async def test_conventional_key_resolved_when_config_unset(self):
        compiler, _ = _make_compiler([_entry(TOOL_ID, category="action")])
        with patch(_NODE_PATH, return_value=AsyncMock()) as mock_node:
            await compiler.compile(_workflow(None), _make_llm_model(), "req-1")
        assert mock_node.call_args.kwargs["draft_key"] == "body"

    @pytest.mark.asyncio
    async def test_isolated_when_draft_key_unresolvable(self):
        """D-09: 스키마에 본문 키가 없으면 워커만 격리, 에이전트는 컴파일된다."""
        compiler, logger = _make_compiler(
            [_entry(TOOL_ID, category="action")],
            schema={"type": "object", "properties": {"text": {}}},
        )
        workflow = _workflow(None)
        # 기존 불변식: 워커 전부 실패면 컴파일 불가 → 다른 워커 하나를 둔다.
        workflow.workers.append(WorkerDefinition(
            tool_id="mcp:3f2a1b4c-0000-1111-2222-333344445555:other",  # 카탈로그 밖 → None → react
            worker_id="other", description="d", sort_order=1,
        ))
        with patch(_NODE_PATH) as mock_node, patch(
            _AGENT_PATH, return_value=MagicMock(),
        ) as mock_agent:
            graph = await compiler.compile(workflow, _make_llm_model(), "req-1")

        assert graph is not None
        assert "mailer" not in graph.nodes and "other" in graph.nodes
        mock_node.assert_not_called()
        assert mock_agent.call_count == 1  # react는 'other' 워커만
        assert logger.error.called

    @pytest.mark.asyncio
    async def test_action_worker_is_run_capped(self):
        """D-11: capped 목록에 action 워커 — 재개 런 이중 발송 방지."""
        compiler, _ = _make_compiler([_entry(TOOL_ID, category="action")])
        with patch(_NODE_PATH, return_value=AsyncMock()), patch(_CAP_PATH) as mock_cap:
            await compiler.compile(_workflow(None), _make_llm_model(), "req-1")
        assert "mailer" in mock_cap.call_args.args[1]

    @pytest.mark.asyncio
    async def test_gated_flag_passed_to_node(self):
        """판정 함수가 True면 노드에 gated=True — 판정 자체는 TestShouldGateWorker가 고정."""
        compiler, _ = _make_compiler([_entry(TOOL_ID, category="action")])
        with patch(_NODE_PATH, return_value=AsyncMock()) as mock_node, patch.object(
            WorkflowCompiler, "_should_gate_worker", return_value=True,
        ):
            await compiler.compile(_workflow(None), _make_llm_model(), "req-1")
        assert mock_node.call_args.kwargs["gated"] is True


class TestShouldGateWorker:
    def test_judgement_and_middleware_agree(self):
        """D-03: 노드 gated 값과 미들웨어 부착 여부는 같은 함수의 결과다."""
        compiler, _ = _make_compiler([])
        gate = GateSettings(mode="always", execute_after=None, expires_hours=24, is_enforced=True)
        worker = WorkerDefinition(tool_id=TOOL_ID, worker_id="mailer", description="d")

        assert compiler._should_gate_worker(worker, gate, {TOOL_ID}) is True
        assert compiler._should_gate_worker(worker, gate, set()) is False
        assert compiler._should_gate_worker(worker, None, {TOOL_ID}) is False
        assert bool(compiler._approval_gate_middleware(
            worker_def=worker, gate_settings=gate, gated_tool_ids={TOOL_ID},
        )) is True
        assert compiler._approval_gate_middleware(
            worker_def=worker, gate_settings=gate, gated_tool_ids=set(),
        ) == []
