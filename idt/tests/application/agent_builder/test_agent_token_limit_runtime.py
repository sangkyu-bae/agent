"""agent-token-limit 실행 경로 테스트 (Design D6~D10).

- SupervisorConfig 에이전트 token_limit 주입 — 대화 실행·승인 재개 (D6)
- 서브 에이전트 독립 token_limit (D7)
- 토큰 가드 limit_reached + limit_reason (D8)
- final_answer 사유별 안내 블록 (D9)
- ANSWER_COMPLETED payload limit_reason (D10)
Plan SC: SC-1(가드 미발동), SC-3(도달 안내), SC-4(서브 독립)
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.errors import GraphRecursionError

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest
from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import (
    build_initial_state,
    create_supervisor_node,
)
from src.domain.agent_builder.policies import TokenLimitPolicy
from src.domain.agent_builder.schemas import SupervisorConfig, WorkerDefinition
from src.domain.agent_run.value_objects import AgentRunEventType
from tests.application.agent_builder.test_agent_iteration_limit import (
    _ai_message,
    _collect,
    _make_agent,
    _make_llm_model,
    _make_stream_use_case,
    _node_state,
)


def _supervisor():
    return create_supervisor_node(
        llm=MagicMock(),
        workers=[WorkerDefinition("tavily_search", "worker_0", "검색", 0)],
        supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
    )


# ── D8: 가드 신호 ──────────────────────────────────────────────────────


class TestGuardLimitReason:
    @pytest.mark.asyncio
    async def test_token_guard_sets_limit_reached_and_reason(self):
        """토큰 가드도 반복 가드와 같은 종료 경로를 탄다 (Plan FR-06)."""
        mock_llm = MagicMock()
        fn = create_supervisor_node(
            llm=mock_llm,
            workers=[WorkerDefinition("tavily_search", "worker_0", "검색", 0)],
            supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
        )
        result = await fn(_node_state(token_usage=9000, token_limit=8000))
        assert result["next_worker"] == "__end__"
        assert result["limit_reached"] is True
        assert result["limit_reason"] == "token"
        assert result["finish_challenge_pending"] is False
        mock_llm.with_structured_output.assert_not_called()

    @pytest.mark.asyncio
    async def test_iteration_guard_sets_reason_iteration(self):
        result = await _supervisor()(
            _node_state(iteration_count=10, max_iterations=10)
        )
        assert result["limit_reached"] is True
        assert result["limit_reason"] == "iteration"

    @pytest.mark.asyncio
    async def test_token_usage_below_agent_limit_does_not_trigger(self):
        """SC-1: 재현 런(8869)은 기본 50000 아래라 가드가 걸리지 않는다."""
        mock_llm = MagicMock()
        structured = AsyncMock()
        structured.ainvoke.return_value = MagicMock(
            next="FINISH", answer="", task="", reasoning="done",
        )
        mock_llm.with_structured_output.return_value = structured
        fn = create_supervisor_node(
            llm=mock_llm,
            workers=[WorkerDefinition("tavily_search", "worker_0", "검색", 0)],
            supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
        )
        result = await fn(_node_state(
            token_usage=8869, token_limit=TokenLimitPolicy.DEFAULT,
        ))
        mock_llm.with_structured_output.assert_called_once()
        assert "limit_reached" not in result or result["limit_reached"] is False

    def test_initial_state_has_empty_reason(self):
        state = build_initial_state(
            messages=[], config=SupervisorConfig(), available_workers=[],
        )
        assert state["limit_reason"] == ""
        assert state["token_limit"] == TokenLimitPolicy.DEFAULT


# ── D9: final_answer 안내 블록 ─────────────────────────────────────────


class TestFinalAnswerLimitReasonNotice:
    def _make_node(self, mock_llm):
        from src.application.agent_builder.workflow_compiler import (
            WorkflowCompiler,
        )

        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(),
            logger=MagicMock(),
        )
        return compiler._create_final_answer_node(mock_llm, "시스템 프롬프트")

    @staticmethod
    def _run(mock_llm_holder: dict, **state_extra):
        from langchain_core.messages import AIMessage, HumanMessage

        llm = AsyncMock()
        llm.ainvoke.return_value = AIMessage(content="답변")
        mock_llm_holder["llm"] = llm
        return {
            "messages": [
                HumanMessage(content="질문"),
                AIMessage(content="[w 검색결과]\n데이터", name="w"),
            ],
            "token_usage": 0,
            **state_extra,
        }

    @staticmethod
    def _system_content(mock_llm) -> str:
        first = mock_llm.ainvoke.call_args[0][0][0]
        return first["content"] if isinstance(first, dict) else first.content

    @pytest.mark.asyncio
    async def test_token_reason_uses_token_notice(self):
        holder: dict = {}
        state = self._run(holder, limit_reached=True, limit_reason="token")
        await self._make_node(holder["llm"])(state)
        content = self._system_content(holder["llm"])
        assert "토큰 한도 도달 안내" in content
        assert "반복 한도 도달 안내" not in content

    @pytest.mark.asyncio
    async def test_iteration_reason_uses_iteration_notice(self):
        holder: dict = {}
        state = self._run(holder, limit_reached=True, limit_reason="iteration")
        await self._make_node(holder["llm"])(state)
        assert "반복 한도 도달 안내" in self._system_content(holder["llm"])

    @pytest.mark.asyncio
    async def test_reached_without_reason_uses_generic_notice(self):
        """재개 스냅샷 등 limit_reason 키가 없는 state와의 하위호환."""
        holder: dict = {}
        state = self._run(holder, limit_reached=True)
        await self._make_node(holder["llm"])(state)
        assert "실행 한도 도달 안내" in self._system_content(holder["llm"])


# ── D10: payload limit_reason ──────────────────────────────────────────


class TestAnswerCompletedLimitReason:
    @staticmethod
    def _answer(events):
        return next(
            e for e in events
            if e.event_type == AgentRunEventType.ANSWER_COMPLETED
        )

    @pytest.mark.asyncio
    async def test_reason_in_payload(self):
        agent = _make_agent()
        events_in = [{
            "event": "on_chain_end", "name": "supervisor",
            "data": {"output": {
                "next_worker": "__end__",
                "limit_reached": True, "limit_reason": "token",
            }},
            "metadata": {}, "run_id": "sv",
        }]
        use_case, _, _ = _make_stream_use_case(agent, astream_event_list=events_in)
        events = await _collect(use_case.stream(
            agent.id, RunAgentRequest(query="x", user_id="user-1"), "req-1",
        ))
        payload = self._answer(events).payload
        assert payload["limit_reached"] is True
        assert payload["limit_reason"] == "token"

    @pytest.mark.asyncio
    async def test_reason_absent_when_not_reached(self):
        agent = _make_agent()
        use_case, _, _ = _make_stream_use_case(agent, astream_event_list=[])
        events = await _collect(use_case.stream(
            agent.id, RunAgentRequest(query="x", user_id="user-1"), "req-1",
        ))
        payload = self._answer(events).payload
        assert "limit_reached" not in payload
        assert "limit_reason" not in payload

    @pytest.mark.asyncio
    async def test_recursion_error_degrade_reports_iteration(self):
        agent = _make_agent()
        events_in = [{
            "event": "on_chain_end", "name": "LangGraph",
            "data": {"output": {"messages": [_ai_message("부분 답변")]}},
            "metadata": {}, "run_id": "top",
        }]

        def _factory(*args, **kwargs):
            async def _gen():
                for e in events_in:
                    yield e
                raise GraphRecursionError("recursion limit hit")
            return _gen()

        use_case, _, _ = _make_stream_use_case(agent, astream_gen=_factory)
        events = await _collect(use_case.stream(
            agent.id, RunAgentRequest(query="x", user_id="user-1"), "req-1",
        ))
        payload = self._answer(events).payload
        assert payload["limit_reached"] is True
        assert payload["limit_reason"] == "iteration"


# ── D6: SupervisorConfig 주입 ──────────────────────────────────────────


class TestTokenLimitInjection:
    @pytest.mark.asyncio
    async def test_stream_injects_agent_token_limit(self):
        agent = _make_agent()
        agent.token_limit = 12345
        use_case, _, compiler = _make_stream_use_case(agent)
        await _collect(use_case.stream(
            agent.id, RunAgentRequest(query="안녕", user_id="user-1"), "req-1",
        ))
        sv_config = compiler.compile.call_args.kwargs["supervisor_config"]
        assert sv_config.token_limit == 12345
        assert sv_config.max_iterations == agent.max_iterations

    @pytest.mark.asyncio
    async def test_resume_injects_agent_token_limit(self):
        """승인 재개 경로도 같은 값을 쓴다 (Plan FR-04)."""
        uc = RunAgentUseCase.__new__(RunAgentUseCase)
        uc._tool_access_resolver = None
        uc._logger = MagicMock()
        uc._tracker = None
        uc._agent_skill_repo = None
        uc._memory_assembler = None
        uc._compiler = MagicMock()
        uc._compiler.compile = AsyncMock(return_value=MagicMock(
            ainvoke=AsyncMock(return_value={"messages": []})
        ))
        uc._llm_model_repository = MagicMock()
        uc._llm_model_repository.find_by_id = AsyncMock(return_value=_make_llm_model())
        uc._parse_result = MagicMock(return_value=("답", None))

        agent = _make_agent()
        agent.token_limit = 23456
        await uc._resume_graph({}, agent, "req-1", subject_user_id="u")
        sv_config = uc._compiler.compile.call_args.kwargs["supervisor_config"]
        assert sv_config.token_limit == 23456


# ── D7: 서브 에이전트 독립 한도 ───────────────────────────────────────


class TestSubAgentTokenLimit:
    def _wrapped(self, **kwargs):
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
        sub_graph = AsyncMock()
        sub_graph.ainvoke.return_value = {"messages": [mock_ai], "token_usage": 10}
        return compiler._wrap_sub_agent("sub_w", sub_graph, **kwargs), sub_graph

    @pytest.mark.asyncio
    async def test_uses_own_limit_not_parent_half(self):
        """SC-4: 서브 정의 20000, 부모 100000 → 20000 (절반 50000 아님)."""
        wrapped, sub_graph = self._wrapped(token_limit=20000)
        user_msg = MagicMock()
        user_msg.content = "작업"
        await wrapped({
            "messages": [user_msg], "token_usage": 0,
            "token_limit": 100000, "max_iterations": 100,
        })
        sub_initial = sub_graph.ainvoke.call_args.args[0]
        assert sub_initial["token_limit"] == 20000

    @pytest.mark.asyncio
    async def test_missing_arg_falls_back_to_policy_default(self):
        wrapped, sub_graph = self._wrapped()
        user_msg = MagicMock()
        user_msg.content = "작업"
        await wrapped({
            "messages": [user_msg], "token_usage": 0, "token_limit": 8000,
        })
        sub_initial = sub_graph.ainvoke.call_args.args[0]
        assert sub_initial["token_limit"] == TokenLimitPolicy.DEFAULT

    @pytest.mark.asyncio
    async def test_compile_passes_sub_agent_definition_limit(self):
        """_compile_sub_agent는 조회한 서브 정의의 token_limit를 넘긴다."""
        from src.application.agent_builder.workflow_compiler import (
            WorkflowCompiler,
        )

        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(),
            logger=MagicMock(),
        )
        sub_agent = _make_agent()
        sub_agent.token_limit = 33333
        compiler._agent_repository = MagicMock()
        compiler._agent_repository.find_by_id = AsyncMock(return_value=sub_agent)
        compiler._llm_model_repository = None
        compiler.compile = AsyncMock(return_value=MagicMock())
        compiler._wrap_sub_agent = MagicMock(return_value=lambda s: s)

        worker_def = WorkerDefinition(
            tool_id="sub_agent", worker_id="sub_w", description="d",
            sort_order=0, worker_type="sub_agent", ref_agent_id=sub_agent.id,
        )
        await compiler._compile_sub_agent(
            worker_def, _make_llm_model(), "req-1", 0.7, SupervisorConfig(),
            1, set(), tracker=None, callback=None, run_id=None,
            auth_ctx=None, include_user_context=True, subject_user_id=None,
            tool_access=None, excluded_sink=None,
        )
        assert compiler._wrap_sub_agent.call_args.kwargs["token_limit"] == 33333


# ── Act-1 (Analysis G-2): 중첩 그래프 이벤트는 latch하지 않는다 ─────────────


class TestNestedLimitLatch:
    @staticmethod
    def _answer(events):
        return next(
            e for e in events
            if e.event_type == AgentRunEventType.ANSWER_COMPLETED
        )

    @pytest.mark.asyncio
    async def test_nested_sub_agent_guard_does_not_latch_parent(self):
        """서브 에이전트 supervisor(parent_ids 3)의 한도 신호는 부모 payload에 안 올라간다."""
        agent = _make_agent()
        events_in = [{
            "event": "on_chain_end", "name": "supervisor",
            "parent_ids": ["root", "sub_w", "sub_graph"],
            "data": {"output": {
                "next_worker": "__end__",
                "limit_reached": True, "limit_reason": "token",
            }},
            "metadata": {}, "run_id": "sub-sv",
        }]
        use_case, _, _ = _make_stream_use_case(agent, astream_event_list=events_in)
        events = await _collect(use_case.stream(
            agent.id, RunAgentRequest(query="x", user_id="user-1"), "req-1",
        ))
        payload = self._answer(events).payload
        assert "limit_reached" not in payload
        assert "limit_reason" not in payload

    @pytest.mark.asyncio
    async def test_top_level_guard_still_latches(self):
        """최상위 supervisor(parent_ids 1)와 parent_ids 부재(구 픽스처)는 기존대로 latch."""
        agent = _make_agent()
        events_in = [{
            "event": "on_chain_end", "name": "supervisor",
            "parent_ids": ["root"],
            "data": {"output": {
                "next_worker": "__end__",
                "limit_reached": True, "limit_reason": "iteration",
            }},
            "metadata": {}, "run_id": "sv",
        }]
        use_case, _, _ = _make_stream_use_case(agent, astream_event_list=events_in)
        events = await _collect(use_case.stream(
            agent.id, RunAgentRequest(query="x", user_id="user-1"), "req-1",
        ))
        payload = self._answer(events).payload
        assert payload["limit_reached"] is True
        assert payload["limit_reason"] == "iteration"
