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
    async def test_compile_zero_workers_graph_nodes(self):
        """agent-instruction-required: 워커 0개(순수 대화형) → supervisor/final_answer만,
        quality_gate는 고아 노드 방지 위해 미등록."""
        compiler, _ = _make_compiler()
        workflow = _make_workflow(worker_count=0)
        graph = await compiler.compile(workflow, _make_llm_model(), "req-1")

        node_names = set(graph.get_graph().nodes.keys())
        assert "supervisor" in node_names
        assert "final_answer" in node_names
        assert "quality_gate" not in node_names

    @pytest.mark.asyncio
    async def test_zero_worker_graph_invokes_and_finishes(self):
        """agent-instruction-required 설계 §8.1: compile(workers=[]) + ainvoke 시
        supervisor가 워커 없이 FINISH+answer로 직접 응답하고 종료한다."""
        from src.application.agent_builder.supervisor_nodes import (
            SupervisorDecision,
            build_initial_state,
        )

        compiler, _ = _make_compiler()
        # supervisor LLM이 워커 호출 없이 즉시 FINISH + answer를 반환하도록 mock
        llm = compiler._llm_factory.create.return_value
        llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=SupervisorDecision(
                next="FINISH",
                reasoning="사용 가능한 워커가 없어 직접 답변",
                answer="안녕하세요! 무엇을 도와드릴까요?",
            )
        )

        workflow = _make_workflow(worker_count=0)
        config = SupervisorConfig()
        graph = await compiler.compile(
            workflow, _make_llm_model(), "req-1", supervisor_config=config,
        )

        state = build_initial_state(
            messages=[{"role": "user", "content": "안녕"}],
            config=config,
            available_workers=[],
        )
        result = await graph.ainvoke(state)

        # 워커 미실행(last_worker_id 없음) → supervisor answer가 최종 메시지로 남고 종료
        contents = [
            getattr(m, "content", "") for m in result["messages"]
        ]
        assert "안녕하세요! 무엇을 도와드릴까요?" in contents

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
    async def test_search_only_has_final_answer(self):
        """TC-W01(개정): search 도구만 → final_answer 노드 존재, answer_agent 부재."""
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
        assert "final_answer" in node_names
        assert "answer_agent" not in node_names
        assert "searcher" in node_names

    @pytest.mark.asyncio
    async def test_action_only_also_has_final_answer(self):
        """TC-W02(개정): action 도구만이어도 depth=0이면 final_answer 존재."""
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
        assert "final_answer" in node_names
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
        assert "final_answer" in node_names
        assert "answer_agent" not in node_names
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
        assert "final_answer" in node_names
        assert mock_react.call_count == 1


class TestSupervisorWorkerExposure:
    """final-answer-node D2: 가상 워커가 supervisor 선택지에 노출되지 않음 (TC-W06~W07 개정)."""

    async def _passed_worker_ids(self, workers) -> set[str]:
        compiler, _ = _make_compiler()
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
        return {w.worker_id for w in passed_workers}

    @pytest.mark.asyncio
    async def test_supervisor_never_sees_virtual_workers_with_search(self):
        """TC-W06(개정): search 워커가 있어도 answer_agent/final_answer 미노출."""
        worker_ids = await self._passed_worker_ids([
            WorkerDefinition(
                tool_id="internal_document_search", worker_id="searcher",
                description="검색", sort_order=0,
            ),
        ])
        assert "answer_agent" not in worker_ids
        assert "final_answer" not in worker_ids
        assert "searcher" in worker_ids

    @pytest.mark.asyncio
    async def test_supervisor_never_sees_virtual_workers_action_only(self):
        """TC-W07(개정): action 전용도 동일."""
        worker_ids = await self._passed_worker_ids([
            WorkerDefinition(
                tool_id="python_code_executor", worker_id="coder",
                description="코드실행", sort_order=0,
            ),
        ])
        assert "answer_agent" not in worker_ids
        assert "final_answer" not in worker_ids


class TestCompileWithAnalysisCategory:
    """analysis-node-agent: category='analysis' 컴파일 통합 테스트 (GAP-1, GAP-2 회귀 방지)."""

    def _analysis_workflow(self) -> WorkflowDefinition:
        workers = [
            WorkerDefinition(
                tool_id="data_analysis", worker_id="analyst",
                description="데이터 분석", sort_order=0,
            ),
        ]
        return WorkflowDefinition(
            supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
        )

    @pytest.mark.asyncio
    async def test_analysis_worker_is_function_node_not_react_agent(self):
        """GAP-1: analysis 워커는 함수 노드로 등록되고 create_react_agent를 타지 않는다."""
        compiler, tool_factory = _make_compiler()
        with patch(
            "src.application.agent_builder.workflow_compiler.create_react_agent",
            return_value=MagicMock(),
        ) as mock_react:
            graph = await compiler.compile(
                self._analysis_workflow(), _make_llm_model(), "req-1",
            )

        node_names = set(graph.get_graph().nodes.keys())
        assert "analyst" in node_names
        # analysis 노드는 도구를 직접 쓰지 않고 react agent도 만들지 않음
        mock_react.assert_not_called()
        tool_factory.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_analysis_node_routes_through_chart_router_to_quality_gate(self):
        """GAP-2 + analysis-chart-router: analysis 노드 → chart_router → quality_gate.

        analysis 워커 직후 chart_router를 경유하고, 라우터는 다시 quality_gate로
        복귀한다(END 직행 아님). 전이적으로 supervisor 복귀 흐름이 보존된다.
        """
        compiler, _ = _make_compiler()
        with patch(
            "src.application.agent_builder.workflow_compiler.create_react_agent",
            return_value=MagicMock(),
        ):
            graph = await compiler.compile(
                self._analysis_workflow(), _make_llm_model(), "req-1",
            )

        edges = graph.get_graph().edges
        analyst_targets = {e.target for e in edges if e.source == "analyst"}
        router_targets = {e.target for e in edges if e.source == "chart_router"}

        # analysis 워커는 chart_router로 진입 (quality_gate 직결 아님, END 아님)
        assert "chart_router" in analyst_targets
        assert "__end__" not in analyst_targets
        # chart_router는 quality_gate로 복귀
        assert "quality_gate" in router_targets

    @pytest.mark.asyncio
    async def test_non_analysis_worker_still_goes_to_quality_gate(self):
        """analysis-chart-router: 비-analysis 워커는 여전히 quality_gate 직결."""
        workers = [
            WorkerDefinition(
                tool_id="web_search_tavily", worker_id="searcher",
                description="검색", sort_order=0,
            ),
        ]
        workflow = WorkflowDefinition(
            supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
        )
        compiler, _ = _make_compiler()
        with patch(
            "src.application.agent_builder.workflow_compiler.create_react_agent",
            return_value=MagicMock(),
        ):
            graph = await compiler.compile(workflow, _make_llm_model(), "req-1")

        node_names = set(graph.get_graph().nodes.keys())
        # analysis 워커가 없으면 chart_router 노드도 만들지 않음
        assert "chart_router" not in node_names

    @pytest.mark.asyncio
    async def test_analysis_only_has_final_answer_not_answer_agent(self):
        """analysis 전용 → answer_agent 없음, final_answer는 depth=0이라 존재."""
        compiler, _ = _make_compiler()
        with patch(
            "src.application.agent_builder.workflow_compiler.create_react_agent",
            return_value=MagicMock(),
        ):
            graph = await compiler.compile(
                self._analysis_workflow(), _make_llm_model(), "req-1",
            )

        node_names = set(graph.get_graph().nodes.keys())
        assert "answer_agent" not in node_names
        assert "final_answer" in node_names


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


def _make_analysis_workflow() -> WorkflowDefinition:
    """analysis 카테고리 워커 1개 워크플로우 (chart_router 분기 활성화용)."""
    return WorkflowDefinition(
        supervisor_prompt="당신은 데이터 분석 에이전트입니다.",
        workers=[
            WorkerDefinition(
                tool_id="__virtual__", worker_id="data_analysis",
                description="데이터 분석", sort_order=0, category="analysis",
            )
        ],
        flow_hint="analysis",
    )


class TestChartBuilderWiring:
    """supervisor-chart-builder-node Design §11-2: chart_builder 노드 배선."""

    @pytest.mark.asyncio
    async def test_chart_builder_node_registered_when_enabled(self):
        """chart_max_count>0 + 분석워커 → chart_router/chart_builder 노드 등록."""
        compiler, _ = _make_compiler()
        compiler._chart_max_count = 3
        graph = await compiler.compile(
            _make_analysis_workflow(), _make_llm_model(), "req-1"
        )
        node_names = set(graph.get_graph().nodes.keys())
        assert "chart_router" in node_names
        assert "chart_builder" in node_names

    @pytest.mark.asyncio
    async def test_chart_builder_node_absent_when_disabled(self):
        """chart_max_count=0(기본) → chart_router만, chart_builder 미등록(하위호환)."""
        compiler, _ = _make_compiler()  # chart_max_count 기본 0
        graph = await compiler.compile(
            _make_analysis_workflow(), _make_llm_model(), "req-1"
        )
        node_names = set(graph.get_graph().nodes.keys())
        assert "chart_router" in node_names
        assert "chart_builder" not in node_names


def _decision(next_: str, answer: str = "") -> MagicMock:
    d = MagicMock()
    d.next = next_
    d.reasoning = "test reasoning"
    d.answer = answer
    return d


def _search_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt="프롬프트",
        workers=[
            WorkerDefinition(
                tool_id="internal_document_search", worker_id="searcher",
                description="검색", sort_order=0,
            ),
        ],
        flow_hint="test",
    )


class TestFinalAnswerWiring:
    """final-answer-node Design §5-4: compile 배선 + 그래프 e2e (TC-C02~C05)."""

    @pytest.mark.asyncio
    async def test_sub_graph_depth_has_no_final_answer(self):
        """TC-C02: depth>0 컴파일 → final_answer 미등록 (D4)."""
        compiler, _ = _make_compiler()
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(
                _search_workflow(), _make_llm_model(), "req-1", depth=1,
            )

        node_names = set(graph.get_graph().nodes.keys())
        assert "final_answer" not in node_names

    @pytest.mark.asyncio
    async def test_final_answer_edge_goes_to_end(self):
        """TC-D3 배선: final_answer → END 직행 (quality_gate 미경유)."""
        compiler, _ = _make_compiler()
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(
                _search_workflow(), _make_llm_model(), "req-1",
            )

        edges = graph.get_graph().edges
        final_targets = {e.target for e in edges if e.source == "final_answer"}
        assert final_targets == {"__end__"}

    def _e2e_setup(self, decisions: list, final_answer: str = "최종 종합 답변"):
        """e2e용 compiler + mock llm/tool 조립."""
        from langchain_core.messages import AIMessage

        mock_llm = MagicMock()
        structured = MagicMock()
        structured.ainvoke = AsyncMock(side_effect=decisions)
        mock_llm.with_structured_output.return_value = structured
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=final_answer))

        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(return_value="검색 자료입니다")
        tool_factory = MagicMock()
        tool_factory.create = MagicMock(return_value=mock_tool)

        llm_factory = MagicMock(spec=LLMFactoryInterface)
        llm_factory.create.return_value = mock_llm

        compiler = WorkflowCompiler(
            tool_factory=tool_factory,
            llm_factory=llm_factory,
            logger=MagicMock(),
            hooks=DefaultHooks(),
        )
        return compiler, mock_llm

    @pytest.mark.asyncio
    async def test_e2e_worker_run_then_final_answer(self):
        """TC-C03: 검색 워커 실행 → FINISH → final_answer 경유 후 END."""
        from src.application.agent_builder.supervisor_nodes import build_initial_state

        compiler, mock_llm = self._e2e_setup(
            decisions=[_decision("searcher"), _decision("FINISH")],
        )
        graph = await compiler.compile(_search_workflow(), _make_llm_model(), "req-1")

        initial = build_initial_state(
            messages=[{"role": "user", "content": "질문입니다"}],
            config=SupervisorConfig(),
            available_workers=["searcher"],
        )
        result = await graph.ainvoke(initial)

        assert result["last_worker_id"] == "final_answer"
        assert result["messages"][-1].content == "최종 종합 답변"
        # final_answer LLM 호출의 system prompt에 검색결과 블록 포함
        system_content = mock_llm.ainvoke.call_args[0][0][0]["content"]
        assert "검색 자료입니다" in system_content

    @pytest.mark.asyncio
    async def test_e2e_direct_answer_skips_final_answer(self):
        """TC-C04: 워커 미실행 FINISH(직접 답변) → final_answer 미경유."""
        from src.application.agent_builder.supervisor_nodes import build_initial_state

        compiler, mock_llm = self._e2e_setup(
            decisions=[_decision("FINISH", answer="직접 답변입니다")],
        )
        graph = await compiler.compile(_search_workflow(), _make_llm_model(), "req-1")

        initial = build_initial_state(
            messages=[{"role": "user", "content": "안녕"}],
            config=SupervisorConfig(),
            available_workers=["searcher"],
        )
        result = await graph.ainvoke(initial)

        assert result["messages"][-1].content == "직접 답변입니다"
        # final_answer 노드의 llm.ainvoke 미호출
        mock_llm.ainvoke.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_e2e_forced_termination_still_goes_final_answer(self):
        """TC-C05: max_iterations 강제 종료라도 워커가 실행됐으면 final_answer 경유 (DQ2)."""
        from src.application.agent_builder.supervisor_nodes import build_initial_state

        compiler, mock_llm = self._e2e_setup(
            decisions=[_decision("searcher")],  # 2번째 supervisor는 LLM 없이 강제 __end__
        )
        graph = await compiler.compile(_search_workflow(), _make_llm_model(), "req-1")

        initial = build_initial_state(
            messages=[{"role": "user", "content": "질문"}],
            config=SupervisorConfig(max_iterations=1),
            available_workers=["searcher"],
        )
        result = await graph.ainvoke(initial)

        assert result["last_worker_id"] == "final_answer"
        assert result["messages"][-1].content == "최종 종합 답변"

    @pytest.mark.asyncio
    async def test_e2e_final_answer_includes_user_context_block(self):
        """TC-F07: effective_supervisor_prompt(사용자 컨텍스트 블록)가 final_answer에 반영 (§3-4 정정)."""
        from src.application.agent_builder.supervisor_nodes import build_initial_state

        compiler, mock_llm = self._e2e_setup(
            decisions=[_decision("searcher"), _decision("FINISH")],
        )
        user_block = "[사용자 정보]\n부서: 여신팀, 이름: 배상규\n"
        with patch(
            "src.application.agent_builder.workflow_compiler.render_user_context_block",
            return_value=user_block,
        ):
            graph = await compiler.compile(
                _search_workflow(), _make_llm_model(), "req-1",
                include_user_context=True,
            )

            initial = build_initial_state(
                messages=[{"role": "user", "content": "내 부서 기준으로 알려줘"}],
                config=SupervisorConfig(),
                available_workers=["searcher"],
            )
            await graph.ainvoke(initial)

        # final_answer LLM 호출의 system prompt에 사용자 컨텍스트 블록이 prepend됨
        system_content = mock_llm.ainvoke.call_args[0][0][0]["content"]
        assert "부서: 여신팀, 이름: 배상규" in system_content


class TestPrefillSafety:
    """fix-anthropic-prefill-error TC-10~12: LLM/에이전트 입력이 assistant로 끝나지 않아야 함."""

    @staticmethod
    def _role(msg) -> str:
        if isinstance(msg, dict):
            return str(msg.get("role", ""))
        return str(getattr(msg, "type", ""))

    def _ai_last_state(self) -> dict:
        from langchain_core.messages import AIMessage

        return {
            "messages": [
                {"role": "user", "content": "질문"},
                AIMessage(content="이전 워커 결과", name="worker_prev"),
            ],
            "token_usage": 0,
            "token_limit": 8000,
            "last_worker_id": "worker_prev",
            "charts": [],
        }

    @pytest.mark.asyncio
    async def test_tc10_wrap_worker_not_assistant_last(self):
        """TC-10: _wrap_worker — react agent에 전달되는 messages 마지막이 user."""
        compiler, _ = _make_compiler()
        worker_agent = MagicMock()
        worker_agent.ainvoke = AsyncMock(return_value={"messages": []})

        wrapped = compiler._wrap_worker("worker_0", worker_agent)
        await wrapped(self._ai_last_state())

        sent = worker_agent.ainvoke.call_args.args[0]["messages"]
        assert self._role(sent[-1]) in ("user", "human")
        # 이전 워커 결과는 보존
        assert any(getattr(m, "name", None) == "worker_prev" for m in sent)

    @pytest.mark.asyncio
    async def test_tc11_analyze_context_not_assistant_last(self):
        """TC-11: _analyze_context — 비검색 워커 AIMessage-last → 마지막이 user."""
        from langchain_core.messages import AIMessage

        compiler, _ = _make_compiler()
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="분석 결과"))

        messages = [
            {"role": "user", "content": "분석해줘"},
            AIMessage(content="비검색 워커 출력", name="other_worker"),
        ]
        await compiler._analyze_context(mock_llm, "프롬프트", "분석해줘", messages)

        sent = mock_llm.ainvoke.call_args.args[0]
        assert self._role(sent[0]) == "system"
        assert self._role(sent[-1]) in ("user", "human")

    @pytest.mark.asyncio
    async def test_tc12_final_answer_user_last_noop(self):
        """TC-12: final_answer_node — 통상(user-last) conversation은 그대로 전달."""
        compiler, _ = _make_compiler()
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="최종 답변"))

        node = compiler._create_final_answer_node(mock_llm, "시스템 프롬프트")
        state = {
            "messages": [{"role": "user", "content": "질문"}],
            "token_usage": 0,
            "token_limit": 8000,
            "last_worker_id": "",
            "charts": [],
        }
        await node(state)

        sent = mock_llm.ainvoke.call_args.args[0]
        assert self._role(sent[0]) == "system"
        assert self._role(sent[-1]) in ("user", "human")
        # no-op: system + 기존 user 1건 = 2건 (지시 메시지 미추가)
        assert len(sent) == 2

    @pytest.mark.asyncio
    async def test_tc12b_final_answer_assistant_last_guarded(self):
        """TC-12b: final_answer_node — name 없는 assistant-last도 user로 교정."""
        from langchain_core.messages import AIMessage

        compiler, _ = _make_compiler()
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="최종 답변"))

        node = compiler._create_final_answer_node(mock_llm, "시스템 프롬프트")
        state = {
            "messages": [
                {"role": "user", "content": "질문"},
                AIMessage(content="draft answer"),  # name 없음 → conversation에 포함
            ],
            "token_usage": 0,
            "token_limit": 8000,
            "last_worker_id": "",
            "charts": [],
        }
        await node(state)

        sent = mock_llm.ainvoke.call_args.args[0]
        assert self._role(sent[-1]) in ("user", "human")
