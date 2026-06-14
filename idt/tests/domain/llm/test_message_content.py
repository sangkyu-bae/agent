"""coerce_message_text tests — LangChain message content 정규화 (domain 순수 함수).

FIX-CHAT-REASONING-OBJECT-RENDER Plan §5-1.
스트리밍 chunk.content가 str | list[block] 으로 내려올 때 항상 평탄화된 str을 보장한다.
"""
from src.domain.llm.message_content import coerce_message_text


def test_passthrough_str():
    assert coerce_message_text("hello") == "hello"


def test_empty_str_passthrough():
    assert coerce_message_text("") == ""


def test_flattens_text_block_list():
    blocks = [
        {"type": "text", "text": "안"},
        {"type": "text", "text": "녕"},
    ]
    assert coerce_message_text(blocks) == "안녕"


def test_ignores_non_text_blocks():
    blocks = [
        {"type": "tool_use", "id": "x", "name": "search"},
        {"type": "text", "text": "ok"},
    ]
    assert coerce_message_text(blocks) == "ok"


def test_mixed_str_and_dict_blocks():
    blocks = ["a", {"type": "text", "text": "b"}, "c"]
    assert coerce_message_text(blocks) == "abc"


def test_block_without_text_key_ignored():
    blocks = [{"type": "text"}, {"type": "text", "text": "x"}]
    assert coerce_message_text(blocks) == "x"


def test_block_with_non_str_text_ignored():
    blocks = [{"type": "text", "text": 123}, {"type": "text", "text": "ok"}]
    assert coerce_message_text(blocks) == "ok"


def test_none_returns_empty():
    assert coerce_message_text(None) == ""


def test_unexpected_type_returns_empty():
    assert coerce_message_text(42) == ""


def test_empty_list_returns_empty():
    assert coerce_message_text([]) == ""
