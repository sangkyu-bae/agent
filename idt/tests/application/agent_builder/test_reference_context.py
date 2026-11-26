"""RunAgentRequest.reference_context — 내부
호출자 전용 참고 자료 (stock-analysis-agents DD5).

- 기본 None 이면 메시지가 그대로다 (기존 호출자 영향 0)
- 있으면 마지막 사용자 메시지 뒤에 "사용자 입력 아님" 표시를 달아 덧붙인다
  (PII 마스킹은 compile 단계 LLM 래퍼가 하므로 메시지 위치와 무관하게 적용된다)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from src.application.agent_builder.reference_context import (
    REFERENCE_HEADER,
    attach_reference_context,
)
from src.application.agent_builder.schemas import RunAgentRequest


def test_request_field_defaults_to_none_and_is_bounded():
    req = RunAgentRequest(query="q", user_id="u")
    assert req.reference_context is None
    RunAgentRequest(query="q", user_id="u", reference_context="x" * 40_000)
    with pytest.raises(ValidationError):
        RunAgentRequest(query="q", user_id="u", reference_context="x" * 40_001)


def test_none_or_blank_leaves_messages_untouched():
    messages = [{"role": "user", "content": "질문"}]
    assert attach_reference_context(messages, None) is messages
    assert attach_reference_context(messages, "   ") is messages


def test_appends_block_to_last_user_text_message():
    history = {"role": "assistant", "content": "이전 답변"}
    messages = [history, {"role": "user", "content": "섹션을 써라"}]
    out = attach_reference_context(messages, "현재가 70,000원")
    assert out[0] is history
    assert out[1]["role"] == "user"
    assert out[1]["content"] == f"섹션을 써라\n\n{REFERENCE_HEADER}\n현재가 70,000원"
    # 원본은 바꾸지 않는다
    assert messages[1]["content"] == "섹션을 써라"


def test_appends_text_block_when_content_is_a_list():
    image = {"type": "image_url", "image_url": {"url": "data:..."}}
    messages = [{"role": "user", "content": [{"type": "text", "text": "질문"}, image]}]
    out = attach_reference_context(messages, "자료")
    assert out[0]["content"][:2] == [{"type": "text", "text": "질문"}, image]
    assert out[0]["content"][2] == {"type": "text", "text": f"{REFERENCE_HEADER}\n자료"}


def test_header_says_it_is_not_user_input():
    assert "사용자 입력 아님" in REFERENCE_HEADER


def test_no_user_message_is_left_untouched():
    messages = [{"role": "assistant", "content": "x"}]
    assert attach_reference_context(messages, "자료") is messages
    assert attach_reference_context([], "자료") == []
