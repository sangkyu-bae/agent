"""supervisor 빈 결과 블록 + 되물음 기회 플래그 테스트.

Design Ref: supervisor-early-finish-fix §4.3 (D-03) / §2.2 (D-05)
Plan SC: FR-05, FR-06, FR-07, FR-08

'수집은 성공했는데 데이터가 없다'를 supervisor에 알리고, 미해소 상태의
첫 FINISH를 되돌릴 기회를 1회 부여한다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import (
    _render_empty_result_block,
    create_supervisor_node,
)
from src.domain.agent_builder.schemas import WorkerDefinition

_REASON = "수집 산출에 유효 데이터 영역이 없음"


def _make_state(messages: list, **overrides) -> dict:
    state = {
        "messages": messages,
        "iteration_count": 0,
        "max_iterations": 10,
        "token_usage": 0,
        "token_limit": 8000,
        "next_worker": "",
        "last_worker_id": "collector",
        "available_workers": ["collector"],
        "quality_gate_enabled": False,
        "retry_counts": {},
        "max_retries_per_worker": 2,
        "forced_worker": "",
        "skipped_workers": [],
        "quality_gate_result": "",
        "attachments": [],
        "viz_decision": "",
    }
    state.update(overrides)
    return state


def _llm_returning(next_: str):
    mock_llm = MagicMock()
    decision = MagicMock()
    decision.next = next_
    decision.answer = ""
    decision.reasoning = "r"
    decision.task = ""
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=decision
    )
    return mock_llm


def _node(mock_llm):
    return create_supervisor_node(
        llm=mock_llm,
        workers=[WorkerDefinition("t", "collector", "수집", 0)],
        supervisor_prompt="지침",
        hooks=DefaultHooks(),
        logger=MagicMock(),
    )


def _sent_system(mock_llm) -> str:
    sent = mock_llm.with_structured_output.return_value.ainvoke.call_args[0][0]
    return sent[0]["content"]


class TestRenderEmptyResultBlock:

    def test_returns_empty_when_no_signal(self):
        assert _render_empty_result_block(_make_state([])) == ""
        assert _render_empty_result_block(_make_state([], last_worker_empty="")) == ""

    def test_renders_block_with_reason(self):
        block = _render_empty_result_block(
            _make_state([], last_worker_empty=_REASON)
        )
        assert "[수집 결과 확인 필요]" in block
        assert _REASON in block

    def test_block_does_not_enumerate_workers_or_tools(self):
        """그래프 계약 ② — 목록 프레이밍 금지. 할 수 있는 것을 나열하지 않는다."""
        block = _render_empty_result_block(
            _make_state([], last_worker_empty=_REASON)
        )
        for forbidden in ("browser_click", "browser_open", "scrape_url", "collector"):
            assert forbidden not in block

    def test_block_within_length_budget(self):
        """Plan NFR — 발동 시에만 렌더, 400자 이내."""
        block = _render_empty_result_block(
            _make_state([], last_worker_empty=_REASON)
        )
        assert len(block) <= 400

    def test_block_is_conditional_not_imperative(self):
        """오탐 시 LLM이 곧바로 FINISH를 재선택할 여지를 남긴다."""
        block = _render_empty_result_block(
            _make_state([], last_worker_empty=_REASON)
        )
        assert "남아 있다면" in block


class TestSupervisorInjectsBlock:

    @pytest.mark.asyncio
    async def test_prompt_includes_block_when_signal_present(self):
        mock_llm = _llm_returning("FINISH")
        state = _make_state(
            [HumanMessage(content="금리 표"), AIMessage(content="...", name="collector")],
            last_worker_empty=_REASON,
        )
        await _node(mock_llm)(state)
        assert "[수집 결과 확인 필요]" in _sent_system(mock_llm)

    @pytest.mark.asyncio
    async def test_prompt_byte_identical_when_no_signal(self):
        """Plan SC: FR-08 — 신호가 없으면 기존과 바이트 동일."""
        messages = [HumanMessage(content="금리 표")]

        mock_a = _llm_returning("FINISH")
        await _node(mock_a)(_make_state(messages))
        baseline = _sent_system(mock_a)

        mock_b = _llm_returning("FINISH")
        await _node(mock_b)(_make_state(messages, last_worker_empty=""))
        assert _sent_system(mock_b) == baseline
        assert "[수집 결과 확인 필요]" not in baseline

    @pytest.mark.asyncio
    async def test_error_block_takes_precedence(self):
        """§6.1 — 오류와 빈 결과 동시 성립 시 오류 블록만."""
        mock_llm = _llm_returning("FINISH")
        state = _make_state(
            [HumanMessage(content="q")],
            last_worker_empty=_REASON,
            last_worker_error="Error executing tool",
        )
        await _node(mock_llm)(state)
        system = _sent_system(mock_llm)
        assert "[직전 수집 실패]" in system
        assert "[수집 결과 확인 필요]" not in system


class TestFinishChallengeLifecycle:
    """§2.2 — 카운터 없이 플래그 수명주기만으로 1회 상한을 보장한다."""

    @pytest.mark.asyncio
    async def test_sets_pending_and_resets_signal(self):
        mock_llm = _llm_returning("FINISH")
        out = await _node(mock_llm)(
            _make_state([HumanMessage(content="q")], last_worker_empty=_REASON)
        )
        assert out["finish_challenge_pending"] is True
        assert out["last_worker_empty"] == ""

    @pytest.mark.asyncio
    async def test_consumes_pending_on_reentry(self):
        """2회차 진입 — 블록 없이 기회만 소진한다."""
        mock_llm = _llm_returning("FINISH")
        out = await _node(mock_llm)(
            _make_state(
                [HumanMessage(content="q")],
                last_worker_empty="",
                finish_challenge_pending=True,
            )
        )
        assert out["finish_challenge_pending"] is False
        assert "[수집 결과 확인 필요]" not in _sent_system(mock_llm)

    @pytest.mark.asyncio
    async def test_no_pending_when_no_signal(self):
        mock_llm = _llm_returning("FINISH")
        out = await _node(mock_llm)(_make_state([HumanMessage(content="q")]))
        assert not out.get("finish_challenge_pending")

    @pytest.mark.asyncio
    async def test_token_limit_guard_consumes_pending(self):
        """회귀: token_limit 가드는 limit_reached를 세우지 않는다(D5).

        pending이 남으면 route가 supervisor로 되돌리고 같은 가드가 다시 걸려
        무한 루프가 된다. iteration_count도 이 경로에선 증가하지 않아
        max_iterations 가드가 막아주지 못한다.
        """
        out = await _node(_llm_returning("FINISH"))(
            _make_state(
                [HumanMessage(content="q")],
                token_usage=99999,
                token_limit=100,
                finish_challenge_pending=True,
            )
        )
        assert out["next_worker"] == "__end__"
        assert out["finish_challenge_pending"] is False

    @pytest.mark.asyncio
    async def test_max_iterations_guard_consumes_pending(self):
        """한도 가드도 플래그를 명시적으로 확정한다 — limit_reached 암묵 의존 제거."""
        out = await _node(_llm_returning("FINISH"))(
            _make_state(
                [HumanMessage(content="q")],
                iteration_count=99,
                max_iterations=10,
                finish_challenge_pending=True,
            )
        )
        assert out["limit_reached"] is True
        assert out["finish_challenge_pending"] is False

    @pytest.mark.asyncio
    async def test_llm_failure_consumes_pending(self):
        """결정 실패는 되물음 대상이 아니다 — 무한 루프 방지.

        회귀: 실패 fallback이 플래그를 소진하지 않으면 route가 계속
        supervisor로 돌려보내 GraphRecursionError가 난다 (실측).
        """
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        out = await _node(mock_llm)(
            _make_state([HumanMessage(content="q")], finish_challenge_pending=True)
        )
        assert out["next_worker"] == "__end__"
        assert out["finish_challenge_pending"] is False
        assert out["last_worker_empty"] == ""

    @pytest.mark.asyncio
    async def test_direct_answer_path_consumes_pending(self):
        """워커 미실행 + draft answer 조기 return도 플래그를 소진한다."""
        mock_llm = _llm_returning("FINISH")
        mock_llm.with_structured_output.return_value.ainvoke.return_value.answer = (
            "직접 답변"
        )
        out = await _node(mock_llm)(
            _make_state([HumanMessage(content="q")], last_worker_id="")
        )
        assert out["finish_challenge_pending"] is False
        assert out["last_worker_empty"] == ""

    @pytest.mark.asyncio
    async def test_pending_set_regardless_of_decision(self):
        """pending은 블록 렌더 여부로만 정해진다.

        워커를 고른 턴에도 세워지지만, route_to_worker_or_final이 __end__일
        때만 소비하므로 무해하다. 다음 턴에 블록이 비면 False로 소진된다.
        """
        mock_llm = _llm_returning("collector")
        out = await _node(mock_llm)(
            _make_state([HumanMessage(content="q")], last_worker_empty=_REASON)
        )
        assert out["last_worker_empty"] == ""
        assert out["finish_challenge_pending"] is True
