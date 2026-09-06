"""supervisor → worker 작업 지시(worker_task) 전달 테스트.

Design Ref: worker-context-injection §3.1 / §4.1 / §8.3 L2 #4~9 —
supervisor만 에이전트 프롬프트를 보므로, 선택한 워커가 지금 할 일을
task로 명시해 내려보낸다. 부재 시 기존 범용 문구로 폴백한다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import (
    SupervisorDecision,
    build_initial_state,
    create_supervisor_node,
)
from src.domain.agent_builder.schemas import SupervisorConfig, WorkerDefinition


def _workers() -> list[WorkerDefinition]:
    return [
        WorkerDefinition(
            tool_id="mcp:srv:fetch", worker_id="scrape_worker",
            description="웹 스크래핑", sort_order=0,
        )
    ]


def _state(**overrides) -> dict:
    state = build_initial_state(
        messages=[{"role": "user", "content": "현재 분기 리포트 작성해주세요"}],
        config=SupervisorConfig(),
        available_workers=["scrape_worker"],
    )
    state.update(overrides)
    return state


def _node(decision: SupervisorDecision, hooks=None):
    llm = MagicMock()
    llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=decision
    )
    return create_supervisor_node(
        llm=llm, workers=_workers(), supervisor_prompt="금융 리서치 에이전트",
        hooks=hooks or DefaultHooks(), logger=MagicMock(),
    )


class TestSupervisorDecisionSchema:

    def test_task_field_exists_with_empty_default(self):
        """FR-04 — 구 모델·파싱 실패 대비 기본값이 있어야 한다."""
        decision = SupervisorDecision(next="w1", reasoning="이유")
        assert decision.task == ""

    def test_task_field_accepts_value(self):
        decision = SupervisorDecision(
            next="w1", reasoning="이유", task="2026년 3분기 실적을 수집하라",
        )
        assert decision.task == "2026년 3분기 실적을 수집하라"


class TestBuildInitialState:

    def test_initial_state_has_empty_worker_task(self):
        state = build_initial_state(
            messages=[], config=SupervisorConfig(), available_workers=[],
        )
        assert state["worker_task"] == ""


class TestSupervisorNodeEmitsTask:

    @pytest.mark.asyncio
    async def test_returns_worker_task_when_routing_to_worker(self):
        """FR-05 — 워커 라우팅 시 task가 상태로 전달된다."""
        node = _node(SupervisorDecision(
            next="scrape_worker", reasoning="스크래핑 필요",
            task="2026년 3분기 실적 자료를 수집하세요",
        ))
        result = await node(_state())
        assert result["next_worker"] == "scrape_worker"
        assert result["worker_task"] == "2026년 3분기 실적 자료를 수집하세요"

    @pytest.mark.asyncio
    async def test_returns_empty_task_when_llm_omits_it(self):
        node = _node(SupervisorDecision(next="scrape_worker", reasoning="이유"))
        result = await node(_state())
        assert result["worker_task"] == ""

    @pytest.mark.asyncio
    async def test_clears_task_on_finish(self):
        """직전 턴의 task가 종료 경로로 새어 나가지 않는다."""
        node = _node(SupervisorDecision(
            next="FINISH", reasoning="완료", task="쓰이면 안 되는 지시",
        ))
        result = await node(_state(last_worker_id="scrape_worker"))
        assert result["next_worker"] == "__end__"
        assert result.get("worker_task", "") == ""

    @pytest.mark.asyncio
    async def test_clears_task_on_forced_routing(self):
        """강제 라우팅은 SupervisorDecision을 거치지 않으므로 task가 비어야 한다."""
        hooks = MagicMock()
        hooks.force_worker = MagicMock(return_value="scrape_worker")
        hooks.skip_workers = MagicMock(return_value=[])
        node = _node(
            SupervisorDecision(next="scrape_worker", reasoning="이유", task="무시됨"),
            hooks=hooks,
        )
        result = await node(_state(worker_task="이전 턴 지시"))
        assert result["next_worker"] == "scrape_worker"
        assert result.get("worker_task", "") == ""

    @pytest.mark.asyncio
    async def test_decision_prompt_asks_for_task(self):
        """supervisor 프롬프트가 task 작성을 요구해야 LLM이 채운다."""
        llm = MagicMock()
        llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=SupervisorDecision(next="scrape_worker", reasoning="이유")
        )
        node = create_supervisor_node(
            llm=llm, workers=_workers(), supervisor_prompt="금융 리서치 에이전트",
            hooks=DefaultHooks(), logger=MagicMock(),
        )
        await node(_state())
        messages = llm.with_structured_output.return_value.ainvoke.call_args.args[0]
        system_content = messages[0]["content"]
        assert "task" in system_content


class TestWrapWorkerAppendsTask:
    """§4.1 핵심 — ensure_user_tail은 tail이 user면 no-op이므로 별도 append."""

    @pytest.mark.asyncio
    async def test_appends_task_when_tail_is_user_message(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from src.application.agent_builder.workflow_compiler import WorkflowCompiler

        captured = {}

        class _Agent:
            async def ainvoke(self, payload):
                captured["messages"] = payload["messages"]
                return {"messages": [AIMessage(content="결과")]}

        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(), logger=MagicMock(),
        )
        wrapped = compiler._wrap_worker("scrape_worker", _Agent())

        state = _state(worker_task="2026년 3분기 실적을 수집하세요")
        state["messages"] = [HumanMessage(content="현재 분기 리포트 작성해주세요")]
        await wrapped(state)

        last = captured["messages"][-1]
        assert "2026년 3분기 실적을 수집하세요" in last.content

    @pytest.mark.asyncio
    async def test_appends_task_when_tail_is_ai_message(self):
        from langchain_core.messages import AIMessage
        from src.application.agent_builder.workflow_compiler import WorkflowCompiler

        captured = {}

        class _Agent:
            async def ainvoke(self, payload):
                captured["messages"] = payload["messages"]
                return {"messages": [AIMessage(content="결과")]}

        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(), logger=MagicMock(),
        )
        wrapped = compiler._wrap_worker("scrape_worker", _Agent())

        state = _state(worker_task="이어서 요약하세요")
        state["messages"] = [AIMessage(content="이전 워커 결과", name="prev")]
        await wrapped(state)

        contents = [getattr(m, "content", "") for m in captured["messages"]]
        assert any("이어서 요약하세요" in c for c in contents)
        # prefill 방어 — 마지막이 AI 메시지로 끝나지 않는다
        assert getattr(captured["messages"][-1], "type", "") != "ai"

    @pytest.mark.asyncio
    async def test_falls_back_to_generic_instruction_without_task(self):
        from langchain_core.messages import AIMessage
        from src.application.agent_builder.workflow_compiler import WorkflowCompiler

        captured = {}

        class _Agent:
            async def ainvoke(self, payload):
                captured["messages"] = payload["messages"]
                return {"messages": [AIMessage(content="결과")]}

        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(), logger=MagicMock(),
        )
        wrapped = compiler._wrap_worker("scrape_worker", _Agent())

        state = _state()  # worker_task 없음
        state["messages"] = [AIMessage(content="이전 결과", name="prev")]
        await wrapped(state)

        contents = [getattr(m, "content", "") for m in captured["messages"]]
        assert any("당신의 역할에 해당하는 작업" in c for c in contents)

    @pytest.mark.asyncio
    async def test_output_contract_unchanged(self):
        """worker-toolmessage-leak-fix 규약: 최종 AIMessage(name) 1건."""
        from langchain_core.messages import AIMessage, HumanMessage
        from src.application.agent_builder.workflow_compiler import WorkflowCompiler

        class _Agent:
            async def ainvoke(self, payload):
                return {"messages": [AIMessage(content="워커 답변")]}

        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(), logger=MagicMock(),
        )
        wrapped = compiler._wrap_worker("scrape_worker", _Agent())

        state = _state(worker_task="작업 지시")
        state["messages"] = [HumanMessage(content="질문")]
        result = await wrapped(state)

        assert len(result["messages"]) == 1
        assert result["messages"][0].name == "scrape_worker"
        assert result["messages"][0].content == "워커 답변"
        assert result["last_worker_id"] == "scrape_worker"

    @pytest.mark.asyncio
    async def test_does_not_mutate_state_messages(self):
        """LangGraph state 공유 안전 — 원본 리스트를 변형하지 않는다."""
        from langchain_core.messages import AIMessage, HumanMessage
        from src.application.agent_builder.workflow_compiler import WorkflowCompiler

        class _Agent:
            async def ainvoke(self, payload):
                return {"messages": [AIMessage(content="결과")]}

        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(), logger=MagicMock(),
        )
        wrapped = compiler._wrap_worker("scrape_worker", _Agent())

        original = [HumanMessage(content="질문")]
        state = _state(worker_task="작업 지시")
        state["messages"] = original
        await wrapped(state)

        assert len(original) == 1


class TestBlockedToolCallStepSummary:
    """GAP-02 / FR-09 — 도구 차단 사실이 run step output_summary로 노출된다."""

    @staticmethod
    def _compiler_and_wrapped():
        from src.application.agent_builder.workflow_compiler import WorkflowCompiler
        compiler = WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(), logger=MagicMock(),
        )
        return compiler

    @pytest.mark.asyncio
    async def test_emits_step_summary_when_tool_call_blocked(self):
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
        from src.application.agent_run.step_tracking import STEP_OUTPUT_SUMMARY_KEY
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy

        blocked_text = ToolArgumentPolicy.build_blocked_message(
            "https://www.example.com/financial-market-2026-09-03"
        )

        class _Agent:
            async def ainvoke(self, payload):
                return {"messages": [
                    ToolMessage(content=blocked_text, tool_call_id="c1"),
                    AIMessage(content="확인된 대상이 없어 조회하지 못했습니다"),
                ]}

        compiler = self._compiler_and_wrapped()
        wrapped = compiler._wrap_worker("scrape_worker", _Agent())

        state = _state()
        state["messages"] = [HumanMessage(content="현재 분기 리포트 작성해주세요")]
        result = await wrapped(state)

        summary = result.get(STEP_OUTPUT_SUMMARY_KEY)
        assert summary is not None
        assert "차단" in summary

    @pytest.mark.asyncio
    async def test_no_step_summary_when_nothing_blocked(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from src.application.agent_run.step_tracking import STEP_OUTPUT_SUMMARY_KEY

        class _Agent:
            async def ainvoke(self, payload):
                return {"messages": [AIMessage(content="정상 결과")]}

        compiler = self._compiler_and_wrapped()
        wrapped = compiler._wrap_worker("scrape_worker", _Agent())

        state = _state()
        state["messages"] = [HumanMessage(content="질문")]
        result = await wrapped(state)

        assert STEP_OUTPUT_SUMMARY_KEY not in result

    @pytest.mark.asyncio
    async def test_output_contract_still_single_ai_message(self):
        """차단이 있어도 워커 출력 규약은 유지된다."""
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy

        class _Agent:
            async def ainvoke(self, payload):
                return {"messages": [
                    ToolMessage(
                        content=ToolArgumentPolicy.build_blocked_message("https://example.com/x"),
                        tool_call_id="c1",
                    ),
                    AIMessage(content="최종 답변"),
                ]}

        compiler = self._compiler_and_wrapped()
        wrapped = compiler._wrap_worker("scrape_worker", _Agent())

        state = _state()
        state["messages"] = [HumanMessage(content="질문")]
        result = await wrapped(state)

        assert len(result["messages"]) == 1
        assert result["messages"][0].name == "scrape_worker"
        assert result["messages"][0].content == "최종 답변"
