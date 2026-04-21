"""WorkflowCompiler 단위 테스트."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.llm_model.entity import LlmModel


def _make_llm_model(provider: str = "openai", model_name: str = "gpt-4o-mini") -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1",
        provider=provider,
        model_name=model_name,
        display_name=model_name,
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=True,
        created_at=now,
        updated_at=now,
    )


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
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch("src.application.agent_builder.workflow_compiler.ChatOpenAI"),
            patch("src.application.agent_builder.workflow_compiler.create_react_agent"),
            patch("src.application.agent_builder.workflow_compiler.create_supervisor",
                  return_value=mock_supervisor),
        ):
            result = compiler.compile(workflow, _make_llm_model(), "req-1")

        assert result is mock_graph

    def test_compile_calls_tool_factory_for_each_worker(self):
        compiler, tool_factory = _make_compiler()
        workflow = _make_workflow()

        mock_supervisor = MagicMock()
        mock_supervisor.compile = MagicMock(return_value=MagicMock())

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch("src.application.agent_builder.workflow_compiler.ChatOpenAI"),
            patch("src.application.agent_builder.workflow_compiler.create_react_agent"),
            patch("src.application.agent_builder.workflow_compiler.create_supervisor",
                  return_value=mock_supervisor),
        ):
            compiler.compile(workflow, _make_llm_model(), "req-1")

        tool_factory.create.assert_called_once_with("tavily_search", "req-1")

    def test_compile_calls_create_supervisor_with_workers(self):
        compiler, _ = _make_compiler()
        workflow = _make_workflow()

        mock_worker_agent = MagicMock()
        mock_supervisor = MagicMock()
        mock_supervisor.compile = MagicMock(return_value=MagicMock())

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch("src.application.agent_builder.workflow_compiler.ChatOpenAI"),
            patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                  return_value=mock_worker_agent),
            patch("src.application.agent_builder.workflow_compiler.create_supervisor",
                  return_value=mock_supervisor) as mock_create_sup,
        ):
            compiler.compile(workflow, _make_llm_model(), "req-1")

        call_kwargs = mock_create_sup.call_args
        agents_arg = call_kwargs[1].get("agents") or (call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None)
        assert mock_worker_agent in agents_arg

    def test_compile_raises_on_tool_factory_error(self):
        compiler, tool_factory = _make_compiler()
        tool_factory.create = MagicMock(side_effect=ValueError("Unknown tool"))
        workflow = _make_workflow()

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch("src.application.agent_builder.workflow_compiler.ChatOpenAI"),
        ):
            with pytest.raises(ValueError, match="Unknown tool"):
                compiler.compile(workflow, _make_llm_model(), "req-1")

    def test_compile_dispatches_anthropic_provider(self):
        compiler, _ = _make_compiler()
        workflow = _make_workflow()

        mock_supervisor = MagicMock()
        mock_supervisor.compile = MagicMock(return_value=MagicMock())

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "ant-key"}),
            patch("src.application.agent_builder.workflow_compiler.ChatAnthropic") as mock_anthropic,
            patch("src.application.agent_builder.workflow_compiler.create_react_agent"),
            patch("src.application.agent_builder.workflow_compiler.create_supervisor",
                  return_value=mock_supervisor),
        ):
            llm_model = _make_llm_model(provider="anthropic", model_name="claude-sonnet-4-6")
            object.__setattr__(llm_model, "api_key_env", "ANTHROPIC_API_KEY")
            compiler.compile(workflow, llm_model, "req-1")

        mock_anthropic.assert_called_once()

    def test_compile_dispatches_ollama_provider(self):
        compiler, _ = _make_compiler()
        workflow = _make_workflow()

        mock_supervisor = MagicMock()
        mock_supervisor.compile = MagicMock(return_value=MagicMock())

        with (
            patch("src.application.agent_builder.workflow_compiler.ChatOllama") as mock_ollama,
            patch("src.application.agent_builder.workflow_compiler.create_react_agent"),
            patch("src.application.agent_builder.workflow_compiler.create_supervisor",
                  return_value=mock_supervisor),
        ):
            llm_model = _make_llm_model(provider="ollama", model_name="llama3")
            compiler.compile(workflow, llm_model, "req-1")

        mock_ollama.assert_called_once()

    def test_compile_raises_on_unknown_provider(self):
        compiler, _ = _make_compiler()
        workflow = _make_workflow()

        llm_model = _make_llm_model(provider="bedrock", model_name="claude-v2")
        with pytest.raises(ValueError, match="지원하지 않는 provider"):
            compiler.compile(workflow, llm_model, "req-1")
