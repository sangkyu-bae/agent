"""supervisor 능력 부정 블록 + 배타 + 되물음 기회 합산 테스트.

Design Ref: worker-capability-denial-guard §4.3 (D-05) / §4.4 (D-06) / §4.5 (D-07)
Plan SC: FR-06, FR-07, FR-08, FR-09, FR-11

'워커가 자기 도구 범위를 근거로 불가를 선언했다'를 supervisor에 알리고,
미해소 상태의 첫 FINISH를 되돌릴 기회를 빈 결과와 합산 1회 부여한다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import (
    _render_capability_denial_block,
    _select_guidance_block,
    build_initial_state,
    create_supervisor_node,
)
from src.application.agent_builder.supervisor_state import SupervisorState
from src.domain.agent_builder.schemas import WorkerDefinition

_REASON = "워커가 에이전트 전체 능력을 부정함: '어떤 도구로도'"


def _make_state(messages: list, **overrides) -> dict:
    state = {
        "messages": messages,
        "iteration_count": 0,
        "max_iterations": 10,
        "token_usage": 0,
        "token_limit": 8000,
        "next_worker": "",
        "last_worker_id": "lister",
        "available_workers": ["lister", "reader"],
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


def _llm_returning(next_: str, answer: str = ""):
    mock_llm = MagicMock()
    decision = MagicMock()
    decision.next = next_
    decision.answer = answer
    decision.reasoning = "r"
    decision.task = ""
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=decision
    )
    return mock_llm


def _node(mock_llm, logger=None):
    return create_supervisor_node(
        llm=mock_llm,
        workers=[
            WorkerDefinition("t1", "lister", "목록", 0),
            WorkerDefinition("t2", "reader", "본문", 1),
        ],
        supervisor_prompt="지침",
        hooks=DefaultHooks(),
        logger=logger or MagicMock(),
    )


def _sent_system(mock_llm) -> str:
    sent = mock_llm.with_structured_output.return_value.ainvoke.call_args[0][0]
    return sent[0]["content"]


_MSGS = [HumanMessage(content="본문 읽을 수 있나요?"), AIMessage(content="불가", name="lister")]


class TestStateSchema:

    def test_state_declares_denial_channel(self):
        assert "last_worker_denial" in SupervisorState.__annotations__

    def test_initial_state_has_empty_denial(self):
        from src.application.agent_builder.supervisor_nodes import SupervisorConfig
        state = build_initial_state(
            messages=[{"role": "user", "content": "q"}],
            config=SupervisorConfig(),
            available_workers=[],
        )
        assert state["last_worker_denial"] == ""


class TestRenderCapabilityDenialBlock:

    def test_returns_empty_when_no_signal(self):
        assert _render_capability_denial_block(_make_state([])) == ""
        assert _render_capability_denial_block(
            _make_state([], last_worker_denial="")
        ) == ""

    def test_renders_block_with_reason(self):
        block = _render_capability_denial_block(
            _make_state([], last_worker_denial=_REASON)
        )
        assert "[워커 능력 부정 감지]" in block
        assert _REASON in block

    def test_block_points_to_worker_list_as_truth(self):
        block = _render_capability_denial_block(
            _make_state([], last_worker_denial=_REASON)
        )
        assert "사용 가능한 워커" in block
        assert "근거가 아닙니다" in block

    def test_block_tells_how_to_answer_capability_question(self):
        """FR-10 1차 기대 동작 — 가능함과 필요한 입력을 answer에 적는다."""
        block = _render_capability_denial_block(
            _make_state([], last_worker_denial=_REASON)
        )
        assert "answer" in block
        assert "필요한 입력" in block

    def test_block_does_not_enumerate_workers_or_tools(self):
        """그래프 계약 ② — 워커·도구 이름을 나열하지 않는다."""
        block = _render_capability_denial_block(
            _make_state([], last_worker_denial=_REASON)
        )
        for forbidden in ("get_inquiry", "list_inquiries", "lister", "reader"):
            assert forbidden not in block

    def test_block_within_length_budget(self):
        block = _render_capability_denial_block(
            _make_state([], last_worker_denial="x")
        )
        assert len(block) <= 400


class TestSelectGuidanceBlock:
    """D-06: 한 결정에 안내 블록은 최대 1개. 오류 > 빈 결과 > 능력 부정."""

    def test_none_when_no_signals(self):
        assert _select_guidance_block(_make_state([]), "") == ("", "")

    def test_denial_only(self):
        block, kind = _select_guidance_block(
            _make_state([], last_worker_denial=_REASON), ""
        )
        assert kind == "denial"
        assert "[워커 능력 부정 감지]" in block

    def test_empty_beats_denial(self):
        block, kind = _select_guidance_block(
            _make_state([], last_worker_denial=_REASON, last_worker_empty="빈"), ""
        )
        assert kind == "empty"
        assert "[워커 능력 부정 감지]" not in block

    def test_error_beats_both(self):
        block, kind = _select_guidance_block(
            _make_state(
                [], last_worker_denial=_REASON, last_worker_empty="빈",
                last_worker_error="오류",
            ),
            "",
        )
        assert kind == "error"
        assert "[워커 능력 부정 감지]" not in block
        assert "[수집 결과 확인 필요]" not in block


class TestSupervisorInjectsBlock:

    @pytest.mark.asyncio
    async def test_prompt_includes_block_when_signal_present(self):
        llm = _llm_returning("FINISH")
        await _node(llm)(_make_state(_MSGS, last_worker_denial=_REASON))
        assert "[워커 능력 부정 감지]" in _sent_system(llm)

    @pytest.mark.asyncio
    async def test_prompt_byte_identical_when_no_signal(self):
        """FR-09 — 신호 없으면 기존과 바이트 동일 (키 부재·빈 문자열 모두)."""
        llm_a = _llm_returning("FINISH")
        await _node(llm_a)(_make_state(_MSGS))
        llm_b = _llm_returning("FINISH")
        await _node(llm_b)(_make_state(_MSGS, last_worker_denial=""))
        assert _sent_system(llm_a) == _sent_system(llm_b)
        assert "[워커 능력 부정 감지]" not in _sent_system(llm_a)

    @pytest.mark.asyncio
    async def test_empty_block_takes_precedence(self):
        llm = _llm_returning("FINISH")
        await _node(llm)(
            _make_state(_MSGS, last_worker_denial=_REASON, last_worker_empty="빈")
        )
        sent = _sent_system(llm)
        assert "[수집 결과 확인 필요]" in sent
        assert "[워커 능력 부정 감지]" not in sent

    @pytest.mark.asyncio
    async def test_error_block_takes_precedence(self):
        llm = _llm_returning("FINISH")
        await _node(llm)(
            _make_state(_MSGS, last_worker_denial=_REASON, last_worker_error="오류")
        )
        assert "[워커 능력 부정 감지]" not in _sent_system(llm)


class TestFinishChallengeLifecycle:
    """D-07: 모든 return 경로가 신호 리셋과 pending을 명시적으로 확정한다."""

    @pytest.mark.asyncio
    async def test_sets_pending_and_resets_signal(self):
        out = await _node(_llm_returning("FINISH"))(
            _make_state(_MSGS, last_worker_denial=_REASON)
        )
        assert out["finish_challenge_pending"] is True
        assert out["last_worker_denial"] == ""

    @pytest.mark.asyncio
    async def test_pending_also_when_routing_to_worker(self):
        out = await _node(_llm_returning("reader"))(
            _make_state(_MSGS, last_worker_denial=_REASON)
        )
        assert out["finish_challenge_pending"] is True
        assert out["next_worker"] == "reader"

    @pytest.mark.asyncio
    async def test_error_block_does_not_raise_pending(self):
        out = await _node(_llm_returning("FINISH"))(
            _make_state(_MSGS, last_worker_denial=_REASON, last_worker_error="오류")
        )
        assert out["finish_challenge_pending"] is False
        assert out["last_worker_denial"] == ""

    @pytest.mark.asyncio
    async def test_consumes_pending_on_reentry(self):
        out = await _node(_llm_returning("FINISH"))(
            _make_state(_MSGS, finish_challenge_pending=True)
        )
        assert out["finish_challenge_pending"] is False

    @pytest.mark.asyncio
    async def test_max_iterations_guard_resets(self):
        out = await _node(_llm_returning("FINISH"))(
            _make_state(_MSGS, iteration_count=10, last_worker_denial=_REASON)
        )
        assert out["last_worker_denial"] == ""
        assert out["finish_challenge_pending"] is False

    @pytest.mark.asyncio
    async def test_token_limit_guard_resets(self):
        out = await _node(_llm_returning("FINISH"))(
            _make_state(_MSGS, token_usage=9000, last_worker_denial=_REASON)
        )
        assert out["last_worker_denial"] == ""
        assert out["finish_challenge_pending"] is False

    @pytest.mark.asyncio
    async def test_forced_routing_resets(self):
        hooks = MagicMock()
        hooks.force_worker.return_value = "reader"
        node = create_supervisor_node(
            llm=_llm_returning("FINISH"),
            workers=[WorkerDefinition("t2", "reader", "본문", 0)],
            supervisor_prompt="지침", hooks=hooks, logger=MagicMock(),
        )
        out = await node(_make_state(_MSGS, last_worker_denial=_REASON))
        assert out["last_worker_denial"] == ""
        assert out["finish_challenge_pending"] is False

    @pytest.mark.asyncio
    async def test_llm_failure_resets(self):
        llm = MagicMock()
        llm.with_structured_output.return_value.ainvoke = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        out = await _node(llm)(_make_state(_MSGS, last_worker_denial=_REASON))
        assert out["next_worker"] == "__end__"
        assert out["last_worker_denial"] == ""
        assert out["finish_challenge_pending"] is False

    @pytest.mark.asyncio
    async def test_direct_answer_path_resets(self):
        out = await _node(_llm_returning("FINISH", answer="바로 답"))(
            _make_state(
                [HumanMessage(content="q")], last_worker_id="",
                last_worker_denial=_REASON,
            )
        )
        assert out["last_worker_denial"] == ""
        assert out["finish_challenge_pending"] is False


class TestChallengeLogging:
    """FR-11: 되물음 기회 발동을 구조화 로그로 남긴다 (사유 종류 포함)."""

    @pytest.mark.asyncio
    async def test_logs_reason_kind_when_denial_block_rendered(self):
        logger = MagicMock()
        await _node(_llm_returning("FINISH"), logger)(
            _make_state(_MSGS, last_worker_denial=_REASON)
        )
        kinds = [
            c.kwargs.get("reason_kind") for c in logger.info.call_args_list
        ]
        assert "denial" in kinds

    @pytest.mark.asyncio
    async def test_no_challenge_log_when_no_signal(self):
        logger = MagicMock()
        await _node(_llm_returning("FINISH"), logger)(_make_state(_MSGS))
        kinds = [
            c.kwargs.get("reason_kind") for c in logger.info.call_args_list
        ]
        assert "denial" not in kinds and "empty" not in kinds


class TestBlockCoversCrossDescriptionConfusion:
    """module-6 실런(런 a217f45e) 정정: supervisor가 '워커 목록'을 봤는데도
    다른 워커(list_inquiries)의 description에 적힌 "어떤 도구로도 볼 수 없다"를
    에이전트 전체 제한으로 읽었다. 블록이 '다른 워커 설명의 제한은 그 워커에만
    적용'임을 명시해야 한다.
    """

    def test_block_scopes_other_worker_description_limits(self):
        block = _render_capability_denial_block(
            _make_state([], last_worker_denial=_REASON)
        )
        assert "그 워커에만" in block

    def test_block_still_within_length_budget(self):
        block = _render_capability_denial_block(
            _make_state([], last_worker_denial=_REASON)
        )
        assert len(block) <= 400


class TestChallengeReentryReminder:
    """Act-1 Gap-03: 되물음 재결정(2회차)에 판단 근거를 유지한다.

    실런 295d2915: 1회차 재판단은 옳았으나 answer는 DQ1로 폐기되고 reasoning은
    대화에 남지 않아, 블록 없는 2회차가 원래 믿음으로 되돌아갔다. 재진입 시
    사유 종류만 담은 짧은 리마인더를 싣는다 — 신호는 이미 리셋돼 있으므로
    pending은 False로만 가며 1회 상한은 그대로다.
    """

    @pytest.mark.asyncio
    async def test_block_render_records_challenge_kind(self):
        out = await _node(_llm_returning("FINISH"))(
            _make_state(_MSGS, last_worker_denial=_REASON)
        )
        assert out["finish_challenge_kind"] == "denial"

    @pytest.mark.asyncio
    async def test_reentry_prompt_has_reminder_and_consumes(self):
        llm = _llm_returning("FINISH")
        out = await _node(llm)(
            _make_state(_MSGS, finish_challenge_pending=True, finish_challenge_kind="denial")
        )
        sent = _sent_system(llm)
        assert "[되물음 재결정]" in sent
        assert "사용 가능한 워커" in sent
        assert "[워커 능력 부정 감지]" not in sent
        assert out["finish_challenge_pending"] is False
        assert out["finish_challenge_kind"] == ""

    @pytest.mark.asyncio
    async def test_reentry_reminder_for_empty_kind(self):
        llm = _llm_returning("FINISH")
        await _node(llm)(
            _make_state(_MSGS, finish_challenge_pending=True, finish_challenge_kind="empty")
        )
        sent = _sent_system(llm)
        assert "[되물음 재결정]" in sent
        assert "유효한 데이터" in sent

    @pytest.mark.asyncio
    async def test_no_reminder_when_not_pending(self):
        llm = _llm_returning("FINISH")
        await _node(llm)(_make_state(_MSGS, finish_challenge_kind="denial"))
        assert "[되물음 재결정]" not in _sent_system(llm)

    @pytest.mark.asyncio
    async def test_fresh_signal_beats_reminder(self):
        """재진입인데 새 워커 신호가 있으면 정식 블록이 우선한다."""
        llm = _llm_returning("FINISH")
        await _node(llm)(
            _make_state(
                _MSGS, finish_challenge_pending=True, finish_challenge_kind="denial",
                last_worker_denial=_REASON,
            )
        )
        sent = _sent_system(llm)
        assert "[워커 능력 부정 감지]" in sent
        assert "[되물음 재결정]" not in sent

    @pytest.mark.asyncio
    async def test_reentry_logs_consumed(self):
        logger = MagicMock()
        await _node(_llm_returning("FINISH"), logger)(
            _make_state(_MSGS, finish_challenge_pending=True, finish_challenge_kind="denial")
        )
        events = [c.args[0] for c in logger.info.call_args_list]
        assert "finish challenge consumed" in events

    @pytest.mark.asyncio
    async def test_arm_log_event_name(self):
        logger = MagicMock()
        await _node(_llm_returning("FINISH"), logger)(
            _make_state(_MSGS, last_worker_denial=_REASON)
        )
        events = [c.args[0] for c in logger.info.call_args_list]
        assert "finish challenge armed" in events


class TestBlockLengthWorstCase:
    """Act-1 Gap-07: 사유 요약 상한(120자)에서도 블록 400자 이내."""

    def test_block_within_budget_with_max_reason(self):
        reason = "가" * 120
        block = _render_capability_denial_block(
            _make_state([], last_worker_denial=reason)
        )
        assert len(block) <= 400
