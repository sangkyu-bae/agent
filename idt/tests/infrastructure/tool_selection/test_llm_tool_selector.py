"""tool-recommender Design §8.3 — L2 통합 테스트 (LLM 셀렉터).

LLM은 스텁으로 주입한다. 실 LLM 호출은 module-3의 골드셋 평가에서만 한다.

핵심 검증축: **어떤 실패에서도 예외가 새어나가지 않고 필수 세트가 살아남는가**
(Plan RISK — 기능 회귀).
"""
import asyncio
from datetime import datetime

import pytest
from src.domain.llm_model.entity import LlmModel
from src.domain.tool_selection.policies import SelectionReason
from src.domain.tool_selection.schemas import ToolCandidate, ToolSource
from src.infrastructure.tool_selection.llm_tool_selector import LLMToolSelector
from src.infrastructure.tool_selection.null_cache import NullSelectionCache

# ── 테스트 더블 ──────────────────────────────────────────────────────────────


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    """ainvoke만 흉내내는 최소 스텁."""

    def __init__(self, content: str = "", exc: Exception | None = None,
                 delay: float = 0.0) -> None:
        self._content = content
        self._exc = exc
        self._delay = delay
        self.calls = 0

    async def ainvoke(self, messages, **kwargs):
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc is not None:
            raise self._exc
        return _Response(self._content)


class _FakeFactory:
    def __init__(self, llm: _FakeLLM) -> None:
        self.llm = llm
        self.create_calls = 0

    def create(self, llm_model, temperature: float = 0.0):
        self.create_calls += 1
        return self.llm


class _SpyLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def _rec(self, level: str, message: str, **kwargs) -> None:
        self.records.append((level, message, kwargs))

    def debug(self, message: str, **kwargs) -> None:
        self._rec("debug", message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        self._rec("info", message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self._rec("warning", message, **kwargs)

    def error(self, message: str, exception=None, **kwargs) -> None:
        self._rec("error", message, exception=exception, **kwargs)

    def critical(self, message: str, exception=None, **kwargs) -> None:
        self._rec("critical", message, exception=exception, **kwargs)

    def levels(self) -> list[str]:
        return [level for level, _, _ in self.records]


def _model() -> LlmModel:
    now = datetime(2026, 1, 1)
    return LlmModel(
        id="tool-selector-llm",
        provider="openai",
        model_name="gpt-4o-mini",
        display_name="Tool Selector",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
    )


def _candidates(n: int) -> list[ToolCandidate]:
    return [
        ToolCandidate(
            tool_id=f"internal:tool_{i}",
            name=f"tool_{i}",
            description=f"{i}번 도구입니다.",
            source=ToolSource.INTERNAL,
        )
        for i in range(n)
    ]


def _build(llm: _FakeLLM, *, top_k: int = 3, timeout_sec: float = 3.0):
    logger = _SpyLogger()
    selector = LLMToolSelector(
        llm_factory=_FakeFactory(llm),
        llm_model=_model(),
        logger=logger,
        cache=NullSelectionCache(),
        top_k=top_k,
        timeout_sec=timeout_sec,
    )
    return selector, logger


# ── #1 정상 경로 ─────────────────────────────────────────────────────────────


async def test_normal_selection_unions_required_and_selected():
    llm = _FakeLLM('{"tool_ids": ["internal:tool_1", "internal:tool_3"]}')
    selector, _ = _build(llm)

    result = await selector.select(
        "엑셀로 뽑아줘",
        _candidates(6),
        required_ids=("internal:tool_0",),
        request_id="req-1",
    )

    assert result.fallback is False
    assert result.reason is None
    assert result.selected_ids == ("internal:tool_1", "internal:tool_3")
    assert result.final_ids == (
        "internal:tool_0", "internal:tool_1", "internal:tool_3",
    )
    assert result.candidate_count == 6
    assert llm.calls == 1


async def test_normal_selection_records_elapsed_and_logs_info():
    llm = _FakeLLM('{"tool_ids": ["internal:tool_1"]}')
    selector, logger = _build(llm)

    result = await selector.select("질의", _candidates(6))

    assert result.elapsed_ms >= 0
    assert "info" in logger.levels()


async def test_bare_json_array_is_accepted():
    llm = _FakeLLM('["internal:tool_2"]')
    selector, _ = _build(llm)

    result = await selector.select("질의", _candidates(6))

    assert result.selected_ids == ("internal:tool_2",)
    assert result.fallback is False


async def test_code_fenced_json_is_accepted():
    llm = _FakeLLM('```json\n{"tool_ids": ["internal:tool_2"]}\n```')
    selector, _ = _build(llm)

    result = await selector.select("질의", _candidates(6))

    assert result.selected_ids == ("internal:tool_2",)
    assert result.fallback is False


# ── #2 LLM 예외 (Design §6.1 #3) ────────────────────────────────────────────


async def test_llm_exception_falls_back_to_required_without_raising():
    llm = _FakeLLM(exc=RuntimeError("boom"))
    selector, logger = _build(llm)

    result = await selector.select(
        "질의", _candidates(6), required_ids=("internal:tool_0",)
    )

    assert result.fallback is True
    assert result.reason == SelectionReason.LLM_ERROR
    assert result.final_ids == ("internal:tool_0",)
    assert result.selected_ids == ()
    assert "warning" in logger.levels()


async def test_llm_exception_preserves_stack_trace_in_log():
    """CLAUDE.md §6 — 스택 트레이스 없는 에러 처리 금지."""
    boom = RuntimeError("boom")
    selector, logger = _build(_FakeLLM(exc=boom))

    await selector.select("질의", _candidates(6))

    warnings = [kw for lvl, _, kw in logger.records if lvl == "warning"]
    assert any(kw.get("exception") is boom for kw in warnings)


async def test_llm_exception_with_no_required_returns_empty():
    selector, _ = _build(_FakeLLM(exc=RuntimeError("boom")))

    result = await selector.select("질의", _candidates(6))

    assert result.fallback is True
    assert result.final_ids == ()


# ── #3 타임아웃 (Design §6.1 #4) ────────────────────────────────────────────


async def test_llm_timeout_falls_back_to_required():
    llm = _FakeLLM('{"tool_ids": ["internal:tool_1"]}', delay=0.2)
    selector, logger = _build(llm, timeout_sec=0.01)

    result = await selector.select(
        "질의", _candidates(6), required_ids=("internal:tool_0",)
    )

    assert result.fallback is True
    assert result.reason == SelectionReason.LLM_TIMEOUT
    assert result.final_ids == ("internal:tool_0",)
    assert "warning" in logger.levels()


# ── #4 파싱 실패 (Design §6.1 #5) ───────────────────────────────────────────


@pytest.mark.parametrize(
    "content",
    [
        "응답: {잘못된json",
        "",
        "저는 도구를 고를 수 없습니다.",
        '{"tools": ["internal:tool_1"]}',  # 키 이름이 다름
        '{"tool_ids": "internal:tool_1"}',  # 배열이 아님
    ],
)
async def test_unparseable_response_falls_back_to_required(content):
    selector, logger = _build(_FakeLLM(content))

    result = await selector.select(
        "질의", _candidates(6), required_ids=("internal:tool_0",)
    )

    assert result.fallback is True
    assert result.reason == SelectionReason.PARSE_ERROR
    assert result.final_ids == ("internal:tool_0",)
    assert "warning" in logger.levels()


# ── #5 환각 ID 정제 (Design §6.1 #6) ────────────────────────────────────────


async def test_unknown_ids_are_dropped_and_logged():
    llm = _FakeLLM(
        '{"tool_ids": ["internal:tool_1", "internal:ghost", "mcp:x:ghost2"]}'
    )
    selector, logger = _build(llm)

    result = await selector.select("질의", _candidates(6))

    assert result.selected_ids == ("internal:tool_1",)
    assert result.dropped_ids == ("internal:ghost", "mcp:x:ghost2")
    assert result.reason == SelectionReason.SANITIZED
    assert result.fallback is False  # 유효분이 남았으므로 폴백 아님
    assert "warning" in logger.levels()


async def test_all_unknown_ids_becomes_empty_selection_fallback():
    llm = _FakeLLM('{"tool_ids": ["internal:ghost1", "internal:ghost2"]}')
    selector, _ = _build(llm)

    result = await selector.select(
        "질의", _candidates(6), required_ids=("internal:tool_0",)
    )

    assert result.fallback is True
    assert result.reason == SelectionReason.EMPTY_SELECTION
    assert result.final_ids == ("internal:tool_0",)


# ── #6 빈 선택 (Design §6.1 #7) ─────────────────────────────────────────────


async def test_empty_selection_falls_back_to_required():
    selector, _ = _build(_FakeLLM('{"tool_ids": []}'))

    result = await selector.select(
        "질의", _candidates(6), required_ids=("internal:tool_0",)
    )

    assert result.fallback is True
    assert result.reason == SelectionReason.EMPTY_SELECTION
    assert result.final_ids == ("internal:tool_0",)


# ── #7 조기 반환 — LLM 미호출 (Design §6.1 #1, FR-08) ───────────────────────


async def test_under_threshold_skips_llm_entirely():
    llm = _FakeLLM('{"tool_ids": ["internal:tool_0"]}')
    selector, _ = _build(llm, top_k=8)

    result = await selector.select("질의", _candidates(3))

    assert llm.calls == 0
    assert result.fallback is False
    assert result.reason == SelectionReason.UNDER_THRESHOLD
    assert result.final_ids == (
        "internal:tool_0", "internal:tool_1", "internal:tool_2",
    )


async def test_exactly_top_k_candidates_skips_llm():
    llm = _FakeLLM('{"tool_ids": []}')
    selector, _ = _build(llm, top_k=3)

    result = await selector.select("질의", _candidates(3))

    assert llm.calls == 0
    assert len(result.final_ids) == 3


async def test_no_candidates_returns_required_without_llm():
    llm = _FakeLLM('{"tool_ids": []}')
    selector, _ = _build(llm)

    result = await selector.select("질의", [], required_ids=("internal:tool_0",))

    assert llm.calls == 0
    assert result.reason == SelectionReason.NO_CANDIDATES
    assert result.final_ids == ("internal:tool_0",)
    assert result.fallback is False


# ── Port 계약 (Design §4.1) ─────────────────────────────────────────────────


async def test_required_id_absent_from_candidates_still_survives():
    llm = _FakeLLM('{"tool_ids": ["internal:tool_1"]}')
    selector, _ = _build(llm)

    result = await selector.select(
        "질의", _candidates(6), required_ids=("internal:not_a_candidate",)
    )

    assert "internal:not_a_candidate" in result.final_ids


async def test_final_ids_never_exceed_candidates_union_required():
    """§7 권한 경계 불변 — 선별은 축소만 한다."""
    llm = _FakeLLM('{"tool_ids": ["internal:tool_1", "internal:tool_2"]}')
    selector, _ = _build(llm)
    candidates = _candidates(6)

    result = await selector.select(
        "질의", candidates, required_ids=("internal:tool_0",)
    )

    allowed = {c.tool_id for c in candidates} | {"internal:tool_0"}
    assert set(result.final_ids) <= allowed


async def test_final_ids_follow_candidate_order_not_model_order():
    llm = _FakeLLM('{"tool_ids": ["internal:tool_4", "internal:tool_1"]}')
    selector, _ = _build(llm)

    result = await selector.select("질의", _candidates(6))

    assert result.final_ids == ("internal:tool_1", "internal:tool_4")


async def test_selection_is_repeatable_for_same_input():
    def fresh():
        return _build(_FakeLLM('{"tool_ids": ["internal:tool_2"]}'))[0]

    first = await fresh().select("질의", _candidates(6))
    second = await fresh().select("질의", _candidates(6))

    assert first.final_ids == second.final_ids


# ── 저신호 설명 보강이 프롬프트에 반영되는가 (Design §3.3) ───────────────────


async def test_prompt_contains_enriched_description_for_stub_mcp_tool():
    captured: list = []

    class _CapturingLLM(_FakeLLM):
        async def ainvoke(self, messages, **kwargs):
            captured.append(messages)
            return await super().ainvoke(messages, **kwargs)

    llm = _CapturingLLM('{"tool_ids": []}')
    selector, _ = _build(llm)
    candidates = [
        *_candidates(5),
        ToolCandidate(
            tool_id="mcp:s1:search_blog",
            name="search_blog",
            description="MCP tool: search_blog",
            source=ToolSource.MCP,
            server_name="naver_mcp",
        ),
    ]

    await selector.select("블로그 검색", candidates)

    prompt_text = str(captured[0])
    assert "naver_mcp 서버의 'search blog' 기능" in prompt_text
    assert "MCP tool: search_blog" not in prompt_text


async def test_prompt_contains_every_candidate_id():
    captured: list = []

    class _CapturingLLM(_FakeLLM):
        async def ainvoke(self, messages, **kwargs):
            captured.append(messages)
            return await super().ainvoke(messages, **kwargs)

    llm = _CapturingLLM('{"tool_ids": []}')
    selector, _ = _build(llm)
    candidates = _candidates(6)

    await selector.select("질의", candidates)

    prompt_text = str(captured[0])
    for c in candidates:
        assert c.tool_id in prompt_text


# ── #11 NullSelectionCache (Design §8.3 #11) ────────────────────────────────


async def test_null_cache_always_misses():
    cache = NullSelectionCache()
    await cache.set("key", ["a", "b"])
    assert await cache.get("key") is None


async def test_cache_is_consulted_before_llm():
    """캐시 히트 시 LLM을 부르지 않는다 (교체 가능성 검증)."""

    class _HitCache(NullSelectionCache):
        async def get(self, key: str):
            return ("internal:tool_1",)

    llm = _FakeLLM('{"tool_ids": ["internal:tool_5"]}')
    logger = _SpyLogger()
    selector = LLMToolSelector(
        llm_factory=_FakeFactory(llm),
        llm_model=_model(),
        logger=logger,
        cache=_HitCache(),
        top_k=3,
    )

    result = await selector.select("질의", _candidates(6))

    assert llm.calls == 0
    assert result.reason == SelectionReason.CACHE_HIT
    assert result.final_ids == ("internal:tool_1",)


async def test_stale_cache_entry_falls_through_to_llm():
    """캐시 값이 전부 무효해졌으면 히트로 취급하지 않고 새로 선별한다.

    build_cache_key가 후보 집합을 키에 넣으므로 정상 상황에서는 발생하지 않지만,
    캐시를 실구현할 때(공유 캐시·키 충돌·수동 주입) 도달 가능한 경로다. 여기서
    폴백해버리면 도구 목록이 바뀔 때마다 선별이 죽는다.
    """

    class _StaleCache(NullSelectionCache):
        async def get(self, key: str):
            return ("internal:gone_1", "internal:gone_2")

    llm = _FakeLLM('{"tool_ids": ["internal:tool_1"]}')
    selector = LLMToolSelector(
        llm_factory=_FakeFactory(llm),
        llm_model=_model(),
        logger=_SpyLogger(),
        cache=_StaleCache(),
        top_k=3,
    )

    result = await selector.select("질의", _candidates(6))

    assert llm.calls == 1  # 캐시를 무시하고 실제로 선별했다
    assert result.reason is None
    assert result.fallback is False
    assert result.selected_ids == ("internal:tool_1",)


async def test_cache_failure_does_not_break_selection():
    class _BrokenCache(NullSelectionCache):
        async def get(self, key: str):
            raise RuntimeError("cache down")

        async def set(self, key: str, tool_ids) -> None:
            raise RuntimeError("cache down")

    llm = _FakeLLM('{"tool_ids": ["internal:tool_1"]}')
    logger = _SpyLogger()
    selector = LLMToolSelector(
        llm_factory=_FakeFactory(llm),
        llm_model=_model(),
        logger=logger,
        cache=_BrokenCache(),
        top_k=3,
    )

    result = await selector.select("질의", _candidates(6))

    assert result.selected_ids == ("internal:tool_1",)
    assert result.fallback is False


# ── 기본값 ───────────────────────────────────────────────────────────────────


async def test_selector_works_without_explicit_cache():
    """cache 미주입 시 NullSelectionCache로 자동 대체된다."""
    llm = _FakeLLM('{"tool_ids": ["internal:tool_1"]}')
    selector = LLMToolSelector(
        llm_factory=_FakeFactory(llm),
        llm_model=_model(),
        logger=_SpyLogger(),
        top_k=3,
    )

    result = await selector.select("질의", _candidates(6))

    assert result.selected_ids == ("internal:tool_1",)


# ── 프롬프트 설명 압축 (Act-2, 실측 기반) ────────────────────────────────────


def test_summarize_strips_args_block():
    """실측: MCP 설명은 Args: 블록을 포함한 여러 줄 docstring이다."""
    from src.infrastructure.tool_selection.prompts import summarize_description

    real = (
        "DOCX 문서를 HTML로 변환합니다.\n\n"
        "    Args:\n"
        '        source: {"kind": "path"|"url"|"base64", "value": "..."}\n'
        '        output: {"mode": "base64"|"path"}\n'
    )
    assert summarize_description(real) == "DOCX 문서를 HTML로 변환합니다."


def test_summarize_collapses_whitespace_into_one_line():
    from src.infrastructure.tool_selection.prompts import summarize_description

    assert "\n" not in summarize_description("첫 줄\n\n  둘째  줄\t셋째")


def test_summarize_truncates_long_text():
    from src.infrastructure.tool_selection.prompts import (
        MAX_DESCRIPTION_CHARS,
        summarize_description,
    )

    out = summarize_description("가" * 500)
    assert len(out) == MAX_DESCRIPTION_CHARS
    assert out.endswith("…")


def test_summarize_keeps_short_text_intact():
    from src.infrastructure.tool_selection.prompts import summarize_description

    assert summarize_description("엑셀로 저장합니다.") == "엑셀로 저장합니다."


def test_summarize_handles_empty():
    from src.infrastructure.tool_selection.prompts import summarize_description

    assert summarize_description("") == ""


def test_prompt_keeps_one_line_per_tool():
    """도구 1건 = 1줄 — 실측 docstring이 섞여도 형식이 깨지지 않는다."""
    from src.domain.tool_selection.schemas import ToolCandidate, ToolSource
    from src.infrastructure.tool_selection.prompts import build_user_prompt

    candidates = [
        ToolCandidate(
            tool_id="mcp:s:docx_to_html",
            name="docx_to_html",
            description=(
                "DOCX를 HTML로 변환합니다.\n\n    Args:\n        source: {...}\n"
            ),
            source=ToolSource.MCP,
        ),
        ToolCandidate(
            tool_id="internal:excel_export",
            name="excel_export",
            description="엑셀로 저장합니다.",
        ),
    ]

    body = build_user_prompt("질의", candidates).split("사용 가능한 도구:\n")[1]
    assert len(body.splitlines()) == len(candidates)
