"""_with_denial_signal 데코레이터 + 생성자 kwarg 테스트 — 능력 부정 신호의 state 배선.

Design Ref: worker-capability-denial-guard §4.2 (D-04) / §8.4
Plan SC: FR-04, FR-05

능력 부정은 어떤 워커도 할 수 있으므로(실측은 react 워커) 노드 등록 루프
한 지점에서 **전 워커**를 덮는다. _wrap_step은 tracker 미배선 시 원본을
그대로 반환하므로 신호 배선에 쓸 수 없다 — 별도 데코레이터.
"""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from src.application.agent_builder.workflow_compiler import (
    WorkflowCompiler,
    _with_denial_signal,
)

PATTERNS = ("어떤 도구로도", "권한/범위 밖")

_DENIAL = (
    "미답변 문의 48건을 정리했습니다.\n" * 5
    + "문의 본문은 어떤 도구로도 조회할 수 없도록 제한되어 있습니다."
)
_OK = "미답변 문의 48건을 정리했습니다.\n" * 5


def _node_returning(content, **extra):
    async def node(state):
        out = {
            "messages": [AIMessage(content=content, name="w1")],
            "last_worker_id": "w1",
            "token_usage": 123,
        }
        out.update(extra)
        return out
    return node


class TestSignalInjection:

    @pytest.mark.asyncio
    async def test_denial_body_sets_reason(self):
        node = _with_denial_signal(_node_returning(_DENIAL), PATTERNS)
        out = await node({})
        assert out["last_worker_denial"] != ""

    @pytest.mark.asyncio
    async def test_normal_body_sets_empty_string(self):
        """이전 턴 신호가 잔류하지 않도록 정상일 때도 항상 덮어쓴다."""
        node = _with_denial_signal(_node_returning(_OK), PATTERNS)
        out = await node({})
        assert out["last_worker_denial"] == ""

    @pytest.mark.asyncio
    async def test_preserves_existing_keys(self):
        node = _with_denial_signal(_node_returning(_DENIAL), PATTERNS)
        out = await node({})
        assert out["last_worker_id"] == "w1"
        assert out["token_usage"] == 123
        assert len(out["messages"]) == 1

    @pytest.mark.asyncio
    async def test_coexists_with_empty_signal_key(self):
        """빈 결과 신호와 같은 out dict에 독립적으로 실린다 (§4.2)."""
        node = _with_denial_signal(
            _node_returning(_DENIAL, last_worker_empty="사유"), PATTERNS,
        )
        out = await node({})
        assert out["last_worker_empty"] == "사유"
        assert out["last_worker_denial"] != ""


class TestErrorTakesPrecedence:
    """§6.1 — 오류가 있으면 판정을 건너뛴다 (블록 2개 동시 렌더 방지)."""

    @pytest.mark.asyncio
    async def test_skips_detection_when_worker_error_present(self):
        node = _with_denial_signal(
            _node_returning(_DENIAL, last_worker_error="도구 오류"), PATTERNS,
        )
        out = await node({})
        assert out["last_worker_denial"] == ""
        assert out["last_worker_error"] == "도구 오류"

    @pytest.mark.asyncio
    async def test_detects_when_error_is_blank(self):
        node = _with_denial_signal(
            _node_returning(_DENIAL, last_worker_error=""), PATTERNS,
        )
        out = await node({})
        assert out["last_worker_denial"] != ""


class TestDefensiveBehavior:

    @pytest.mark.asyncio
    async def test_no_messages_key(self):
        async def node(state):
            return {"last_worker_id": "w1"}
        out = await _with_denial_signal(node, PATTERNS)({})
        assert out["last_worker_denial"] == ""

    @pytest.mark.asyncio
    async def test_non_string_content(self):
        node = _with_denial_signal(
            _node_returning([{"type": "text", "text": _DENIAL}]), PATTERNS,
        )
        out = await node({})
        assert out["last_worker_denial"] == ""

    @pytest.mark.asyncio
    async def test_non_dict_return_passes_through(self):
        async def node(state):
            return "raw"
        assert await _with_denial_signal(node, PATTERNS)({}) == "raw"

    @pytest.mark.asyncio
    async def test_none_patterns_safe(self):
        """미주입 경로(테스트 픽스처·백그라운드)에서 항상 '' — 무회귀."""
        node = _with_denial_signal(_node_returning(_DENIAL), None)
        out = await node({})
        assert out["last_worker_denial"] == ""


class TestCompilerKwarg:
    """FR-03: config는 main.py가 정규화해 kwarg로 주입한다."""

    def _compiler(self, **kw):
        return WorkflowCompiler(
            tool_factory=MagicMock(), llm_factory=MagicMock(), logger=MagicMock(),
            **kw,
        )

    def test_default_is_empty_tuple(self):
        assert self._compiler()._capability_denial_patterns == ()

    def test_kwarg_is_stored_as_tuple(self):
        c = self._compiler(capability_denial_patterns=["어떤 도구로도"])
        assert c._capability_denial_patterns == ("어떤 도구로도",)


class TestWorkerInputScopeReminder:
    """Act-1 Gap-02: 규범(system)만으로는 워커가 task 밖 능력 질문에 답했다
    (실런 2회 모두 되물음 발동). [현재 작업] 지시 꼬리에 범위 리마인더를 덧붙여
    가장 가까운 위치에서 한 번 더 제한한다. D-08: 절대 프레이밍 금지.
    """

    def test_task_message_carries_scope_reminder(self):
        from langchain_core.messages import HumanMessage
        from src.application.agent_builder.workflow_compiler import _build_worker_input
        msgs = _build_worker_input({
            "messages": [HumanMessage(content="목록 알려줘. 본문 읽을 수 있나요?")],
            "worker_task": "customer 게시판 미답변 목록 조회",
        })
        task_msg = next(m for m in msgs if "[현재 작업]" in getattr(m, "content", ""))
        assert "customer 게시판 미답변 목록 조회" in task_msg.content
        assert "능력" in task_msg.content and "답하지" in task_msg.content
        assert "라고만" not in task_msg.content

    def test_no_task_no_reminder(self):
        """task가 비면 기존 폴백 지시 그대로 — 무회귀."""
        from langchain_core.messages import HumanMessage
        from src.application.agent_builder.workflow_compiler import _build_worker_input
        msgs = _build_worker_input({
            "messages": [HumanMessage(content="q")], "worker_task": "",
        })
        assert not any("[현재 작업]" in getattr(m, "content", "") for m in msgs)
