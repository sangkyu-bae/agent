"""route_to_worker_or_final 되물음 분기 테스트.

Design Ref: supervisor-early-finish-fix §4.4 (D-05) / §8.4
Plan SC: FR-06, FR-07

빈 결과가 미해소인 상태의 첫 FINISH를 1회 되돌린다. 특정 워커로 강제
라우팅하지 않고 재결정 기회만 준다 — 그래프 계약 ③(결정적 신호 vs LLM 판단).
"""
from src.application.agent_builder.supervisor_nodes import route_to_worker_or_final


def _state(**overrides) -> dict:
    state = {
        "next_worker": "__end__",
        "last_worker_id": "collector",
        "limit_reached": False,
        "finish_challenge_pending": False,
    }
    state.update(overrides)
    return state


class TestChallengeBranch:

    def test_pending_finish_is_returned_to_supervisor(self):
        assert route_to_worker_or_final(
            _state(finish_challenge_pending=True)
        ) == "supervisor"

    def test_finish_passes_when_not_pending(self):
        assert route_to_worker_or_final(_state()) == "final_answer"

    def test_second_finish_passes_after_challenge_consumed(self):
        """되물음 후 supervisor가 pending을 소진하면 통과한다 — 1회 상한."""
        assert route_to_worker_or_final(
            _state(finish_challenge_pending=False)
        ) == "final_answer"


class TestGuardPrecedence:
    """§6.1 D-09 — 한도 가드가 되물음보다 우선. 종료를 막지 않는다."""

    def test_limit_reached_beats_pending(self):
        assert route_to_worker_or_final(
            _state(finish_challenge_pending=True, limit_reached=True)
        ) == "final_answer"

    def test_limit_reached_without_worker_still_reaches_final(self):
        assert route_to_worker_or_final(
            _state(last_worker_id="", limit_reached=True,
                   finish_challenge_pending=True)
        ) == "final_answer"


class TestExistingBehaviorPreserved:

    def test_worker_id_passes_through(self):
        assert route_to_worker_or_final(
            _state(next_worker="collector", finish_challenge_pending=True)
        ) == "collector"

    def test_pure_conversation_ends_directly(self):
        """워커 미실행(단순 대화)은 END 직행 — 기존 동작 보존."""
        assert route_to_worker_or_final(
            _state(last_worker_id="", limit_reached=False)
        ) == "__end__"

    def test_missing_keys_are_safe(self):
        """기존 체크포인트(신규 키 부재) 하위호환."""
        assert route_to_worker_or_final(
            {"next_worker": "__end__", "last_worker_id": "w"}
        ) == "final_answer"
