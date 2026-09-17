"""EmptyResultPolicy 단위 테스트.

Design Ref: supervisor-early-finish-fix §3.2 / §8.2 (L1 #1~6)
Plan SC: FR-02, FR-03

'도구는 성공했는데 유효 데이터가 없다'를 결정적으로 탐지한다.
그 다음 행동(다른 워커를 부를지)은 supervisor LLM이 판단한다 — 그래프 계약 ③.
"""
import pytest

from src.domain.agent_builder.policies import EmptyResultPolicy

PATTERNS = ("등록된 데이터가 없습니다", "검색 결과가 없습니다")

# 재현 케이스(트레이스 01a0a82b): 네비게이션 메뉴 때문에 본문은 길지만
# 데이터 영역만 비어 있다 — 구조적 신호로는 잡히지 않고 패턴으로만 잡힌다.
_LONG_NAV_BODY = (
    "현재금리(26년~) | 정기예금 | 상품공시 | 소비자포털\n"
    + ("상품공시 경영공시 소비자공시 소비자정보 금융조회서비스 자료실\n" * 40)
    + "평균금리 6개월 0.00% 12개월 0.00% 24개월 0.00%\n"
    "정기예금 상품별 금리현황표\n"
    "상세 등록된 데이터가 없습니다.\n"
)


class TestStructuralSignal:
    """1차 — 산출 자체가 비었거나 지나치게 짧다."""

    def test_empty_string_is_empty_result(self):
        assert EmptyResultPolicy.detect("", PATTERNS) != ""

    def test_whitespace_only_is_empty_result(self):
        assert EmptyResultPolicy.detect("   \n\t  ", PATTERNS) != ""

    def test_body_shorter_than_min_is_empty_result(self):
        short = "가" * (EmptyResultPolicy.MIN_BODY_CHARS - 1)
        assert EmptyResultPolicy.detect(short, PATTERNS) != ""

    def test_body_at_min_length_is_not_empty_by_structure(self):
        body = "가" * EmptyResultPolicy.MIN_BODY_CHARS
        assert EmptyResultPolicy.detect(body, PATTERNS) == ""


class TestPatternSignal:
    """2차 — 본문은 충분히 길지만 데이터 영역이 비었다는 문구가 있다."""

    def test_long_body_with_pattern_is_empty_result(self):
        """재현 케이스 — 구조적으로는 정상, 패턴으로만 탐지된다."""
        assert len(_LONG_NAV_BODY) > EmptyResultPolicy.MIN_BODY_CHARS
        assert EmptyResultPolicy.detect(_LONG_NAV_BODY, PATTERNS) != ""

    def test_long_body_without_pattern_is_normal(self):
        body = "저축은행A 12개월 3.50%\n" * 50
        assert EmptyResultPolicy.detect(body, PATTERNS) == ""

    def test_empty_pattern_tuple_falls_back_to_structural_only(self):
        """설정 누락이 런을 깨뜨리지 않는다 — 구조적 신호만 동작."""
        assert EmptyResultPolicy.detect(_LONG_NAV_BODY, ()) == ""
        assert EmptyResultPolicy.detect("", ()) != ""

    @pytest.mark.parametrize("patterns", [None, ()])
    def test_none_or_empty_patterns_are_safe(self, patterns):
        assert EmptyResultPolicy.detect("a" * 500, patterns) == ""


class TestSummaryContract:

    def test_summary_within_max_chars(self):
        assert len(EmptyResultPolicy.detect("", PATTERNS)) <= (
            EmptyResultPolicy.MAX_SUMMARY_CHARS
        )
        assert len(EmptyResultPolicy.detect(_LONG_NAV_BODY, PATTERNS)) <= (
            EmptyResultPolicy.MAX_SUMMARY_CHARS
        )

    def test_summary_is_policy_authored_not_raw_content(self):
        """§7 보안 — 수집 원문이 지시문 위치로 승격되지 않는다."""
        summary = EmptyResultPolicy.detect(_LONG_NAV_BODY, PATTERNS)
        assert "정기예금 상품별 금리현황표" not in summary

    def test_non_string_body_is_not_empty_result(self):
        """§6.1 — 멀티모달 content 등은 판정 생략(기존 경로를 깨지 않는다)."""
        assert EmptyResultPolicy.detect(None, PATTERNS) == ""
        assert EmptyResultPolicy.detect([{"type": "text"}], PATTERNS) == ""
