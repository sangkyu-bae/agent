"""tool-recommender Design §8.2 — L1 유닛 테스트 (도메인 정책).

외부 의존 0. LLM·DB·langchain 없이 순수 함수만 검증한다.
"""
import pytest
from src.domain.tool_selection.policies import (
    DEFAULT_TOP_K,
    SelectionReason,
    build_cache_key,
    effective_description,
    is_low_signal,
    merge,
    needs_selection,
    sanitize,
    tokenize_name,
)
from src.domain.tool_selection.schemas import (
    SelectionResult,
    ToolCandidate,
    ToolSource,
)


def _mcp(tool_id: str, name: str, description: str = "", server: str | None = None):
    return ToolCandidate(
        tool_id=tool_id,
        name=name,
        description=description,
        source=ToolSource.MCP,
        server_name=server,
    )


# ── merge: required ∪ selected (Design §8.2 #1, #2) ─────────────────────────


def test_merge_unions_required_and_selected_in_candidate_order():
    order = ("a", "b", "c", "d")
    assert merge(("c",), ("a", "d"), order) == ("a", "c", "d")


def test_merge_deduplicates_overlap():
    order = ("a", "b", "c")
    assert merge(("a", "b"), ("b", "c"), order) == ("a", "b", "c")


def test_merge_keeps_required_not_present_in_candidates():
    """required는 후보에 없어도 결과에 반드시 포함된다 (Port 계약)."""
    order = ("a", "b")
    assert merge(("zzz",), ("a",), order) == ("a", "zzz")


def test_merge_appends_missing_required_after_ordered_candidates():
    order = ("a", "b", "c")
    assert merge(("x", "y"), ("c", "a"), order) == ("a", "c", "x", "y")


def test_merge_with_empty_selection_returns_required_only():
    assert merge(("a",), (), ("a", "b", "c")) == ("a",)


def test_merge_is_deterministic_across_input_permutations():
    order = ("a", "b", "c", "d")
    first = merge(("d", "a"), ("c", "b"), order)
    second = merge(("a", "d"), ("b", "c"), order)
    assert first == second == ("a", "b", "c", "d")


# ── sanitize: 화이트리스트 대조 (Design §8.2 #3) ─────────────────────────────


def test_sanitize_drops_unknown_ids():
    kept, dropped = sanitize(["a", "ghost1", "b", "ghost2", "ghost3"], ("a", "b"))
    assert kept == ("a", "b")
    assert dropped == ("ghost1", "ghost2", "ghost3")


def test_sanitize_returns_empty_dropped_when_all_known():
    kept, dropped = sanitize(["b", "a"], ("a", "b"))
    assert kept == ("b", "a")
    assert dropped == ()


def test_sanitize_deduplicates_repeated_ids():
    kept, dropped = sanitize(["a", "a", "a"], ("a",))
    assert kept == ("a",)
    assert dropped == ()


def test_sanitize_ignores_whitespace_and_blank_entries():
    kept, dropped = sanitize([" a ", "", "   "], ("a",))
    assert kept == ("a",)
    assert dropped == ()


def test_sanitize_drops_non_string_entries():
    kept, dropped = sanitize(["a", 42, None], ("a",))
    assert kept == ("a",)
    assert dropped == ("42", "None")


# ── needs_selection: 조기 반환 (Design §8.2 #4, FR-08) ───────────────────────


@pytest.mark.parametrize(
    ("count", "top_k", "expected"),
    [(5, 8, False), (8, 8, False), (9, 8, True), (0, 8, False), (40, 8, True)],
)
def test_needs_selection_threshold(count, top_k, expected):
    assert needs_selection(count, top_k) is expected


def test_default_top_k_is_eight():
    assert DEFAULT_TOP_K == 8


# ── 저신호 설명 판별 (Design §8.2 #5, #6) ────────────────────────────────────


def test_is_low_signal_detects_mcp_stub_description():
    assert is_low_signal("MCP tool: search_blog", "search_blog") is True


def test_is_low_signal_false_for_real_description():
    assert is_low_signal("네이버 블로그를 검색합니다.", "search_blog") is False


def test_is_low_signal_true_for_blank():
    assert is_low_signal("", "search_blog") is True
    assert is_low_signal("   ", "search_blog") is True


def test_is_low_signal_detects_stub_when_adapter_name_is_server_prefixed():
    """실제 데이터 형태 — 스텁 꼬리는 원본 도구명, 어댑터 name은 서버명 접두.

    tool_registry.py:83-90 이 name은 sanitize(f"{server}_{tool}")로, description은
    f"MCP tool: {tool}"로 만든다. 둘이 다르므로 name 대조만으로는 못 잡는다.
    """
    assert is_low_signal("MCP tool: search_blog", "naver_mcp_search_blog") is True


def test_is_low_signal_false_when_stub_prefix_has_extra_content():
    """접두어로 시작해도 실제 설명이 이어지면 스텁이 아니다."""
    assert is_low_signal(
        "MCP tool: search_blog 을 이용해 블로그를 검색합니다.", "search_blog"
    ) is False


# ── 이름 토큰화 (Design §8.2 #7, §3.3) ───────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("search_blog_posts", "search blog posts"),
        ("search-blog", "search blog"),
        ("naver.search", "naver search"),
        ("a/b:c", "a b c"),
        ("__leading__", "leading"),
        ("single", "single"),
        ("", ""),
    ],
)
def test_tokenize_name(name, expected):
    assert tokenize_name(name) == expected


# ── effective_description (Design §8.2 #8) ──────────────────────────────────


def test_effective_description_enriches_stub_with_server_name():
    c = _mcp("mcp:s1:search_blog", "search_blog", "MCP tool: search_blog", "naver_mcp")
    assert effective_description(c) == "naver_mcp 서버의 'search blog' 기능"


def test_effective_description_enriches_stub_without_server_name():
    c = _mcp("mcp:s1:search_blog", "search_blog", "MCP tool: search_blog")
    assert effective_description(c) == "'search blog' 기능"


def test_effective_description_preserves_real_description():
    c = _mcp("mcp:s1:x", "x", "네이버 블로그 검색", "naver_mcp")
    assert effective_description(c) == "네이버 블로그 검색"


def test_effective_description_enriches_blank_internal_tool():
    c = ToolCandidate(
        tool_id="internal:excel_export",
        name="excel_export",
        description="",
        source=ToolSource.INTERNAL,
    )
    assert effective_description(c) == "'excel export' 기능"


# ── 캐시 키 (Design §4.2) ────────────────────────────────────────────────────


def test_cache_key_is_stable_for_same_inputs():
    assert build_cache_key("질의", ("b", "a")) == build_cache_key("질의", ("b", "a"))


def test_cache_key_ignores_candidate_order():
    """후보 집합이 같으면 순서가 달라도 같은 키."""
    assert build_cache_key("질의", ("a", "b")) == build_cache_key("질의", ("b", "a"))


def test_cache_key_changes_when_candidate_set_changes():
    """후보가 추가·제거되면 자동 무효화된다."""
    assert build_cache_key("질의", ("a", "b")) != build_cache_key("질의", ("a",))


def test_cache_key_changes_with_query():
    assert build_cache_key("질의1", ("a",)) != build_cache_key("질의2", ("a",))


# ── SelectionResult VO (Design §8.2 #9) ─────────────────────────────────────


def test_selection_result_is_frozen():
    r = SelectionResult(
        selected_ids=("a",), required_ids=(), final_ids=("a",), candidate_count=1
    )
    with pytest.raises(Exception):
        r.final_ids = ("b",)  # type: ignore[misc]


def test_selection_result_defaults_are_success_shaped():
    r = SelectionResult(
        selected_ids=("a",), required_ids=(), final_ids=("a",), candidate_count=1
    )
    assert r.fallback is False
    assert r.reason is None
    assert r.dropped_ids == ()
    assert r.elapsed_ms == 0


def test_selection_reason_constants_exist():
    """§6.1 실패 모드 표의 reason 값이 상수로 존재한다."""
    assert SelectionReason.UNDER_THRESHOLD == "under_threshold"
    assert SelectionReason.NO_CANDIDATES == "no_candidates"
    assert SelectionReason.LLM_ERROR == "llm_error"
    assert SelectionReason.LLM_TIMEOUT == "llm_timeout"
    assert SelectionReason.PARSE_ERROR == "parse_error"
    assert SelectionReason.SANITIZED == "sanitized"
    assert SelectionReason.EMPTY_SELECTION == "empty_selection"
