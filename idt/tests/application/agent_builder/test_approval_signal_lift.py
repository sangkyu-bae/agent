"""승인 신호 리프트 + 라우팅 단위 테스트.

Design Ref: §2.1 ②③ — 미들웨어가 남긴 마커를 워커 래퍼가 SupervisorState 로
올리고, 라우팅이 즉시 __end__ 로 보낸다. `ToolErrorPolicy.summarize` /
`limit_reached` 와 같은 계열이다.
"""
from langchain_core.messages import AIMessage, ToolMessage

from src.application.agent_builder.supervisor_nodes import route_to_worker_or_final
from src.domain.approval.policies import ApprovalSignalPolicy


def _state(**over) -> dict:
    base = {
        "next_worker": "__end__",
        "last_worker_id": "w1",
        "limit_reached": False,
        "finish_challenge_pending": False,
        "approval_pending": {},
    }
    base.update(over)
    return base


def _pending() -> dict:
    return {
        "tool_id": "email_send",
        "tool_args": {"to": "a@b.c"},
        "draft": "본문",
        "tool_call_id": "tc1",
        "worker_id": "w1",
    }


class TestRouting:
    def test_승인대기면_final_answer를_거치지_않고_종료(self):
        """초안은 사람이 볼 것이지 LLM이 요약할 것이 아니다.

        final_answer 를 태우면 LLM 호출이 한 번 더 들고, 사용자에게는
        '완료했습니다' 같은 오해 소지 문구가 나갈 수 있다.
        """
        assert route_to_worker_or_final(_state(approval_pending=_pending())) == "__end__"

    def test_승인대기는_되물음보다_우선한다(self):
        """게이트가 걸린 런은 더 돌 이유가 없다."""
        state = _state(approval_pending=_pending(), finish_challenge_pending=True)
        assert route_to_worker_or_final(state) == "__end__"

    def test_승인대기는_한도도달보다_우선한다(self):
        state = _state(approval_pending=_pending(), limit_reached=True)
        assert route_to_worker_or_final(state) == "__end__"

    def test_승인대기가_없으면_기존_동작(self):
        """무회귀 — 워커 이력이 있으면 final_answer 경유."""
        assert route_to_worker_or_final(_state()) == "final_answer"

    def test_빈_dict는_승인대기가_아니다(self):
        assert route_to_worker_or_final(_state(approval_pending={})) == "final_answer"

    def test_키_부재_상태도_기존_동작(self):
        """하위호환 — 옛 state 에는 approval_pending 키가 없다."""
        state = _state()
        del state["approval_pending"]
        assert route_to_worker_or_final(state) == "final_answer"

    def test_워커로_라우팅_중이면_승인대기가_있어도_그대로(self):
        """next_worker 가 실제 워커면 게이트 판정 이전 단계다."""
        state = _state(next_worker="w2", approval_pending=_pending())
        assert route_to_worker_or_final(state) == "w2"


class TestSignalLift:
    """_wrap_worker 가 트레이스에서 신호를 건져 state 로 올린다."""

    def test_마커_트레이스에서_pending을_만든다(self):
        from src.application.agent_builder.workflow_compiler import (
            _extract_approval_pending,
        )

        marker = ApprovalSignalPolicy.render(
            tool_id="email_send", tool_args={"to": "a@b.c"},
            draft="본문", tool_call_id="tc1",
        )
        pending = _extract_approval_pending([ToolMessage(marker, tool_call_id="tc1")], "w1")
        assert pending["tool_id"] == "email_send"
        assert pending["worker_id"] == "w1"
        assert pending["tool_call_id"] == "tc1"
        assert pending["draft"] == "본문"

    def test_마커가_없으면_빈_dict(self):
        """빈 dict 가 '없음' — last_worker_error 의 빈 문자열과 같은 계열."""
        from src.application.agent_builder.workflow_compiler import (
            _extract_approval_pending,
        )

        result = _extract_approval_pending([AIMessage(content="평범한 답변")], "w1")
        assert result == {}

    def test_빈_트레이스도_빈_dict(self):
        from src.application.agent_builder.workflow_compiler import (
            _extract_approval_pending,
        )

        assert _extract_approval_pending([], "w1") == {}

    def test_워커id는_인자에서_온다(self):
        """마커에도 담기지만 래퍼가 아는 값이 권위 있다."""
        from src.application.agent_builder.workflow_compiler import (
            _extract_approval_pending,
        )

        marker = ApprovalSignalPolicy.render(
            tool_id="t", tool_args={}, draft="", tool_call_id="tc"
        )
        pending = _extract_approval_pending(
            [ToolMessage(marker, tool_call_id="tc")], "실제워커"
        )
        assert pending["worker_id"] == "실제워커"


class TestStateSchema:
    def test_approval_pending_필드가_선언되어_있다(self):
        from src.application.agent_builder.supervisor_state import SupervisorState

        assert "approval_pending" in SupervisorState.__annotations__
