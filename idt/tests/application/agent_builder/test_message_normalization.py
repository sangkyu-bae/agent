"""message_normalization 단위 테스트 (fix-anthropic-prefill-error TC-01~07)."""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.application.agent_builder.message_normalization import (
    DEFAULT_CONTINUATION,
    ensure_user_tail,
)


class TestEnsureUserTail:
    def test_tc01_human_last_is_noop(self):
        """TC-01: user-last → 입력 그대로 (append 없음)."""
        messages = [HumanMessage(content="질문")]
        result = ensure_user_tail(messages)
        assert result == messages
        assert len(result) == 1

    def test_tc02_ai_last_appends_instruction(self):
        """TC-02: assistant-last → 지시 HumanMessage append."""
        messages = [
            HumanMessage(content="질문"),
            AIMessage(content="워커 결과", name="worker_0"),
        ]
        result = ensure_user_tail(messages, instruction="계속하세요.")
        assert len(result) == 3
        assert isinstance(result[-1], HumanMessage)
        assert result[-1].content == "계속하세요."
        # 기존 메시지 보존 (name 포함)
        assert result[1].name == "worker_0"

    def test_tc03_consecutive_ai_appends_single_human(self):
        """TC-03: 연속 assistant-last → Human 1개만 append."""
        messages = [
            HumanMessage(content="질문"),
            AIMessage(content="결과1", name="worker_0"),
            AIMessage(content="결과2", name="worker_1"),
        ]
        result = ensure_user_tail(messages)
        assert len(result) == 4
        assert isinstance(result[-1], HumanMessage)
        assert isinstance(result[-2], AIMessage)

    def test_tc04_tool_message_last_is_noop(self):
        """TC-04: tool-last → no-op (Anthropic에서 tool_result는 user측 블록)."""
        messages = [
            HumanMessage(content="질문"),
            AIMessage(content="", tool_calls=[
                {"name": "t", "args": {}, "id": "call_1"},
            ]),
            ToolMessage(content="툴 결과", tool_call_id="call_1"),
        ]
        result = ensure_user_tail(messages)
        assert result == messages
        assert len(result) == 3

    def test_tc05_dict_assistant_last_appends(self):
        """TC-05: dict 형태 assistant-last → append 발생."""
        messages = [
            {"role": "user", "content": "질문"},
            {"role": "assistant", "content": "응답"},
        ]
        result = ensure_user_tail(messages)
        assert len(result) == 3
        assert isinstance(result[-1], HumanMessage)
        assert result[-1].content == DEFAULT_CONTINUATION

    def test_tc05b_dict_user_last_is_noop(self):
        """TC-05b: dict 형태 user-last → no-op."""
        messages = [{"role": "user", "content": "질문"}]
        result = ensure_user_tail(messages)
        assert result == messages

    def test_tc06_empty_with_instruction(self):
        """TC-06: 빈 배열 + instruction → [HumanMessage(instruction)]."""
        result = ensure_user_tail([], instruction="시작하세요.")
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "시작하세요."

    def test_tc06b_empty_without_instruction(self):
        """TC-06b: 빈 배열 + instruction 빈 문자열 → 그대로."""
        result = ensure_user_tail([], instruction="")
        assert result == []

    def test_tc07_original_list_not_mutated(self):
        """TC-07: 원본 리스트 비변형 (LangGraph state 공유 안전)."""
        messages = [
            HumanMessage(content="질문"),
            AIMessage(content="응답"),
        ]
        result = ensure_user_tail(messages)
        assert len(messages) == 2  # 원본 무변형
        assert result is not messages
