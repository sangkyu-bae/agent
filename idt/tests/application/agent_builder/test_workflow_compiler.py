"""WorkflowCompiler 단위 테스트 — Custom StateGraph 기반 (TC-16~18)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import (
    SupervisorConfig,
    WorkerDefinition,
    WorkflowDefinition,
)
from src.domain.llm.interfaces import LLMFactoryInterface
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


def _make_workflow(worker_count: int = 1) -> WorkflowDefinition:
    workers = [
        WorkerDefinition(
            tool_id=f"tool_{i}", worker_id=f"worker_{i}",
            description=f"워커 {i}", sort_order=i,
        )
        for i in range(worker_count)
    ]
    return WorkflowDefinition(
        supervisor_prompt="당신은 AI 에이전트입니다.",
        workers=workers,
        flow_hint="test",
    )


def _make_compiler(hooks=None) -> tuple[WorkflowCompiler, MagicMock]:
    mock_tool = MagicMock()
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=mock_tool)
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    logger = MagicMock()
    compiler = WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=logger,
        hooks=hooks or DefaultHooks(),
    )
    return compiler, tool_factory


class TestWorkflowCompiler:
    @pytest.mark.asyncio
    async def test_compile_returns_compiled_graph(self):
        """compile()이 CompiledGraph를 반환."""
        compiler, _ = _make_compiler()
        workflow = _make_workflow()
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            result = await compiler.compile(workflow, _make_llm_model(), "req-1")
        assert result is not None

    @pytest.mark.asyncio
    async def test_compile_single_worker_graph_nodes(self):
        """TC-16: 워커 1개 → 노드: supervisor, worker_0, quality_gate."""
        compiler, _ = _make_compiler()
        workflow = _make_workflow(worker_count=1)
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(workflow, _make_llm_model(), "req-1")

        node_names = set(graph.get_graph().nodes.keys())
        assert "supervisor" in node_names
        assert "worker_0" in node_names
        assert "quality_gate" in node_names

    @pytest.mark.asyncio
    async def test_compile_three_workers_graph_nodes(self):
        """TC-17: 워커 3개 → 노드 5개 + 올바른 구조."""
        compiler, _ = _make_compiler()
        workflow = _make_workflow(worker_count=3)
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(workflow, _make_llm_model(), "req-1")

        node_names = set(graph.get_graph().nodes.keys())
        assert "supervisor" in node_names
        assert "worker_0" in node_names
        assert "worker_1" in node_names
        assert "worker_2" in node_names
        assert "quality_gate" in node_names

    @pytest.mark.asyncio
    async def test_compile_calls_tool_factory_for_each_worker(self):
        compiler, tool_factory = _make_compiler()
        workflow = _make_workflow(worker_count=2)
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            await compiler.compile(workflow, _make_llm_model(), "req-1")
        assert tool_factory.create.call_count == 2

    @pytest.mark.asyncio
    async def test_compile_delegates_to_llm_factory(self):
        compiler, _ = _make_compiler()
        workflow = _make_workflow()
        llm_model = _make_llm_model()
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            await compiler.compile(workflow, llm_model, "req-1", temperature=0.5)
        compiler._llm_factory.create.assert_called_once_with(llm_model, 0.5)

    @pytest.mark.asyncio
    async def test_compile_raises_on_tool_factory_error(self):
        compiler, tool_factory = _make_compiler()
        tool_factory.create = MagicMock(side_effect=ValueError("Unknown tool"))
        workflow = _make_workflow()
        with pytest.raises(ValueError, match="Unknown tool"):
            await compiler.compile(workflow, _make_llm_model(), "req-1")

    @pytest.mark.asyncio
    async def test_compile_accepts_supervisor_config(self):
        """SupervisorConfig 전달 시 정상 컴파일."""
        compiler, _ = _make_compiler()
        workflow = _make_workflow()
        config = SupervisorConfig(max_iterations=5, quality_gate_enabled=True)
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1", supervisor_config=config,
            )
        assert graph is not None

    @pytest.mark.asyncio
    async def test_compile_default_config_when_none(self):
        """supervisor_config=None이면 기본값 사용."""
        compiler, _ = _make_compiler()
        workflow = _make_workflow()
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1", supervisor_config=None,
            )
        assert graph is not None


class TestResolveCategory:
    """_resolve_category 3-tier fallback 테스트 (TC-R01~R04)."""

    def test_db_override_takes_priority(self):
        """TC-R01: worker_def.category가 있으면 DB 값 우선."""
        compiler, _ = _make_compiler()
        worker = WorkerDefinition(
            tool_id="internal_document_search", worker_id="w",
            description="d", category="action",
        )
        assert compiler._resolve_category(worker) == "action"

    def test_falls_back_to_registry(self):
        """TC-R02: category=None이면 TOOL_REGISTRY 값."""
        compiler, _ = _make_compiler()
        worker = WorkerDefinition(
            tool_id="internal_document_search", worker_id="w",
            description="d", category=None,
        )
        assert compiler._resolve_category(worker) == "search"

    def test_falls_back_to_action_for_unknown_tool(self):
        """TC-R03: TOOL_REGISTRY에 없는 도구(MCP 등)는 "action"."""
        compiler, _ = _make_compiler()
        worker = WorkerDefinition(
            tool_id="mcp_custom_tool", worker_id="w",
            description="d", category=None,
        )
        assert compiler._resolve_category(worker) == "action"

    def test_db_search_overrides_registry_action(self):
        """TC-R04: DB에 "search" 지정 → registry 무관하게 search."""
        compiler, _ = _make_compiler()
        worker = WorkerDefinition(
            tool_id="python_code_executor", worker_id="w",
            description="d", category="search",
        )
        assert compiler._resolve_category(worker) == "search"


class TestCompileWithCategory:
    """카테고리 기반 분기 통합 테스트 (TC-W01~W06)."""

    @pytest.mark.asyncio
    async def test_search_only_has_answer_agent(self):
        """TC-W01: search 도구만 → answer_agent 노드 존재."""
        compiler, _ = _make_compiler()
        workers = [
            WorkerDefinition(
                tool_id="internal_document_search", worker_id="searcher",
                description="검색", sort_order=0,
            ),
        ]
        workflow = WorkflowDefinition(
            supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
        )
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(workflow, _make_llm_model(), "req-1")

        node_names = set(graph.get_graph().nodes.keys())
        assert "answer_agent" in node_names
        assert "searcher" in node_names

    @pytest.mark.asyncio
    async def test_action_only_no_answer_agent(self):
        """TC-W02: action 도구만 → answer_agent 없음."""
        compiler, _ = _make_compiler()
        workers = [
            WorkerDefinition(
                tool_id="python_code_executor", worker_id="coder",
                description="코드실행", sort_order=0,
            ),
        ]
        workflow = WorkflowDefinition(
            supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
        )
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(workflow, _make_llm_model(), "req-1")

        node_names = set(graph.get_graph().nodes.keys())
        assert "answer_agent" not in node_names
        assert "coder" in node_names

    @pytest.mark.asyncio
    async def test_mixed_creates_both_types(self):
        """TC-W03: 혼합 → search는 search_node, action은 react_agent."""
        compiler, _ = _make_compiler()
        workers = [
            WorkerDefinition(
                tool_id="internal_document_search", worker_id="searcher",
                description="검색", sort_order=0,
            ),
            WorkerDefinition(
                tool_id="python_code_executor", worker_id="coder",
                description="코드실행", sort_order=1,
            ),
        ]
        workflow = WorkflowDefinition(
            supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
        )
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()) as mock_react:
            graph = await compiler.compile(workflow, _make_llm_model(), "req-1")

        node_names = set(graph.get_graph().nodes.keys())
        assert "answer_agent" in node_names
        assert "searcher" in node_names
        assert "coder" in node_names
        assert mock_react.call_count == 1

    @pytest.mark.asyncio
    async def test_react_agent_only_for_action_tools(self):
        """TC-W04: create_react_agent 호출 = action 도구 수."""
        compiler, _ = _make_compiler()
        workers = [
            WorkerDefinition(
                tool_id="tavily_search", worker_id="s1",
                description="검색1", sort_order=0,
            ),
            WorkerDefinition(
                tool_id="internal_document_search", worker_id="s2",
                description="검색2", sort_order=1,
            ),
            WorkerDefinition(
                tool_id="excel_export", worker_id="a1",
                description="엑셀", sort_order=2,
            ),
        ]
        workflow = WorkflowDefinition(
            supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
        )
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()) as mock_react:
            await compiler.compile(workflow, _make_llm_model(), "req-1")

        assert mock_react.call_count == 1

    @pytest.mark.asyncio
    async def test_db_category_override_search_to_action(self):
        """TC-W05: DB category override로 search 도구를 action으로."""
        compiler, _ = _make_compiler()
        workers = [
            WorkerDefinition(
                tool_id="internal_document_search", worker_id="searcher",
                description="검색", sort_order=0,
                category="action",
            ),
        ]
        workflow = WorkflowDefinition(
            supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
        )
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()) as mock_react:
            graph = await compiler.compile(workflow, _make_llm_model(), "req-1")

        node_names = set(graph.get_graph().nodes.keys())
        assert "answer_agent" not in node_names
        assert mock_react.call_count == 1


class TestSupervisorAnswerAgentRouting:
    """Supervisor → answer_agent 라우팅 테스트 (TC-W06~W07)."""

    @pytest.mark.asyncio
    async def test_supervisor_knows_answer_agent_when_search_exists(self):
        """TC-W06: search 워커 존재 시 supervisor가 answer_agent를 인식."""
        compiler, _ = _make_compiler()
        workers = [
            WorkerDefinition(
                tool_id="internal_document_search", worker_id="searcher",
                description="검색", sort_order=0,
            ),
        ]
        workflow = WorkflowDefinition(
            supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
        )
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()), \
             patch("src.application.agent_builder.workflow_compiler.create_supervisor_node",
                   return_value=AsyncMock()) as mock_sup:
            await compiler.compile(workflow, _make_llm_model(), "req-1")

        call_kwargs = mock_sup.call_args
        passed_workers = call_kwargs.kwargs.get("workers") or call_kwargs[1].get("workers")
        if passed_workers is None:
            passed_workers = call_kwargs[0][1]
        worker_ids = {w.worker_id for w in passed_workers}
        assert "answer_agent" in worker_ids

    @pytest.mark.asyncio
    async def test_supervisor_no_answer_agent_when_action_only(self):
        """TC-W07: action 전용 → supervisor에 answer_agent 없음."""
        compiler, _ = _make_compiler()
        workers = [
            WorkerDefinition(
                tool_id="python_code_executor", worker_id="coder",
                description="코드실행", sort_order=0,
            ),
        ]
        workflow = WorkflowDefinition(
            supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
        )
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()), \
             patch("src.application.agent_builder.workflow_compiler.create_supervisor_node",
                   return_value=AsyncMock()) as mock_sup:
            await compiler.compile(workflow, _make_llm_model(), "req-1")

        call_kwargs = mock_sup.call_args
        passed_workers = call_kwargs.kwargs.get("workers") or call_kwargs[1].get("workers")
        if passed_workers is None:
            passed_workers = call_kwargs[0][1]
        worker_ids = {w.worker_id for w in passed_workers}
        assert "answer_agent" not in worker_ids


class TestMcpToolAsync:
    """MCP 도구 비동기 생성 테스트 (TC-M01~M02)."""

    @pytest.mark.asyncio
    async def test_mcp_tool_uses_create_async(self):
        """TC-M01: mcp_ 접두사 tool_id는 create_async 사용."""
        mock_tool = MagicMock()
        tool_factory = MagicMock()
        tool_factory.create_async = AsyncMock(return_value=mock_tool)
        llm_factory = MagicMock(spec=LLMFactoryInterface)
        llm_factory.create.return_value = MagicMock()
        logger = MagicMock()
        compiler = WorkflowCompiler(
            tool_factory=tool_factory,
            llm_factory=llm_factory,
            logger=logger,
        )
        workers = [
            WorkerDefinition(
                tool_id="mcp_custom_tool", worker_id="mcp_worker",
                description="MCP 도구", sort_order=0, category="action",
            ),
        ]
        workflow = WorkflowDefinition(
            supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
        )
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            await compiler.compile(workflow, _make_llm_model(), "req-1")

        tool_factory.create_async.assert_called_once()
        tool_factory.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_mcp_tool_uses_sync_create(self):
        """TC-M02: 일반 tool_id는 기존 create 사용."""
        compiler, tool_factory = _make_compiler()
        workers = [
            WorkerDefinition(
                tool_id="python_code_executor", worker_id="coder",
                description="코드실행", sort_order=0,
            ),
        ]
        workflow = WorkflowDefinition(
            supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
        )
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            await compiler.compile(workflow, _make_llm_model(), "req-1")

        tool_factory.create.assert_called()


class TestWrapWorker:
    @pytest.mark.asyncio
    async def test_wrap_worker_updates_state(self):
        """TC-18: 워커 실행 후 last_worker_id 갱신, token_usage 증가."""
        compiler, _ = _make_compiler()

        mock_ai_msg = MagicMock()
        mock_ai_msg.content = "검색 결과입니다. AI 관련 뉴스 3건을 찾았습니다."
        mock_worker_agent = AsyncMock()
        mock_worker_agent.ainvoke.return_value = {"messages": [mock_ai_msg]}

        wrapped = compiler._wrap_worker("worker_0", mock_worker_agent)
        state = {
            "messages": [{"role": "user", "content": "test"}],
            "token_usage": 0,
        }
        result = await wrapped(state)
        assert result["last_worker_id"] == "worker_0"
        assert result["token_usage"] > 0
        assert result["messages"] == [mock_ai_msg]
