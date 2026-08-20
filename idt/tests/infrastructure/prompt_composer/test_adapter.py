"""prompt-composer Design §8.4 #1~4 — LLM 어댑터 테스트.

핵심 계약 2개:
- **P2**: `_PromptDraft` 에 계산 필드가 없다 → LLM 이 오염시킬 경로가 없다.
- **P5**: 어떤 실패도 예외로 새어 나가지 않는다 → degraded=True + 폴백 섹션.

실 LLM 을 부르지 않는다. chain 대역을 주입한다.
"""
import asyncio

import pytest
from pydantic import ValidationError
from src.domain.prompt_composer.schemas import ToolMeta
from src.infrastructure.config.prompt_composer_config import PromptComposerConfig
from src.infrastructure.prompt_composer.adapter import (
    LLMPromptGeneratorAdapter,
    _GuideDraft,
    _PromptDraft,
)

_METAS = (
    ToolMeta(
        tool_id="internal:excel_export",
        name="엑셀 내보내기",
        description="표를 엑셀로 내보낸다",
        source="internal",
    ),
)


class _FakeLogger:
    def __init__(self):
        self.records: list[tuple[str, str]] = []

    def info(self, msg, **kw):
        self.records.append(("info", msg))

    def warning(self, msg, **kw):
        self.records.append(("warning", msg))

    def error(self, msg, **kw):
        self.records.append(("error", msg))

    def debug(self, msg, **kw):
        self.records.append(("debug", msg))


class _Chain:
    """지정한 결과나 예외를 돌려주는 체인 대역."""

    def __init__(self, result=None, exc: Exception | None = None, delay: float = 0.0):
        self._result = result
        self._exc = exc
        self._delay = delay
        self.calls: list[dict] = []

    async def ainvoke(self, payload, config=None):
        self.calls.append(payload)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc is not None:
            raise self._exc
        return self._result


def _valid_draft() -> _PromptDraft:
    return _PromptDraft.model_validate(
        {
            "purpose": "문서를 검색해 답하는 에이전트입니다.",
            "roles": [{"title": "검색", "detail": "규정을 찾는다"}],
            "tool_guides": [
                {
                    "tool_id": "internal:excel_export",
                    "when": "표 저장 요청 시",
                    "how": "행 데이터를 전달한다",
                    "caution": "수치를 지어내지 않는다",
                }
            ],
            "principles": ["한국어로 답한다"],
        }
    )


def _adapter(chain, logger=None) -> LLMPromptGeneratorAdapter:
    return LLMPromptGeneratorAdapter(
        logger=logger or _FakeLogger(),
        config=PromptComposerConfig(PROMPT_COMPOSER_TIMEOUT_SEC=0.05),
        chain=chain,
    )


# ── P2: LLM 스키마에 계산 필드가 없다 (Design §8.2 #8) ───────────────────────


@pytest.mark.parametrize(
    "field", ["degraded", "dropped_tool_ids", "unknown_tool_ids", "elapsed_ms"]
)
def test_draft_schema_has_no_system_owned_fields(field):
    """계산 필드가 스키마에 있으면 LLM 이 채울 수 있다 — 없어야 한다 (P2)."""
    assert field not in _PromptDraft.model_fields


def test_draft_schema_has_exactly_the_four_sections():
    assert set(_PromptDraft.model_fields) == {
        "purpose",
        "roles",
        "tool_guides",
        "principles",
    }


def test_draft_guide_schema_has_no_name_field():
    """도구 표기 이름은 카탈로그가 정한다 — LLM 이 개명할 수 없어야 한다."""
    assert set(_GuideDraft.model_fields) == {"tool_id", "when", "how", "caution"}


# ── 정상 경로 ───────────────────────────────────────────────────────────────


async def test_generate_returns_sections_without_degrading():
    adapter = _adapter(_Chain(result=_valid_draft()))
    sections, degraded, reason, elapsed = await adapter.generate(
        "사내 규정 봇", _METAS, None, [], "req-1"
    )
    assert degraded is False
    assert reason is None
    assert sections.purpose.startswith("문서를 검색해")
    assert sections.tool_guides[0].tool_id == "internal:excel_export"
    assert elapsed >= 0


async def test_generate_accepts_dict_output_from_structured_llm():
    """structured output 이 dict 로 오는 구현도 있다."""
    adapter = _adapter(_Chain(result=_valid_draft().model_dump()))
    sections, degraded, _, _ = await adapter.generate(
        "요청", _METAS, None, [], "req-1"
    )
    assert degraded is False
    assert sections.purpose != ""


async def test_generate_fills_guide_name_from_catalog():
    adapter = _adapter(_Chain(result=_valid_draft()))
    sections, _, _, _ = await adapter.generate("요청", _METAS, None, [], "req-1")
    assert sections.tool_guides[0].name == "엑셀 내보내기"


async def test_generate_applies_section_caps():
    draft = _PromptDraft.model_validate(
        {
            "purpose": "목적",
            "roles": [{"title": f"r{i}", "detail": "d"} for i in range(30)],
            "tool_guides": [],
            "principles": [f"p{i}" for i in range(30)],
        }
    )
    adapter = _adapter(_Chain(result=draft))
    sections, _, _, _ = await adapter.generate("요청", (), None, [], "req-1")
    assert len(sections.roles) == 6
    assert len(sections.principles) == 10


# ── P5 / SC-02: 실패 4종은 전부 degraded (Design E1~E4) ─────────────────────


async def test_llm_exception_degrades_instead_of_raising():
    logger = _FakeLogger()
    adapter = _adapter(_Chain(exc=RuntimeError("boom")), logger)
    sections, degraded, reason, _ = await adapter.generate(
        "사내 규정 봇", _METAS, None, [], "req-1"
    )
    assert degraded is True
    assert reason == "error"
    assert sections.purpose != ""
    assert ("error", "prompt generation error, fallback=degraded") in logger.records


async def test_timeout_degrades_with_timeout_reason():
    logger = _FakeLogger()
    adapter = _adapter(_Chain(result=_valid_draft(), delay=0.5), logger)
    _, degraded, reason, _ = await adapter.generate(
        "요청", _METAS, None, [], "req-1"
    )
    assert degraded is True
    assert reason == "timeout"
    assert any(level == "warning" for level, _ in logger.records)


async def test_schema_violation_degrades():
    adapter = _adapter(_Chain(result={"unexpected": "shape"}))
    _, degraded, reason, _ = await adapter.generate(
        "요청", _METAS, None, [], "req-1"
    )
    assert degraded is True
    assert reason == "schema"


async def test_blank_purpose_degrades_as_empty():
    draft = _PromptDraft.model_validate(
        {"purpose": "   ", "roles": [], "tool_guides": [], "principles": []}
    )
    adapter = _adapter(_Chain(result=draft))
    sections, degraded, reason, _ = await adapter.generate(
        "요청", _METAS, None, [], "req-1"
    )
    assert degraded is True
    assert reason == "empty"
    assert sections.purpose != ""


async def test_fallback_still_covers_every_tool():
    adapter = _adapter(_Chain(exc=RuntimeError("boom")))
    sections, _, _, _ = await adapter.generate("요청", _METAS, None, [], "req-1")
    assert tuple(g.tool_id for g in sections.tool_guides) == (
        "internal:excel_export",
    )


@pytest.mark.parametrize(
    "exc", [RuntimeError("x"), ValueError("x"), KeyError("x"), OSError("x")]
)
async def test_no_exception_type_escapes(exc):
    adapter = _adapter(_Chain(exc=exc))
    _, degraded, _, _ = await adapter.generate("요청", (), None, [], "req-1")
    assert degraded is True


# ── 프롬프트 조립 (FR-13 · 도구 블록) ────────────────────────────────────────


async def test_intent_block_omitted_when_intent_absent():
    chain = _Chain(result=_valid_draft())
    await _adapter(chain).generate("요청", _METAS, None, [], "req-1")
    assert chain.calls[0]["intent_block"] == ""


async def test_intent_block_omitted_when_intent_degraded():
    """FR-13 — 오염된 판정으로 프롬프트를 왜곡시키지 않는다."""
    chain = _Chain(result=_valid_draft())
    intent = {"label": "qa", "degraded": True, "reason": "timeout"}
    await _adapter(chain).generate("요청", _METAS, intent, [], "req-1")
    assert chain.calls[0]["intent_block"] == ""


async def test_intent_block_present_when_intent_usable():
    chain = _Chain(result=_valid_draft())
    intent = {"label": "document_qa", "degraded": False, "reason": "문서 질의"}
    await _adapter(chain).generate("요청", _METAS, intent, [], "req-1")
    block = chain.calls[0]["intent_block"]
    assert "document_qa" in block


async def test_tools_block_omitted_when_no_tools():
    chain = _Chain(result=_valid_draft())
    await _adapter(chain).generate("요청", (), None, [], "req-1")
    assert chain.calls[0]["tools_block"] == ""


async def test_tools_block_lists_tool_ids():
    chain = _Chain(result=_valid_draft())
    await _adapter(chain).generate("요청", _METAS, None, [], "req-1")
    assert "internal:excel_export" in chain.calls[0]["tools_block"]


async def test_tools_block_truncates_beyond_max_and_warns():
    logger = _FakeLogger()
    metas = tuple(
        ToolMeta(tool_id=f"t{i}", name=f"n{i}", description="d") for i in range(60)
    )
    adapter = LLMPromptGeneratorAdapter(
        logger=logger,
        config=PromptComposerConfig(PROMPT_COMPOSER_MAX_TOOLS=5),
        chain=_Chain(result=_valid_draft()),
    )
    await adapter.generate("요청", metas, None, [], "req-1")
    assert any(level == "warning" for level, _ in logger.records)


async def test_history_is_passed_through_clamped():
    chain = _Chain(result=_valid_draft())
    history = [{"role": "user", "content": "이전 질문"}]
    await _adapter(chain).generate("요청", _METAS, None, history, "req-1")
    assert "이전 질문" in chain.calls[0]["history_block"]


async def test_user_request_reaches_payload():
    chain = _Chain(result=_valid_draft())
    await _adapter(chain).generate("사내 규정 봇", _METAS, None, [], "req-1")
    assert chain.calls[0]["user_request"] == "사내 규정 봇"


# ── 스키마 자체 검증 ────────────────────────────────────────────────────────


def test_draft_rejects_missing_purpose():
    with pytest.raises(ValidationError):
        _PromptDraft.model_validate({"roles": [], "tool_guides": [], "principles": []})


def test_draft_defaults_empty_collections():
    draft = _PromptDraft.model_validate({"purpose": "목적"})
    assert draft.roles == []
    assert draft.tool_guides == []
    assert draft.principles == []
