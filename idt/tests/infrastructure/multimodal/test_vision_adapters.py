"""비전 어댑터 3종 — Design §9.5, FR-05/FR-20.

실 LLM 없이 fake BaseChatModel 로: (1) 벤더별 이미지 블록 포맷, (2) 출력 모드 폴백
strict→json→text 와 degraded 표기, (3) usage 전달을 검증한다.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, ConfigDict
from src.domain.llm_model.entity import LlmModel
from src.domain.multimodal.interfaces import DescribeOptions
from src.domain.multimodal.schemas import DescriptionDraft
from src.domain.multimodal.value_objects import BBox, ElementType, ImageCandidate
from src.infrastructure.multimodal.vision.anthropic_vision_adapter import (
    AnthropicVisionAdapter,
)
from src.infrastructure.multimodal.vision.base_vision_adapter import (
    BaseVisionAdapter,
    VisionCallError,
)
from src.infrastructure.multimodal.vision.openai_compatible_vision_adapter import (
    OpenAICompatibleVisionAdapter,
)
from src.infrastructure.multimodal.vision.openai_vision_adapter import (
    OpenAIVisionAdapter,
)

DRAFT = {
    "detected_type": "figure",
    "description": "빨간 사각형",
    "keywords": ["사각형"],
    "markdown_table": None,
    "chart": None,
    "page_text": None,
}


def _model(provider="openai", base_url=None) -> LlmModel:
    now = datetime.now(UTC)
    return LlmModel(
        id="m1",
        provider=provider,
        model_name="x",
        display_name="X",
        description=None,
        api_key_env="K",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
        base_url=base_url,
        supports_vision=True,
    )


def _image() -> ImageCandidate:
    return ImageCandidate(
        page=1,
        bbox=BBox(0, 0, 10, 10),
        image_bytes=b"\x89PNGdata",
        mime="image/png",
        width=300,
        height=200,
        area_ratio=0.2,
        sha256="a" * 64,
        hint_type=ElementType.FIGURE,
    )


class FakeStructured:
    """llm.with_structured_output(...) 의 반환 객체 흉내."""

    def __init__(self, fn):
        self._fn = fn
        self.calls: list = []
        self.configs: list = []

    async def ainvoke(self, messages, config=None):
        self.calls.append(messages)
        self.configs.append(config)
        return self._fn(messages)


class FakeChat:
    """BaseChatModel 흉내.

    strict/json 모드는 with_structured_output, text 는 ainvoke.
    """

    def __init__(self, strict=None, json_mode=None, text=None):
        self._modes = {"strict": strict, "json": json_mode}
        self._text = text
        self.structured_calls: list[tuple[str, FakeStructured]] = []
        self.plain_calls: list = []

    def with_structured_output(self, schema, method=None, strict=None, **kw):
        mode = "strict" if strict else "json"
        fn = self._modes[mode]
        if fn is None:
            raise AssertionError(f"{mode} 모드 미준비")
        fs = FakeStructured(fn)
        self.structured_calls.append((mode, fs))
        return fs

    async def ainvoke(self, messages, config=None):
        self.plain_calls.append(messages)
        if self._text is None:
            raise AssertionError("text 모드 미준비")
        return self._text(messages)


def _factory(chat: FakeChat) -> MagicMock:
    f = MagicMock()
    f.create.return_value = chat
    return f


def _ok_draft(_msgs):
    from src.domain.multimodal.schemas import DescriptionDraft

    return DescriptionDraft(**DRAFT)


def _human_image_block(messages):
    human = messages[-1]
    return human.content[-1]


# ── 포맷 ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_openai_adapter_builds_image_url_block_with_detail():
    chat = FakeChat(strict=_ok_draft)
    a = OpenAIVisionAdapter(_factory(chat), _model("openai"), MagicMock())
    assert a.provider == "openai"
    out = await a.describe(
        _image(), ElementType.FIGURE, DescribeOptions("ko", "detailed")
    )
    block = _human_image_block(chat.structured_calls[0][1].calls[0])
    b64 = base64.b64encode(b"\x89PNGdata").decode()
    assert block == {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
    }
    assert out.output_mode == "strict" and out.degraded_output_mode is False
    assert out.draft.description == "빨간 사각형"


@pytest.mark.asyncio
async def test_openai_brief_maps_to_low_detail():
    chat = FakeChat(strict=_ok_draft)
    a = OpenAIVisionAdapter(_factory(chat), _model("openai"), MagicMock())
    await a.describe(_image(), ElementType.FIGURE, DescribeOptions("ko", "brief"))
    block = _human_image_block(chat.structured_calls[0][1].calls[0])
    assert block["image_url"]["detail"] == "low"


@pytest.mark.asyncio
async def test_anthropic_adapter_builds_base64_source_block():
    chat = FakeChat(strict=_ok_draft)
    a = AnthropicVisionAdapter(_factory(chat), _model("anthropic"), MagicMock())
    assert a.provider == "anthropic"
    await a.describe(_image(), ElementType.FIGURE, DescribeOptions("ko", "detailed"))
    block = _human_image_block(chat.structured_calls[0][1].calls[0])
    assert block == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(b"\x89PNGdata").decode(),
        },
    }


@pytest.mark.asyncio
async def test_openai_compatible_skips_strict_and_uses_json_first():
    chat = FakeChat(json_mode=_ok_draft)
    a = OpenAICompatibleVisionAdapter(_factory(chat), _model("ollama"), MagicMock())
    assert a.output_modes == ("json", "text")
    out = await a.describe(
        _image(), ElementType.FIGURE, DescribeOptions("ko", "detailed")
    )
    assert [m for m, _ in chat.structured_calls] == ["json"]
    assert out.output_mode == "json" and out.degraded_output_mode is True
    block = _human_image_block(chat.structured_calls[0][1].calls[0])
    assert block["type"] == "image_url"


# ── 폴백 ───────────────────────────────────────────────────────────────────────


def _raise(exc):
    def fn(_m):
        raise exc

    return fn


@pytest.mark.asyncio
async def test_fallback_strict_to_json_marks_degraded():
    chat = FakeChat(
        strict=_raise(ValueError("schema unsupported")), json_mode=_ok_draft
    )
    a = OpenAIVisionAdapter(_factory(chat), _model("openai"), MagicMock())
    out = await a.describe(
        _image(), ElementType.FIGURE, DescribeOptions("ko", "detailed")
    )
    assert [m for m, _ in chat.structured_calls] == ["strict", "json"]
    assert out.output_mode == "json" and out.degraded_output_mode is True


@pytest.mark.asyncio
async def test_fallback_to_text_parses_json_inside_code_fence():
    text = AIMessage(
        content="설명:\n```json\n" + json.dumps(DRAFT, ensure_ascii=False) + "\n```",
        usage_metadata={"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
    )
    chat = FakeChat(
        strict=_raise(ValueError("x")),
        json_mode=_raise(ValueError("y")),
        text=lambda m: text,
    )
    a = OpenAIVisionAdapter(_factory(chat), _model("openai"), MagicMock())
    out = await a.describe(
        _image(), ElementType.FIGURE, DescribeOptions("ko", "detailed")
    )
    assert out.output_mode == "text" and out.degraded_output_mode is True
    assert out.draft.keywords == ["사각형"]
    assert out.usage == {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}


@pytest.mark.asyncio
async def test_all_modes_fail_raises_vision_call_error_with_last_cause():
    chat = FakeChat(
        strict=_raise(ValueError("a")),
        json_mode=_raise(ValueError("b")),
        text=lambda m: AIMessage(content="이건 JSON 이 아님"),
    )
    a = OpenAIVisionAdapter(_factory(chat), _model("openai"), MagicMock())
    with pytest.raises(VisionCallError) as ei:
        await a.describe(
            _image(), ElementType.FIGURE, DescribeOptions("ko", "detailed")
        )
    assert "text" in str(ei.value)


@pytest.mark.asyncio
async def test_rate_limit_like_errors_are_not_swallowed_by_fallback():
    """429/타임아웃은 출력 모드 문제가 아니다.

    폴백하지 않고 즉시 전파(UseCase 가 재시도).
    """

    class RateLimitError(Exception):
        status_code = 429

    chat = FakeChat(strict=_raise(RateLimitError("slow down")), json_mode=_ok_draft)
    a = OpenAIVisionAdapter(_factory(chat), _model("openai"), MagicMock())
    with pytest.raises(RateLimitError):
        await a.describe(
            _image(), ElementType.FIGURE, DescribeOptions("ko", "detailed")
        )
    assert [m for m, _ in chat.structured_calls] == ["strict"]


# ── 공통 ───────────────────────────────────────────────────────────────────────


def test_factory_called_once_per_adapter_with_temperature_zero():
    chat = FakeChat(strict=_ok_draft)
    f = _factory(chat)
    OpenAIVisionAdapter(f, _model("openai"), MagicMock())
    f.create.assert_called_once()
    assert f.create.call_args.kwargs.get("temperature", 0.0) == 0.0


def test_base_adapter_is_abstract():
    with pytest.raises(TypeError):
        BaseVisionAdapter(MagicMock(), _model(), MagicMock())  # type: ignore[abstract]


@pytest.mark.asyncio
async def test_callbacks_are_passed_in_config():
    chat = FakeChat(strict=_ok_draft)
    cb = object()
    a = OpenAIVisionAdapter(
        _factory(chat), _model("openai"), MagicMock(), callbacks=[cb]
    )
    await a.describe(_image(), ElementType.FIGURE, DescribeOptions("ko", "detailed"))
    # FakeStructured.ainvoke(messages, config) — config 에 callbacks 전달
    # config 는 생성 시 고정된 불변값 — FakeStructured 가 받은 config 로 검증
    assert chat.structured_calls[0][1].configs[-1] == {"callbacks": [cb]}


@pytest.mark.asyncio
async def test_structured_include_raw_shape_yields_usage():
    """FR-20: include_raw 응답에서 raw.usage_metadata 를 usage 로 전달한다."""

    def raw_shape(_msgs):
        return {
            "raw": AIMessage(
                content="",
                usage_metadata={
                    "input_tokens": 900,
                    "output_tokens": 80,
                    "total_tokens": 980,
                },
            ),
            "parsed": DescriptionDraft(**DRAFT),
            "parsing_error": None,
        }

    chat = FakeChat(strict=raw_shape)
    a = OpenAIVisionAdapter(_factory(chat), _model("openai"), MagicMock())
    out = await a.describe(_image(), ElementType.FIGURE, DescribeOptions("ko", "brief"))
    assert out.usage == {"input_tokens": 900, "output_tokens": 80, "total_tokens": 980}
    assert out.output_mode == "strict"


@pytest.mark.asyncio
async def test_structured_parsing_error_triggers_fallback():
    def broken(_msgs):
        return {
            "raw": AIMessage(content="x"),
            "parsed": None,
            "parsing_error": ValueError("bad"),
        }

    chat = FakeChat(strict=broken, json_mode=_ok_draft)
    a = OpenAIVisionAdapter(_factory(chat), _model("openai"), MagicMock())
    out = await a.describe(_image(), ElementType.FIGURE, DescribeOptions("ko", "brief"))
    assert out.output_mode == "json" and out.degraded_output_mode is True


# ── describe_with (golden-sample-blueprint D8: 스키마 일반화) ─────────────────


class _OtherDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    score: int


@pytest.mark.asyncio
async def test_describe_with_uses_given_schema_and_strict_first():
    chat = FakeChat(strict=lambda _m: _OtherDraft(kind="cover", score=3))
    adapter = OpenAIVisionAdapter(_factory(chat), _model("openai"), MagicMock())
    outcome = await adapter.describe_with([SystemMessage(content="s")], _OtherDraft)
    assert isinstance(outcome.draft, _OtherDraft) and outcome.draft.kind == "cover"
    assert outcome.output_mode == "strict" and outcome.degraded_output_mode is False


@pytest.mark.asyncio
async def test_describe_with_falls_back_to_text_with_other_schema():
    def boom(_m):
        raise ValueError("no")

    chat = FakeChat(
        strict=boom,
        json_mode=boom,
        text=lambda _m: AIMessage(content='```json\n{"kind":"toc","score":1}\n```'),
    )
    adapter = OpenAIVisionAdapter(_factory(chat), _model("openai"), MagicMock())
    outcome = await adapter.describe_with([SystemMessage(content="s")], _OtherDraft)
    assert outcome.draft == _OtherDraft(kind="toc", score=1)
    assert outcome.output_mode == "text" and outcome.degraded_output_mode is True


@pytest.mark.asyncio
async def test_describe_with_rejects_schema_mismatch_in_text_mode():
    def boom(_m):
        raise ValueError("no")

    chat = FakeChat(
        strict=boom, json_mode=boom, text=lambda _m: AIMessage(content='{"kind":"x"}')
    )
    adapter = OpenAIVisionAdapter(_factory(chat), _model("openai"), MagicMock())
    with pytest.raises(VisionCallError):
        await adapter.describe_with([SystemMessage(content="s")], _OtherDraft)
