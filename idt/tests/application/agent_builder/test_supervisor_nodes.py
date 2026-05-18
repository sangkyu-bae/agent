"""supervisor_nodes 단위 테스트 (TC-02~10 + routing)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.domain.agent_builder.policies import QualityGatePolicy
from src.domain.agent_builder.schemas import SupervisorConfig, WorkerDefinition


def _make_state(**overrides) -> dict:
    base = {
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 10,
        "token_usage": 0,
        "token_limit": 8000,
        "next_worker": "",
        "last_worker_id": "",
        "available_workers": ["worker_0", "worker_1"],
        "quality_gate_enabled": False,
        "retry_counts": {},
        "max_retries_per_worker": 2,
        "forced_worker": "",
        "skipped_workers": [],
        "quality_gate_result": "",
    }
    base.update(overrides)
    return base


def _make_workers() -> list[WorkerDefinition]:
    return [
        WorkerDefinition("tavily_search", "worker_0", "웹 검색", 0),
        WorkerDefinition("perplexity_search", "worker_1", "딥 리서치", 1),
    ]


class TestBuildInitialState:
    def test_returns_correct_structure(self):
        from src.application.agent_builder.supervisor_nodes import build_initial_state

        config = SupervisorConfig()
        state = build_initial_state(
            messages=[{"role": "user", "content": "hello"}],
            config=config,
            available_workers=["worker_0", "worker_1"],
        )
        assert state["iteration_count"] == 0
        assert state["max_iterations"] == 10
        assert state["token_usage"] == 0
        assert state["token_limit"] == 8000
        assert state["available_workers"] == ["worker_0", "worker_1"]
        assert state["quality_gate_enabled"] is False
        assert state["retry_counts"] == {}
        assert state["max_retries_per_worker"] == 2
        assert state["forced_worker"] == ""
        assert state["skipped_workers"] == []
        assert state["quality_gate_result"] == ""

    def test_custom_config_applied(self):
        from src.application.agent_builder.supervisor_nodes import build_initial_state

        config = SupervisorConfig(max_iterations=5, token_limit=4000, quality_gate_enabled=True)
        state = build_initial_state(
            messages=[], config=config, available_workers=["w"],
        )
        assert state["max_iterations"] == 5
        assert state["token_limit"] == 4000
        assert state["quality_gate_enabled"] is True


class TestSupervisorNode:
    @pytest.mark.asyncio
    async def test_finish_returns_end(self):
        """TC-02: LLM이 FINISH 선택 → next_worker = '__end__'."""
        from src.application.agent_builder.supervisor_nodes import create_supervisor_node

        mock_llm = MagicMock()
        decision = MagicMock()
        decision.next = "FINISH"
        decision.reasoning = "done"
        mock_structured = AsyncMock(return_value=decision)
        mock_llm.with_structured_output.return_value.ainvoke = mock_structured

        fn = create_supervisor_node(
            llm=mock_llm, workers=_make_workers(),
            supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
        )
        result = await fn(_make_state())
        assert result["next_worker"] == "__end__"

    @pytest.mark.asyncio
    async def test_valid_worker_selected(self):
        """TC-03: LLM이 유효 워커 선택 → 해당 워커."""
        from src.application.agent_builder.supervisor_nodes import create_supervisor_node

        mock_llm = MagicMock()
        decision = MagicMock()
        decision.next = "worker_0"
        decision.reasoning = "search needed"
        mock_structured = AsyncMock(return_value=decision)
        mock_llm.with_structured_output.return_value.ainvoke = mock_structured

        fn = create_supervisor_node(
            llm=mock_llm, workers=_make_workers(),
            supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
        )
        result = await fn(_make_state())
        assert result["next_worker"] == "worker_0"

    @pytest.mark.asyncio
    async def test_invalid_worker_fallback_to_end(self):
        """TC-04: LLM이 잘못된 워커 선택 → __end__ 폴백."""
        from src.application.agent_builder.supervisor_nodes import create_supervisor_node

        mock_llm = MagicMock()
        decision = MagicMock()
        decision.next = "nonexistent_worker"
        decision.reasoning = "???"
        mock_structured = AsyncMock(return_value=decision)
        mock_llm.with_structured_output.return_value.ainvoke = mock_structured

        fn = create_supervisor_node(
            llm=mock_llm, workers=_make_workers(),
            supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
        )
        result = await fn(_make_state())
        assert result["next_worker"] == "__end__"

    @pytest.mark.asyncio
    async def test_max_iterations_reached(self):
        """TC-05: max_iterations 도달 → 즉시 __end__."""
        from src.application.agent_builder.supervisor_nodes import create_supervisor_node

        mock_llm = MagicMock()
        fn = create_supervisor_node(
            llm=mock_llm, workers=_make_workers(),
            supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
        )
        state = _make_state(iteration_count=10, max_iterations=10)
        result = await fn(state)
        assert result["next_worker"] == "__end__"
        mock_llm.with_structured_output.assert_not_called()

    @pytest.mark.asyncio
    async def test_token_limit_exceeded(self):
        """TC-06: token_limit 초과 → 즉시 __end__."""
        from src.application.agent_builder.supervisor_nodes import create_supervisor_node

        mock_llm = MagicMock()
        fn = create_supervisor_node(
            llm=mock_llm, workers=_make_workers(),
            supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
        )
        state = _make_state(token_usage=9000, token_limit=8000)
        result = await fn(state)
        assert result["next_worker"] == "__end__"

    @pytest.mark.asyncio
    async def test_force_worker_hook_skips_llm(self):
        """TC-11: force_worker 반환 시 LLM 호출 스킵."""
        from src.application.agent_builder.supervisor_nodes import create_supervisor_node

        class ForceHooks:
            def force_worker(self, state):
                return "worker_1"
            def skip_workers(self, state):
                return []

        mock_llm = MagicMock()
        fn = create_supervisor_node(
            llm=mock_llm, workers=_make_workers(),
            supervisor_prompt="test", hooks=ForceHooks(), logger=MagicMock(),
        )
        result = await fn(_make_state())
        assert result["next_worker"] == "worker_1"
        assert result["forced_worker"] == "worker_1"
        mock_llm.with_structured_output.assert_not_called()

    @pytest.mark.asyncio
    async def test_skipped_worker_fallback(self):
        """TC-12: skip_workers에 포함된 워커 선택 → __end__ 폴백."""
        from src.application.agent_builder.supervisor_nodes import create_supervisor_node

        class SkipHooks:
            def force_worker(self, state):
                return None
            def skip_workers(self, state):
                return ["worker_0"]

        mock_llm = MagicMock()
        decision = MagicMock()
        decision.next = "worker_0"
        decision.reasoning = "want search"
        mock_structured = AsyncMock(return_value=decision)
        mock_llm.with_structured_output.return_value.ainvoke = mock_structured

        fn = create_supervisor_node(
            llm=mock_llm, workers=_make_workers(),
            supervisor_prompt="test", hooks=SkipHooks(), logger=MagicMock(),
        )
        result = await fn(_make_state())
        assert result["next_worker"] == "__end__"

    @pytest.mark.asyncio
    async def test_llm_exception_fallback_to_end(self):
        """LLM 호출 실패 → __end__ 폴백."""
        from src.application.agent_builder.supervisor_nodes import create_supervisor_node

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            side_effect=RuntimeError("LLM failure")
        )

        fn = create_supervisor_node(
            llm=mock_llm, workers=_make_workers(),
            supervisor_prompt="test", hooks=DefaultHooks(), logger=MagicMock(),
        )
        result = await fn(_make_state())
        assert result["next_worker"] == "__end__"


class TestQualityGateNode:
    @pytest.mark.asyncio
    async def test_disabled_bypasses(self):
        """TC-07: 비활성 상태 → 바이패스, next_worker 초기화."""
        from src.application.agent_builder.supervisor_nodes import create_quality_gate_node

        fn = create_quality_gate_node(policy=QualityGatePolicy(), logger=MagicMock())
        result = await fn(_make_state(quality_gate_enabled=False))
        assert result["next_worker"] == ""
        assert result["quality_gate_result"] == "skipped"

    @pytest.mark.asyncio
    async def test_enabled_pass(self):
        """TC-08: 활성 + 통과 → next_worker 초기화."""
        from src.application.agent_builder.supervisor_nodes import create_quality_gate_node

        ai_msg = MagicMock()
        ai_msg.type = "ai"
        ai_msg.content = "검색 결과입니다. 최신 AI 뉴스를 정리했습니다."

        fn = create_quality_gate_node(policy=QualityGatePolicy(), logger=MagicMock())
        state = _make_state(
            quality_gate_enabled=True,
            last_worker_id="worker_0",
            messages=[ai_msg],
        )
        result = await fn(state)
        assert result["next_worker"] == ""
        assert result["quality_gate_result"] == "passed"

    @pytest.mark.asyncio
    async def test_enabled_fail_retry(self):
        """TC-09: 활성 + 실패 + 재시도 가능 → 워커 재호출."""
        from src.application.agent_builder.supervisor_nodes import create_quality_gate_node

        ai_msg = MagicMock()
        ai_msg.type = "ai"
        ai_msg.content = "모르겠습니다"

        fn = create_quality_gate_node(policy=QualityGatePolicy(), logger=MagicMock())
        state = _make_state(
            quality_gate_enabled=True,
            last_worker_id="worker_0",
            messages=[ai_msg],
            retry_counts={},
        )
        result = await fn(state)
        assert result["next_worker"] == "worker_0"
        assert result["retry_counts"]["worker_0"] == 1
        assert len(result["messages"]) == 1
        assert result["quality_gate_result"] == "failed"

    @pytest.mark.asyncio
    async def test_enabled_fail_max_retries_force_pass(self):
        """TC-10: 활성 + 실패 + max_retries 도달 → 강제 통과, next_worker 초기화."""
        from src.application.agent_builder.supervisor_nodes import create_quality_gate_node

        ai_msg = MagicMock()
        ai_msg.type = "ai"
        ai_msg.content = "모르겠습니다"

        fn = create_quality_gate_node(policy=QualityGatePolicy(), logger=MagicMock())
        state = _make_state(
            quality_gate_enabled=True,
            last_worker_id="worker_0",
            messages=[ai_msg],
            retry_counts={"worker_0": 2},
            max_retries_per_worker=2,
        )
        result = await fn(state)
        assert result["next_worker"] == ""
        assert result["quality_gate_result"] == "max_retries"

    @pytest.mark.asyncio
    async def test_no_ai_message_bypasses(self):
        """AI 메시지 없음 → 스킵, next_worker 초기화."""
        from src.application.agent_builder.supervisor_nodes import create_quality_gate_node

        fn = create_quality_gate_node(policy=QualityGatePolicy(), logger=MagicMock())
        state = _make_state(
            quality_gate_enabled=True,
            last_worker_id="worker_0",
            messages=[],
        )
        result = await fn(state)
        assert result["next_worker"] == ""
        assert result["quality_gate_result"] == "skipped"


    @pytest.mark.asyncio
    async def test_pass_resets_next_worker(self):
        """quality_gate 통과 후 route_after_quality가 supervisor로 라우팅."""
        from src.application.agent_builder.supervisor_nodes import (
            create_quality_gate_node,
            route_after_quality,
        )

        ai_msg = MagicMock()
        ai_msg.type = "ai"
        ai_msg.content = "검색 결과입니다. 최신 AI 뉴스를 정리했습니다."

        fn = create_quality_gate_node(policy=QualityGatePolicy(), logger=MagicMock())
        state = _make_state(
            quality_gate_enabled=True,
            last_worker_id="worker_0",
            next_worker="worker_0",
            messages=[ai_msg],
        )
        result = await fn(state)
        assert result["next_worker"] == ""

        updated_state = {**state, **result}
        assert route_after_quality(updated_state) == "supervisor"


class TestBuildInitialStateQualityGateResult:
    def test_has_quality_gate_result_field(self):
        from src.application.agent_builder.supervisor_nodes import build_initial_state

        config = SupervisorConfig()
        state = build_initial_state(
            messages=[], config=config, available_workers=[],
        )
        assert state["quality_gate_result"] == ""


class TestRoutingFunctions:
    def test_route_to_worker_returns_next_worker(self):
        from src.application.agent_builder.supervisor_nodes import route_to_worker

        state = _make_state(next_worker="worker_0")
        assert route_to_worker(state) == "worker_0"

    def test_route_to_worker_returns_end(self):
        from src.application.agent_builder.supervisor_nodes import route_to_worker

        state = _make_state(next_worker="__end__")
        assert route_to_worker(state) == "__end__"

    def test_route_after_quality_retry(self):
        from src.application.agent_builder.supervisor_nodes import route_after_quality

        state = _make_state(next_worker="worker_0")
        assert route_after_quality(state) == "worker_0"

    def test_route_after_quality_back_to_supervisor(self):
        from src.application.agent_builder.supervisor_nodes import route_after_quality

        state = _make_state(next_worker="")
        assert route_after_quality(state) == "supervisor"

    def test_route_after_quality_end_goes_to_supervisor(self):
        from src.application.agent_builder.supervisor_nodes import route_after_quality

        state = _make_state(next_worker="__end__")
        assert route_after_quality(state) == "supervisor"
