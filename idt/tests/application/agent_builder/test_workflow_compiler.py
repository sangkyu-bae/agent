"""WorkflowCompiler 단위 테스트."""
from unittest.mock import MagicMock, patch

import pytest

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition


def _make_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt="당신은 AI 뉴스 수집 에이전트입니다.",
        workers=[
            WorkerDefinition(tool_id="tavily_search", worker_id="search_worker",
                             description="웹 검색", sort_order=0),
        ],
        flow_hint="search_worker 실행",
    )


def _make_compiler() -> WorkflowCompiler:
    mock_tool = MagicMock()
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=mock_tool)
    logger = MagicMock()
    return WorkflowCompiler(tool_factory=tool_factory, logger=logger), tool_factory


class TestWorkflowCompiler:
    def test_compile_returns_graph(self):
        compiler, _ = _make_compiler()
        workflow = _make_workflow()

        mock_graph = MagicMock()
        mock_supervisor = MagicMock()
        mock_supervisor.compile = MagicMock(return_value=mock_graph)

        with (
            patch("src.application.agent_builder.workflow_compiler.ChatOpenAI"),
            patch("src.application.agent_builder.workflow_compiler.create_react_agent"),
            patch("src.application.agent_builder.workflow_compiler.create_supervisor",
                  return_value=mock_supervisor),
        ):
            result = compiler.compile(workflow, "gpt-4o-mini", "test-key", "req-1")

        assert result is mock_graph

    def test_compile_calls_tool_factory_for_each_worker(self):
        compiler, tool_factory = _make_compiler()
        workflow = _make_workflow()

        mock_supervisor = MagicMock()
        mock_supervisor.compile = MagicMock(return_value=MagicMock())

        with (
            patch("src.application.agent_builder.workflow_compiler.ChatOpenAI"),
            patch("src.application.agent_builder.workflow_compiler.create_react_agent"),
            patch("src.application.agent_builder.workflow_compiler.create_supervisor",
                  return_value=mock_supervisor),
        ):
            compiler.compile(workflow, "gpt-4o-mini", "test-key", "req-1")

        tool_factory.create.assert_called_once_with("tavily_search", "req-1")

    def test_compile_calls_create_supervisor_with_workers(self):
        compiler, _ = _make_compiler()
        workflow = _make_workflow()

        mock_worker_agent = MagicMock()
        mock_supervisor = MagicMock()
        mock_supervisor.compile = MagicMock(return_value=MagicMock())

        with (
            patch("src.application.agent_builder.workflow_compiler.ChatOpenAI"),
            patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                  return_value=mock_worker_agent),
            patch("src.application.agent_builder.workflow_compiler.create_supervisor",
                  return_value=mock_supervisor) as mock_create_sup,
        ):
            compiler.compile(workflow, "gpt-4o-mini", "test-key", "req-1")

        call_kwargs = mock_create_sup.call_args
        agents_arg = call_kwargs[1].get("agents") or (call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None)
        assert mock_worker_agent in agents_arg

    def test_compile_raises_on_tool_factory_error(self):
        compiler, tool_factory = _make_compiler()
        tool_factory.create = MagicMock(side_effect=ValueError("Unknown tool"))
        workflow = _make_workflow()

        with (
            patch("src.application.agent_builder.workflow_compiler.ChatOpenAI"),
        ):
            with pytest.raises(ValueError, match="Unknown tool"):
                compiler.compile(workflow, "gpt-4o-mini", "test-key", "req-1")
