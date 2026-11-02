"""message_content 헬퍼 테스트 — chat-image-attachment Design §8.2 #6, #7 / D-02."""
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.message_content import (
    image_blocks,
    is_multimodal,
    message_text,
    redact_image_blocks,
)

OPENAI_IMG = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA", "detail": "high"}}
ANTHROPIC_IMG = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "BBBB"}}
MULTI = [{"type": "text", "text": "표에서 3분기 값은?"}, OPENAI_IMG, ANTHROPIC_IMG]


class TestMessageText:
    def test_str_content_returned_as_is(self) -> None:
        assert message_text(HumanMessage(content="hi")) == "hi"
        assert message_text({"role": "user", "content": "hi"}) == "hi"

    def test_list_content_keeps_only_text_blocks(self) -> None:
        out = message_text(HumanMessage(content=MULTI))
        assert out == "표에서 3분기 값은?"
        assert "base64" not in out

    def test_dict_message_with_list_content(self) -> None:
        assert message_text({"role": "user", "content": MULTI}) == "표에서 3분기 값은?"

    def test_non_message_falls_back_to_str(self) -> None:
        assert message_text("plain") == "plain"
        assert message_text(None) == ""

    def test_image_markers_opt_in(self) -> None:
        out = message_text(HumanMessage(content=MULTI), keep_image_markers=True)
        assert out == "표에서 3분기 값은?\n[image:image/png]\n[image:image/jpeg]"

    def test_ai_message_list_content(self) -> None:
        assert message_text(AIMessage(content=[{"type": "text", "text": "ok"}])) == "ok"


class TestIsMultimodal:
    def test_true_only_with_image_block(self) -> None:
        assert is_multimodal(HumanMessage(content=MULTI)) is True
        assert is_multimodal(HumanMessage(content=[{"type": "text", "text": "x"}])) is False
        assert is_multimodal(HumanMessage(content="x")) is False
        assert is_multimodal({"role": "user", "content": MULTI}) is True


class TestImageBlocks:
    def test_returns_image_blocks_in_order(self) -> None:
        assert image_blocks(HumanMessage(content=MULTI)) == [OPENAI_IMG, ANTHROPIC_IMG]

    def test_empty_for_text_only(self) -> None:
        assert image_blocks(HumanMessage(content="x")) == []


class TestRedactImageBlocks:
    def test_str_unchanged(self) -> None:
        assert redact_image_blocks("hello") == "hello"

    def test_image_blocks_replaced_with_text_marker(self) -> None:
        out = redact_image_blocks(MULTI)
        assert out == [
            {"type": "text", "text": "표에서 3분기 값은?"},
            {"type": "text", "text": "[image:image/png]"},
            {"type": "text", "text": "[image:image/jpeg]"},
        ]
        assert "AAAA" not in str(out) and "BBBB" not in str(out)

    def test_does_not_mutate_input(self) -> None:
        src = [dict(OPENAI_IMG)]
        redact_image_blocks(src)
        assert src[0] == OPENAI_IMG


class TestRedactMessages:
    """Analysis G-C1 — 승인 스냅샷 직렬화 전 이미지 블록 축약."""

    def test_base_message_with_image_is_copied_and_redacted(self) -> None:
        from src.application.agent_builder.message_content import redact_messages

        src = [HumanMessage(content=MULTI), AIMessage(content="답")]
        out = redact_messages(src)
        assert out[0] is not src[0]
        assert "AAAA" not in str(out[0].content) and "BBBB" not in str(out[0].content)
        assert out[0].content[0] == {"type": "text", "text": "표에서 3분기 값은?"}
        assert out[1] is src[1]  # 이미지 없는 메시지는 그대로
        assert src[0].content == MULTI  # 원본 불변

    def test_dict_message_redacted(self) -> None:
        from src.application.agent_builder.message_content import redact_messages

        out = redact_messages([{"role": "user", "content": MULTI}])
        assert "AAAA" not in str(out)
