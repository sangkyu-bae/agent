"""react 워커의 도구 호출 횟수 관측 테스트.

Design Ref: mcp-tool-category-routing Analysis Gap-01 (FR-12)

  ToolCallLimitMiddleware는 langchain 내부에서 초과 호출을 차단하므로 그 사실이
  우리 로그·run step에 남지 않는다. 이번 사이클의 핵심 지표("스크랩 4~5회 → 몇
  회?")를 운영 중에 측정할 수단이 없다는 뜻이라 관측을 추가한다.

  계측 지점은 _wrap_worker다. 워커 react agent의 내부 트레이스(ToolMessage)는
  state로 유출되기 전에 폐기되므로(worker-toolmessage-leak-fix D1), 유출 직전인
  여기서 횟수만 건져 올린다 — _blocked_step_summary가 쓰는 것과 같은 접근.
"""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.application.agent_builder.workflow_compiler import (
    WorkflowCompiler,
    _tool_call_step_summary,
)
from src.application.agent_run.step_tracking import STEP_OUTPUT_SUMMARY_KEY
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy


def _make_compiler():
    return WorkflowCompiler(
        tool_factory=MagicMock(),
        llm_factory=MagicMock(spec=LLMFactoryInterface),
        logger=MagicMock(),
    )


class FakeAgent:
    def __init__(self, messages):
        self._messages = messages

    async def ainvoke(self, _payload):
        return {"messages": self._messages}


def _trace(tool_calls: int, answer: str = "최종 답변"):
    messages = [HumanMessage(content="질문")]
    for i in range(tool_calls):
        messages.append(AIMessage(content="", name="w"))
        messages.append(
            ToolMessage(content=f"결과 {i}", tool_call_id=f"call-{i}")
        )
    messages.append(AIMessage(content=answer))
    return messages


def _state():
    return {"messages": [HumanMessage(content="질문")], "token_usage": 0}


class TestToolCallStepSummary:
    def test_counts_tool_messages(self):
        assert "2회" in _tool_call_step_summary(_trace(2), limit=None)

    def test_returns_empty_when_no_tool_call(self):
        """도구를 쓰지 않은 워커에는 잡음을 남기지 않는다."""
        assert _tool_call_step_summary(_trace(0), limit=None) == ""

    def test_marks_limit_reached(self):
        summary = _tool_call_step_summary(_trace(2), limit=2)
        assert "상한" in summary

    def test_does_not_mark_when_under_limit(self):
        summary = _tool_call_step_summary(_trace(1), limit=2)
        assert "상한" not in summary

    def test_limit_none_never_marks(self):
        assert "상한" not in _tool_call_step_summary(_trace(9), limit=None)


class TestWrapWorkerObservability:
    @pytest.mark.asyncio
    async def test_tool_call_count_reaches_step_summary(self):
        compiler = _make_compiler()
        node = compiler._wrap_worker(
            "scrape_worker", FakeAgent(_trace(3)), tool_call_limit=5,
        )

        out = await node(_state())

        assert "3회" in out[STEP_OUTPUT_SUMMARY_KEY]

    @pytest.mark.asyncio
    async def test_limit_reached_is_visible(self):
        """상한에 걸렸다는 사실이 실행 이력에서 보여야 한다 (Gap-01의 핵심)."""
        compiler = _make_compiler()
        node = compiler._wrap_worker(
            "scrape_worker", FakeAgent(_trace(2)), tool_call_limit=2,
        )

        out = await node(_state())

        assert "상한" in out[STEP_OUTPUT_SUMMARY_KEY]

    @pytest.mark.asyncio
    async def test_no_summary_key_when_no_tool_calls(self):
        """기존 동작 보존 — 도구 미사용 워커는 요약 키를 만들지 않는다."""
        compiler = _make_compiler()
        node = compiler._wrap_worker(
            "chat_worker", FakeAgent(_trace(0)), tool_call_limit=2,
        )

        out = await node(_state())

        assert STEP_OUTPUT_SUMMARY_KEY not in out

    @pytest.mark.asyncio
    async def test_blocked_summary_is_preserved_alongside_count(self):
        """worker-context-injection §6.3 차단 요약을 덮어쓰지 않는다."""
        compiler = _make_compiler()
        blocked = ToolMessage(
            content=ToolArgumentPolicy.build_blocked_message(
                "https://example.com/x"
            ),
            tool_call_id="c1",
        )
        messages = [
            HumanMessage(content="질문"),
            AIMessage(content="", name="w"),
            blocked,
            AIMessage(content="답변"),
        ]
        node = compiler._wrap_worker(
            "scrape_worker", FakeAgent(messages), tool_call_limit=2,
        )

        out = await node(_state())

        summary = out[STEP_OUTPUT_SUMMARY_KEY]
        assert "차단" in summary
        assert "1회" in summary

    @pytest.mark.asyncio
    async def test_worker_answer_contract_is_unchanged(self):
        """관측 추가가 워커 산출 규약(AIMessage 1건)을 바꾸지 않는다."""
        compiler = _make_compiler()
        node = compiler._wrap_worker(
            "scrape_worker", FakeAgent(_trace(2, answer="수집 결과")),
            tool_call_limit=2,
        )

        out = await node(_state())

        assert len(out["messages"]) == 1
        assert out["messages"][0].content == "수집 결과"
        assert out["messages"][0].name == "scrape_worker"
        assert out["last_worker_id"] == "scrape_worker"

    @pytest.mark.asyncio
    async def test_limit_argument_is_optional(self):
        """기존 호출부 호환 — tool_call_limit 미지정도 동작한다."""
        compiler = _make_compiler()
        node = compiler._wrap_worker("w", FakeAgent(_trace(1)))

        out = await node(_state())

        assert "1회" in out[STEP_OUTPUT_SUMMARY_KEY]
