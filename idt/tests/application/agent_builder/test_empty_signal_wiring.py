"""_with_empty_signal 데코레이터 테스트 — 빈 결과 신호의 state 배선.

Design Ref: supervisor-early-finish-fix §4.2 (D-06)
Plan SC: FR-04

4개 워커 팩토리(react / collect / search / deep-search)를 노드 등록 루프
한 지점에서 덮는다. _wrap_step은 tracker 미배선 시 원본을 그대로 반환하므로
(workflow_compiler.py:749-750) 신호 배선에 쓸 수 없다 — 별도 데코레이터.
"""
import pytest
from langchain_core.messages import AIMessage

from src.application.agent_builder.workflow_compiler import _with_empty_signal

PATTERNS = ("등록된 데이터가 없습니다",)

_LONG_EMPTY = "메뉴 상품공시 경영공시\n" * 40 + "상세 등록된 데이터가 없습니다."
_LONG_OK = "저축은행A 12개월 3.50%\n" * 40


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
    async def test_empty_body_sets_reason(self):
        node = _with_empty_signal(_node_returning(_LONG_EMPTY), PATTERNS)
        out = await node({})
        assert out["last_worker_empty"] != ""

    @pytest.mark.asyncio
    async def test_normal_body_sets_empty_string(self):
        """이전 턴 신호가 잔류하지 않도록 정상일 때도 항상 덮어쓴다."""
        node = _with_empty_signal(_node_returning(_LONG_OK), PATTERNS)
        out = await node({})
        assert out["last_worker_empty"] == ""

    @pytest.mark.asyncio
    async def test_preserves_existing_keys(self):
        node = _with_empty_signal(_node_returning(_LONG_OK), PATTERNS)
        out = await node({})
        assert out["last_worker_id"] == "w1"
        assert out["token_usage"] == 123
        assert len(out["messages"]) == 1


class TestErrorTakesPrecedence:
    """§6.1 — 오류와 빈 결과가 동시 성립하면 오류가 우선(블록 2개 동시 렌더 방지)."""

    @pytest.mark.asyncio
    async def test_skips_detection_when_worker_error_present(self):
        node = _with_empty_signal(
            _node_returning(_LONG_EMPTY, last_worker_error="Error executing tool"),
            PATTERNS,
        )
        out = await node({})
        assert out["last_worker_empty"] == ""
        assert out["last_worker_error"] == "Error executing tool"

    @pytest.mark.asyncio
    async def test_detects_when_error_is_blank(self):
        node = _with_empty_signal(
            _node_returning(_LONG_EMPTY, last_worker_error=""), PATTERNS,
        )
        out = await node({})
        assert out["last_worker_empty"] != ""


class TestDefensiveBehavior:
    """§6.1 — 신규 코드가 기존 워커 경로를 깨뜨리지 않는다."""

    @pytest.mark.asyncio
    async def test_no_messages_key(self):
        async def node(state):
            return {"last_worker_id": "w1"}
        out = await _with_empty_signal(node, PATTERNS)({})
        assert out["last_worker_empty"] == ""

    @pytest.mark.asyncio
    async def test_empty_messages_list(self):
        async def node(state):
            return {"messages": [], "last_worker_id": "w1"}
        out = await _with_empty_signal(node, PATTERNS)({})
        assert out["last_worker_empty"] == ""

    @pytest.mark.asyncio
    async def test_non_string_content(self):
        node = _with_empty_signal(
            _node_returning([{"type": "text", "text": "x"}]), PATTERNS,
        )
        out = await node({})
        assert out["last_worker_empty"] == ""

    @pytest.mark.asyncio
    async def test_non_dict_return_passes_through(self):
        async def node(state):
            return "not-a-dict"
        assert await _with_empty_signal(node, PATTERNS)({}) == "not-a-dict"

    @pytest.mark.asyncio
    async def test_none_patterns_safe(self):
        node = _with_empty_signal(_node_returning(_LONG_EMPTY), None)
        out = await node({})
        assert out["last_worker_empty"] == ""
