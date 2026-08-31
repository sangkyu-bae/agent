"""prompts.build_messages — Design §9.5, FR-06."""

from src.domain.multimodal.interfaces import DescribeOptions
from src.domain.multimodal.value_objects import ElementType
from src.infrastructure.multimodal.prompts import build_messages

IMAGE_BLOCK = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}


def _msgs(et: ElementType, lang="ko", detail="detailed"):
    return build_messages(et, DescribeOptions(lang, detail), IMAGE_BLOCK)


def test_returns_system_and_human_with_image_block_last():
    msgs = _msgs(ElementType.FIGURE)
    assert [m.type for m in msgs] == ["system", "human"]
    human = msgs[1]
    assert isinstance(human.content, list)
    assert human.content[-1] == IMAGE_BLOCK
    assert human.content[0]["type"] == "text"


def test_system_prompt_has_injection_guard_and_language():
    sys_ko = _msgs(ElementType.FIGURE).pop(0).content
    assert "지시" in sys_ko and "무시" in sys_ko  # 이미지 내 지시 무시 (Design §7)
    assert "한국어" in sys_ko
    sys_en = _msgs(ElementType.FIGURE, lang="en").pop(0).content
    assert "English" in sys_en


def test_each_type_has_distinct_instruction():
    texts = {et: _msgs(et)[1].content[0]["text"] for et in ElementType}
    assert len(set(texts.values())) == 4
    assert "마크다운" in texts[ElementType.TABLE_IMAGE]
    assert "축" in texts[ElementType.CHART] and "수치" in texts[ElementType.CHART]
    assert "전사" in texts[ElementType.PAGE_SCAN]


def test_detail_level_changes_instruction():
    brief = _msgs(ElementType.FIGURE, detail="brief")[1].content[0]["text"]
    detailed = _msgs(ElementType.FIGURE, detail="detailed")[1].content[0]["text"]
    assert brief != detailed
