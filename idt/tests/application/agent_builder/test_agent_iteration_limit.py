"""agent-recursion-limit 실행 경로 테스트 (Design D1, D3, D5~D10).

- supervisor 가드의 limit_reached 플래그 (D5)
- route_to_worker_or_final 확장 (D6)
- final_answer 안내 지시 (D7-①)
- ANSWER_COMPLETED payload limit_reached (D7-③)
- graph_config recursion_limit 파생 (D3)
- SupervisorConfig 에이전트 값 주입 (D1)
- GraphRecursionError 안전망 (D9)
- sub-agent 절반 상속 + recursion_limit (D8)
- API 요청 스키마 검증 (D10)
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.errors import GraphRecursionError

from src.application.agent_builder import run_agent_use_case as run_mod
from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import (
    CreateAgentRequest,
    RunAgentRequest,
    UpdateAgentRequest,
)
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_builder.policies import IterationLimitPolicy
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.agent_run.value_objects import AgentRunEventType
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.llm_model.entity import LlmModel


# ── 공용 fixture ────────────────────────────────────────────────────────


def _make_agent(max_iterations: int = 25) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name="테스트 에이전트",
        description="설명",
        system_prompt="시스템 프롬프트",
        flow_hint="힌트",
        workers=[WorkerDefinition("tavily_search", "search_worker", "검색", 0)],
        llm_model_id="model-1",
        status="active",
        max_iterations=max_iterations,
        created_at=now,
        updated_at=now,
    )


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="GPT-4o Mini", description=None,
        api_key_env="OPENAI_API_KEY", max_tokens=128000,
        is_active=True, is_default=True, created_at=now, updated_at=now,
    )


def _ai_message(content: str, name: str | None = None):
    m = MagicMock()
    m.content = content
    m.name = name
    return m


def _node_state(**overrides) -> dict:
    base = {
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 10,
        "token_usage": 0,
        "token_limit": 8000,
        "next_worker": "",
        "last_worker_id": "",
        "available_workers": ["worker_0"],
        "quality_gate_enabled": False,
        "retry_counts": {},
        "max_retries_per_worker": 2,
        "forced_worker": "",
        "skipped_workers": [],
        "quality_gate_result": "",
        "limit_reached": False,
    }
    base.update(overrides)
    return base


def _make_stream_use_case(
    agent: AgentDefinition,
    astream_event_list: list[dict] | None = None,
    astream_gen=None,
):
    """test_run_agent_use_case_stream.py 하네스 축약판."""
    repository = MagicMock()
    llm_model_repository = MagicMock()
    compiler = MagicMock()
    message_repo = MagicMock()
    summary_repo = MagicMock()
    summarizer = MagicMock()
    tracker = MagicMock(spec=RunTracker)
    tracker.start_run = AsyncMock()
    tracker.complete_run = AsyncMock()
    tracker.fail_run = AsyncMock()

    repository.find_by_id = AsyncMock(return_value=agent)
    llm_model_repository.find_by_id = AsyncMock(return_value=_make_llm_model())
    message_repo.find_by_session = AsyncMock(return_value=[])
    saved_msg = MagicMock()
    saved_msg.id.value = 42
    message_repo.save = AsyncMock(return_value=saved_msg)
    summary_repo.find_latest_by_session = AsyncMock(return_value=None)
    summary_repo.save = AsyncMock()
    summarizer.summarize = AsyncMock(return_value="요약")

    mock_graph = MagicMock()
    if astream_gen is not None:
        mock_graph.astream_events = astream_gen
    else:
        events = list(astream_event_list or [])
        events.append({
            "event": "on_chain_end", "name": "LangGraph",
            "data": {"output": {"messages": [_ai_message("기본 답변")]}},
            "metadata": {}, "run_id": "top",
        })

        def _fake(*args, **kwargs):
            async def _gen():
                for e in events:
                    yield e
            return _gen()
        mock_graph.astream_events = _fake
    compiler.compile = AsyncMock(return_value=mock_graph)

    use_case = RunAgentUseCase(
        repository=repository,
        llm_model_repository=llm_model_repository,
        compiler=compiler,
        logger=MagicMock(),
        message_repo=message_repo,
        summary_repo=summary_repo,
        summarizer=summarizer,
        policy=SummarizationPolicy(),
        tracker=tracker,
    )
    return use_case, tracker, compiler


async def _collect(stream) -> list:
    return [ev async for ev in stream]


# ── D5: supervisor 가드 limit_reached ───────────────────────────────────


class TestSupervisorGuardLimitReached:
    @pytest.mark.asyncio
    async def test_iteration_guard_sets_limit_reached(self):
        from src.application.agent_builder.supervisor_hooks import DefaultHooks
        from src.application.agent_builder.supervisor_nodes import (
            create_supervisor_node,
        )

        mock_llm = MagicMock()
        fn = create_supervisor_node(
            llm=mock_llm,
            workers=[WorkerDefinition("tavily_search", "worker_0", "검색", 0)],
            supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
        )
        result = await fn(_node_state(iteration_count=10, max_iterations=10))
        assert result["next_worker"] == "__end__"
        assert result["limit_reached"] is True
        mock_llm.with_structured_output.assert_not_called()

    @pytest.mark.asyncio
    async def test_token_guard_does_not_set_limit_reached(self):
        """token_limit 가드는 현행 유지 — limit_reached 미설정 (D5)."""
        from src.application.agent_builder.supervisor_hooks import DefaultHooks
        from src.application.agent_builder.supervisor_nodes import (
            create_supervisor_node,
        )

        fn = create_supervisor_node(
            llm=MagicMock(),
            workers=[WorkerDefinition("tavily_search", "worker_0", "검색", 0)],
            supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
        )
        result = await fn(_node_state(token_usage=9000, token_limit=8000))
        assert result["next_worker"] == "__end__"
        assert "limit_reached" not in result

    def test_initial_state_has_limit_reached_false(self):
        from src.application.agent_builder.supervisor_nodes import (
            build_initial_state,
        )
        from src.domain.agent_builder.schemas import SupervisorConfig

        state = build_initial_state(
            messages=[], config=SupervisorConfig(), available_workers=[],
        )
        assert state["limit_reached"] is False


# ── D6: 라우팅 확장 ─────────────────────────────────────────────────────


class TestRouteWithLimitReached:
    def test_limit_reached_without_worker_goes_to_final_answer(self):
        from src.application.agent_builder.supervisor_nodes import (
            route_to_worker_or_final,
        )

        state = _node_state(
            next_worker="__end__", last_worker_id="", limit_reached=True,
        )
        assert route_to_worker_or_final(state) == "final_answer"

    def test_plain_end_without_worker_still_ends(self):
        """단순 대화(FINISH, 한도 미도달)는 기존대로 즉시 종료."""
        from src.application.agent_builder.supervisor_nodes import (
            route_to_worker_or_final,
        )

        state = _node_state(
            next_worker="__end__", last_worker_id="", limit_reached=False,
        )
        assert route_to_worker_or_final(state) == "__end__"

    def test_limit_reached_with_worker_goes_to_final_answer(self):
        from src.application.agent_builder.supervisor_nodes import (
            route_to_worker_or_final,
        )

        state = _node_state(
            next_worker="__end__", last_worker_id="worker_0", limit_reached=True,
        )
        assert route_to_worker_or_final(state) == "final_answer"


# ── D7-①: final_answer 안내 지시 ────────────────────────────────────────


class TestFinalAnswerLimitNotice:
    def _make_node(self, mock_llm):
        from src.application.agent_builder.workflow_compiler import (
            WorkflowCompiler,
        )

        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(),
            logger=MagicMock(),
        )
        return compiler._create_final_answer_node(mock_llm, "시스템 프롬프트")

    def _mock_llm(self):
        from langchain_core.messages import AIMessage

        llm = AsyncMock()
        llm.ainvoke.return_value = AIMessage(content="답변")
        return llm

    @staticmethod
    def _system_content(mock_llm) -> str:
        first = mock_llm.ainvoke.call_args[0][0][0]
        return first["content"] if isinstance(first, dict) else first.content

    @pytest.mark.asyncio
    async def test_limit_reached_adds_notice_instruction(self):
        from langchain_core.messages import AIMessage, HumanMessage

        mock_llm = self._mock_llm()
        node = self._make_node(mock_llm)
        state = {
            "messages": [
                HumanMessage(content="질문"),
                AIMessage(content="[w 검색결과]\n데이터", name="w"),
            ],
            "token_usage": 0,
            "limit_reached": True,
        }
        await node(state)
        assert "반복 한도" in self._system_content(mock_llm)

    @pytest.mark.asyncio
    async def test_no_notice_when_limit_not_reached(self):
        from langchain_core.messages import AIMessage, HumanMessage

        mock_llm = self._mock_llm()
        node = self._make_node(mock_llm)
        state = {
            "messages": [
                HumanMessage(content="질문"),
                AIMessage(content="[w 검색결과]\n데이터", name="w"),
            ],
            "token_usage": 0,
        }
        await node(state)
        assert "반복 한도" not in self._system_content(mock_llm)


# ── D3: graph_config recursion_limit ────────────────────────────────────


class TestGraphConfigRecursionLimit:
    def test_recursion_limit_derived_from_agent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(run_mod, "make_agent_run_tracer", lambda *a, **k: None)
        agent = _make_agent(max_iterations=100)

        cfg = RunAgentUseCase._build_graph_config(
            agent=agent, session_id="s-1", run_id=None,
            user_id="user-1", callback=None,
        )
        assert cfg["recursion_limit"] == (
            IterationLimitPolicy.derive_recursion_limit(100)
        )


# ── D1: SupervisorConfig 주입 ───────────────────────────────────────────


class TestSupervisorConfigInjection:
    @pytest.mark.asyncio
    async def test_agent_max_iterations_injected_into_compile(self):
        agent = _make_agent(max_iterations=42)
        use_case, _, compiler = _make_stream_use_case(agent)
        request = RunAgentRequest(query="안녕", user_id="user-1")

        await _collect(use_case.stream(agent.id, request, "req-1"))

        sv_config = compiler.compile.call_args.kwargs["supervisor_config"]
        assert sv_config.max_iterations == 42


# ── D7-③: ANSWER_COMPLETED payload ─────────────────────────────────────


class TestAnswerCompletedLimitFlag:
    @pytest.mark.asyncio
    async def test_limit_reached_flag_in_payload(self):
        agent = _make_agent()
        events_in = [{
            "event": "on_chain_end", "name": "supervisor",
            "data": {"output": {"next_worker": "__end__", "limit_reached": True}},
            "metadata": {}, "run_id": "sv",
        }]
        use_case, _, _ = _make_stream_use_case(agent, astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        answer = next(
            e for e in events
            if e.event_type == AgentRunEventType.ANSWER_COMPLETED
        )
        assert answer.payload["limit_reached"] is True

    @pytest.mark.asyncio
    async def test_flag_absent_when_not_reached(self):
        agent = _make_agent()
        use_case, _, _ = _make_stream_use_case(agent, astream_event_list=[])
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        answer = next(
            e for e in events
            if e.event_type == AgentRunEventType.ANSWER_COMPLETED
        )
        assert "limit_reached" not in answer.payload


# ── D9: GraphRecursionError 안전망 ──────────────────────────────────────


class TestGraphRecursionErrorSafetyNet:
    @staticmethod
    def _gen_yield_then_raise(events: list[dict]):
        def _factory(*args, **kwargs):
            async def _gen():
                for e in events:
                    yield e
                raise GraphRecursionError("recursion limit hit")
            return _gen()
        return _factory

    @pytest.mark.asyncio
    async def test_degraded_answer_when_messages_accumulated(self):
        """축적 메시지가 있으면 RUN_FAILED 대신 강등 답변 + RUN_COMPLETED."""
        agent = _make_agent()
        events_in = [{
            "event": "on_chain_end", "name": "LangGraph",
            "data": {"output": {"messages": [_ai_message("부분 수집 답변")]}},
            "metadata": {}, "run_id": "top",
        }]
        use_case, tracker, _ = _make_stream_use_case(
            agent, astream_gen=self._gen_yield_then_raise(events_in),
        )
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        types = [e.event_type for e in events]
        assert AgentRunEventType.RUN_FAILED not in types
        answer = next(
            e for e in events
            if e.event_type == AgentRunEventType.ANSWER_COMPLETED
        )
        assert answer.payload["answer"] == "부분 수집 답변"
        assert answer.payload["limit_reached"] is True
        assert events[-1].event_type == AgentRunEventType.RUN_COMPLETED
        tracker.complete_run.assert_awaited_once()
        tracker.fail_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_failed_when_nothing_accumulated(self):
        """축적 메시지가 없으면 기존 RUN_FAILED 경로."""
        agent = _make_agent()
        use_case, tracker, _ = _make_stream_use_case(
            agent, astream_gen=self._gen_yield_then_raise([]),
        )
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        assert events[-1].event_type == AgentRunEventType.RUN_FAILED
        tracker.fail_run.assert_awaited_once()


# ── D8: sub-agent 절반 상속 ─────────────────────────────────────────────


class TestSubAgentIterationLimit:
    @pytest.mark.asyncio
    async def test_sub_agent_gets_half_limit_and_recursion_config(self):
        from src.application.agent_builder.workflow_compiler import (
            WorkflowCompiler,
        )

        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(),
            logger=MagicMock(),
        )
        mock_ai = MagicMock()
        mock_ai.content = "서브 결과"
        mock_ai.type = "ai"
        mock_sub_graph = AsyncMock()
        mock_sub_graph.ainvoke.return_value = {
            "messages": [mock_ai], "token_usage": 10,
        }
        wrapped = compiler._wrap_sub_agent("sub_w", mock_sub_graph)

        user_msg = MagicMock()
        user_msg.content = "작업"
        await wrapped({
            "messages": [user_msg],
            "token_usage": 0,
            "token_limit": 8000,
            "max_iterations": 100,
        })

        sub_initial = mock_sub_graph.ainvoke.call_args.args[0]
        assert sub_initial["max_iterations"] == (
            IterationLimitPolicy.sub_agent_limit(100)
        )
        sub_config = mock_sub_graph.ainvoke.call_args.kwargs["config"]
        assert sub_config["recursion_limit"] == (
            IterationLimitPolicy.derive_recursion_limit(
                IterationLimitPolicy.sub_agent_limit(100)
            )
        )

    @pytest.mark.asyncio
    async def test_missing_max_iterations_falls_back_to_default(self):
        """기존 state(max_iterations 키 없음)와의 하위호환."""
        from src.application.agent_builder.workflow_compiler import (
            WorkflowCompiler,
        )

        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(),
            logger=MagicMock(),
        )
        mock_ai = MagicMock()
        mock_ai.content = "서브 결과"
        mock_ai.type = "ai"
        mock_sub_graph = AsyncMock()
        mock_sub_graph.ainvoke.return_value = {
            "messages": [mock_ai], "token_usage": 10,
        }
        wrapped = compiler._wrap_sub_agent("sub_w", mock_sub_graph)

        user_msg = MagicMock()
        user_msg.content = "작업"
        await wrapped({
            "messages": [user_msg], "token_usage": 0, "token_limit": 8000,
        })

        sub_initial = mock_sub_graph.ainvoke.call_args.args[0]
        assert sub_initial["max_iterations"] == (
            IterationLimitPolicy.sub_agent_limit(IterationLimitPolicy.DEFAULT)
        )


# ── D10: API 요청 스키마 ────────────────────────────────────────────────


class TestRequestSchemas:
    def test_create_default_25(self):
        req = CreateAgentRequest(
            user_request="테스트", name="봇", system_prompt="지침",
        )
        assert req.max_iterations == 25

    def test_create_range_validated(self):
        with pytest.raises(Exception):
            CreateAgentRequest(
                user_request="테스트", name="봇", system_prompt="지침",
                max_iterations=9,
            )
        with pytest.raises(Exception):
            CreateAgentRequest(
                user_request="테스트", name="봇", system_prompt="지침",
                max_iterations=1001,
            )

    def test_update_none_means_no_change(self):
        req = UpdateAgentRequest()
        assert req.max_iterations is None

    def test_update_range_validated(self):
        with pytest.raises(Exception):
            UpdateAgentRequest(max_iterations=5)
        assert UpdateAgentRequest(max_iterations=1000).max_iterations == 1000
