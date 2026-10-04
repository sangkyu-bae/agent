"""WorkflowCompiler 멀티 에이전트 컴파일 테스트."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.policies import (
    CircularReferenceError,
    NestingDepthExceededError,
)
from src.domain.agent_builder.schemas import (
    AgentDefinition,
    WorkerDefinition,
    WorkflowDefinition,
)
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="gpt-4o-mini", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _make_agent(
    agent_id: str = "sub-1",
    workers: list[WorkerDefinition] | None = None,
) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=agent_id, user_id="user-1", name="서브 에이전트",
        description="테스트", system_prompt="테스트 프롬프트",
        flow_hint="test", llm_model_id="model-1", status="active",
        workers=workers or [
            WorkerDefinition(
                tool_id="tavily_search", worker_id="tavily_worker",
                description="웹검색", sort_order=0,
            )
        ],
        created_at=now, updated_at=now,
    )


def _make_compiler_with_repo(sub_agent=None):
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=MagicMock())
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    logger = MagicMock()
    repo = AsyncMock()
    repo.find_by_id = AsyncMock(return_value=sub_agent)

    compiler = WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=logger,
        agent_repository=repo,
    )
    return compiler, repo


def _workflow_with_sub_agent(ref_id: str = "sub-1") -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt="상위 에이전트",
        workers=[
            WorkerDefinition(
                tool_id=f"sub_agent_{ref_id[:8]}",
                worker_id="sub_agent_worker_0",
                description="서브 에이전트",
                sort_order=0,
                worker_type="sub_agent",
                ref_agent_id=ref_id,
            ),
        ],
        flow_hint="sub_agent",
    )


def _workflow_mixed() -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt="혼합 에이전트",
        workers=[
            WorkerDefinition(
                tool_id="tavily_search", worker_id="tool_worker_0",
                description="웹검색", sort_order=0, worker_type="tool",
            ),
            WorkerDefinition(
                tool_id="sub_agent_sub-1",
                worker_id="sub_agent_worker_1",
                description="서브 에이전트",
                sort_order=1,
                worker_type="sub_agent",
                ref_agent_id="sub-1",
            ),
        ],
        flow_hint="mixed",
    )


class TestCompileSubAgent:
    @pytest.mark.asyncio
    async def test_compile_sub_agent_produces_graph(self):
        sub_agent = _make_agent("sub-1")
        compiler, _ = _make_compiler_with_repo(sub_agent)
        workflow = _workflow_with_sub_agent("sub-1")
        with patch("src.application.agent_builder.workflow_compiler.create_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                visited={"parent-1"},
            )
        assert graph is not None

    @pytest.mark.asyncio
    async def test_compile_mixed_workers(self):
        sub_agent = _make_agent("sub-1")
        compiler, _ = _make_compiler_with_repo(sub_agent)
        workflow = _workflow_mixed()
        with patch("src.application.agent_builder.workflow_compiler.create_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                visited={"parent-1"},
            )
        node_names = set(graph.get_graph().nodes.keys())
        assert "tool_worker_0" in node_names
        assert "sub_agent_worker_1" in node_names

    @pytest.mark.asyncio
    async def test_compile_circular_ref_raises(self):
        sub_agent = _make_agent("sub-1")
        compiler, _ = _make_compiler_with_repo(sub_agent)
        workflow = _workflow_with_sub_agent("sub-1")
        with pytest.raises(CircularReferenceError, match="순환참조"):
            await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                visited={"sub-1"},
            )

    @pytest.mark.asyncio
    async def test_compile_depth_exceeded_raises(self):
        compiler, _ = _make_compiler_with_repo()
        workflow = _workflow_with_sub_agent("sub-1")
        with pytest.raises(NestingDepthExceededError, match="중첩 깊이"):
            await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                depth=3,
            )

    @pytest.mark.asyncio
    async def test_compile_sub_agent_not_found_raises(self):
        compiler, repo = _make_compiler_with_repo(sub_agent=None)
        workflow = _workflow_with_sub_agent("missing-id")
        with pytest.raises(ValueError, match="서브 에이전트를 찾을 수 없습니다"):
            await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                visited={"parent-1"},
            )

    @pytest.mark.asyncio
    async def test_compile_no_repo_raises(self):
        tool_factory = MagicMock()
        tool_factory.create = MagicMock(return_value=MagicMock())
        llm_factory = MagicMock(spec=LLMFactoryInterface)
        llm_factory.create.return_value = MagicMock()
        compiler = WorkflowCompiler(
            tool_factory=tool_factory, llm_factory=llm_factory,
            logger=MagicMock(), agent_repository=None,
        )
        workflow = _workflow_with_sub_agent("sub-1")
        with pytest.raises(ValueError, match="agent_repository"):
            await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                visited=set(),
            )


class TestWrapSubAgent:
    @pytest.mark.asyncio
    async def test_wrap_sub_agent_task_delegation(self):
        compiler, _ = _make_compiler_with_repo()
        mock_ai_msg = MagicMock()
        mock_ai_msg.content = "서브 에이전트 결과입니다."
        mock_ai_msg.type = "ai"
        mock_sub_graph = AsyncMock()
        mock_sub_graph.ainvoke.return_value = {
            "messages": [mock_ai_msg],
            "token_usage": 100,
        }

        wrapped = compiler._wrap_sub_agent("sub_worker_0", mock_sub_graph)

        user_msg = MagicMock()
        user_msg.content = "문서를 분석해주세요"
        state = {
            "messages": [user_msg],
            "token_usage": 50,
            "token_limit": 8000,
        }

        result = await wrapped(state)
        assert result["last_worker_id"] == "sub_worker_0"
        assert result["token_usage"] == 150
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "서브 에이전트 결과입니다."

        call_args = mock_sub_graph.ainvoke.call_args[0][0]
        assert call_args["messages"][0]["content"] == "문서를 분석해주세요"


# ── subagent-context-scope (Design §8.4 C0~C6) ────────────────────────


def _sub_graph_returning(content: str = "서브 에이전트 결과입니다.") -> AsyncMock:
    from langchain_core.messages import AIMessage

    graph = AsyncMock()
    graph.ainvoke.return_value = {
        "messages": [AIMessage(content=content)], "token_usage": 7,
    }
    return graph


def _parent_state(task: str = "w1 결과를 3줄로 요약") -> dict:
    from langchain_core.messages import AIMessage, HumanMessage

    return {
        "messages": [
            HumanMessage(content="X 조회해서 요약해줘"),
            AIMessage(content="w1 결과 본문", name="w1"),
        ],
        "worker_task": task,
        "token_usage": 10,
        "token_limit": 8000,
        "max_iterations": 20,
    }


class _FakeStrategy:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def build(self, state, worker_id):
        from src.application.agent_builder.sub_agent_context import SubAgentInput

        self.calls.append(worker_id)
        return SubAgentInput(
            messages=[{"role": "user", "content": "FAKE"}], summary="fake-summary",
        )


class TestSubAgentRuntimeNode:
    """C0 — 컴파일된 부모 그래프에서 서브에이전트 노드가 실제로 실행된다.

    회귀(3a25eb7): function_node_ids 도입 시 sub_agent 분기가 누락돼
    _wrap_worker가 함수에 .ainvoke를 호출 → AttributeError.
    """

    @pytest.mark.asyncio
    async def test_C0_서브에이전트_노드가_wrap_worker를_거치지_않는다(self):
        from langchain_core.messages import HumanMessage

        from src.application.agent_builder.supervisor_nodes import build_initial_state
        from src.domain.agent_builder.schemas import SupervisorConfig

        compiler, _ = _make_compiler_with_repo(_make_agent("sub-1"))
        sub_graph = _sub_graph_returning()
        real_node = compiler._wrap_sub_agent("sub_agent_worker_0", sub_graph)
        with patch.object(
            WorkflowCompiler, "_compile_sub_agent", AsyncMock(return_value=real_node),
        ):
            graph = await compiler.compile(
                _workflow_with_sub_agent("sub-1"), _make_llm_model(), "req-1",
                supervisor_config=SupervisorConfig(),
            )

        node = graph.builder.nodes["sub_agent_worker_0"].runnable
        state = build_initial_state(
            messages=[HumanMessage(content="q")], config=SupervisorConfig(),
            available_workers=["sub_agent_worker_0"],
        )
        out = await node.ainvoke(state)

        assert out["messages"][0].content == "서브 에이전트 결과입니다."
        assert out["last_worker_id"] == "sub_agent_worker_0"
        sub_graph.ainvoke.assert_awaited_once()


class TestSubAgentContextWiring:
    @pytest.mark.asyncio
    async def test_C1_기본_전략으로_원질문_참고자료_현재작업을_전달(self):
        compiler, _ = _make_compiler_with_repo()
        sub_graph = _sub_graph_returning()

        await compiler._wrap_sub_agent("sub_w", sub_graph)(_parent_state())

        sent = sub_graph.ainvoke.call_args.args[0]["messages"]
        assert [m["role"] for m in sent] == ["user", "user", "user"]
        assert sent[0]["content"] == "[원 질문]\nX 조회해서 요약해줘"
        assert "[w1 산출]\nw1 결과 본문" in sent[1]["content"]
        assert sent[2]["content"] == "[현재 작업]\nw1 결과를 3줄로 요약"

    @pytest.mark.asyncio
    async def test_C2_주입한_전략의_입력이_그대로_전달(self):
        compiler, _ = _make_compiler_with_repo()
        sub_graph = _sub_graph_returning()
        fake = _FakeStrategy()

        out = await compiler._wrap_sub_agent("sub_w", sub_graph, fake)(_parent_state())

        sent = sub_graph.ainvoke.call_args.args[0]["messages"]
        assert sent == [{"role": "user", "content": "FAKE"}]
        assert fake.calls == ["sub_w"]
        assert out["_step_output_summary"] == "fake-summary"

    @pytest.mark.asyncio
    async def test_C3_생성자_주입_전략이_resolve를_거쳐_래퍼로_간다(self):
        fake = _FakeStrategy()
        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(), logger=MagicMock(),
            agent_repository=AsyncMock(find_by_id=AsyncMock(
                return_value=_make_agent("sub-1"))),
            sub_agent_context_strategy=fake,
        )
        worker = _workflow_with_sub_agent("sub-1").workers[0]
        with patch.object(WorkflowCompiler, "compile", AsyncMock(return_value="G")), \
             patch.object(WorkflowCompiler, "_wrap_sub_agent") as wrap, \
             patch(
                 "src.application.agent_builder.workflow_compiler.resolve_strategy",
                 wraps=lambda w, d: d,
             ) as resolve:
            from src.domain.agent_builder.schemas import SupervisorConfig

            await compiler._compile_sub_agent(
                worker, _make_llm_model(), "req-1", 0.0, SupervisorConfig(),
                depth=1, visited=set(),
            )

        resolve.assert_called_once_with(worker, fake)
        wrap.assert_called_once_with(worker.worker_id, "G", fake)

    @pytest.mark.asyncio
    async def test_C4_요약을_싣고_기존_출력_계약은_유지(self):
        compiler, _ = _make_compiler_with_repo()

        out = await compiler._wrap_sub_agent("sub_w", _sub_graph_returning())(
            _parent_state()
        )

        assert out["_step_output_summary"].startswith("서브에이전트 입력: 원질문 O")
        assert "w1 결과 본문" not in out["_step_output_summary"]
        assert len(out["messages"]) == 1
        assert out["messages"][0].name == "sub_w"
        assert out["last_worker_id"] == "sub_w"
        assert out["token_usage"] == 17
        assert "approval_pending" not in out

    @pytest.mark.asyncio
    async def test_C4b_입력_로그에는_본문이_없다(self):
        """Design §6/§7 — 로그에는 길이·개수만, 질문·과제·참고자료 본문은 싣지 않는다."""
        compiler, _ = _make_compiler_with_repo()

        await compiler._wrap_sub_agent("sub_w", _sub_graph_returning())(_parent_state())

        built = [
            c for c in compiler._logger.info.call_args_list
            if c.args and c.args[0] == "sub_agent input built"
        ]
        assert len(built) == 1
        logged = repr(built[0])
        for body in ("X 조회해서 요약해줘", "w1 결과 본문", "w1 결과를 3줄로 요약"):
            assert body not in logged
        assert built[0].kwargs["worker_id"] == "sub_w"

    @pytest.mark.asyncio
    async def test_C5_전략_예외는_로그_후_현행_입력으로_진행(self):
        compiler, _ = _make_compiler_with_repo()
        broken = MagicMock()
        broken.build.side_effect = RuntimeError("boom")
        sub_graph = _sub_graph_returning()

        out = await compiler._wrap_sub_agent("sub_w", sub_graph, broken)(
            _parent_state()
        )

        sent = sub_graph.ainvoke.call_args.args[0]["messages"]
        assert sent == [{"role": "user", "content": "w1 결과 본문"}]
        assert out["messages"][0].content == "서브 에이전트 결과입니다."
        error_call = compiler._logger.error.call_args
        assert isinstance(error_call.kwargs["exception"], RuntimeError)
        assert out["_step_output_summary"] == "서브에이전트 입력: 레거시(마지막 메시지)"

    @pytest.mark.asyncio
    async def test_C6_init을_거치지_않은_인스턴스도_동작(self):
        compiler = WorkflowCompiler.__new__(WorkflowCompiler)
        compiler._logger = MagicMock()
        sub_graph = _sub_graph_returning()

        out = await compiler._wrap_sub_agent("sub_w", sub_graph)(_parent_state())

        assert out["last_worker_id"] == "sub_w"
        assert sub_graph.ainvoke.call_args.args[0]["messages"][-1]["content"] == (
            "[현재 작업]\nw1 결과를 3줄로 요약"
        )
