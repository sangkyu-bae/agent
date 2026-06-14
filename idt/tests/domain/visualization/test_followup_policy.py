"""ChartFollowupPolicy 테스트 (chart-context-continuity Design §3.3).

보수적 판정: 애매하면 NONE → 일반 경로 (오분류 안전망은 application 가드가 추가 담당).
"""
import pytest

from src.domain.visualization.followup_policy import (
    ChartFollowupDecision,
    ChartFollowupPolicy,
)


@pytest.fixture
def policy() -> ChartFollowupPolicy:
    return ChartFollowupPolicy()


class TestEditDecision:
    @pytest.mark.parametrize("question", [
        "해당 그래프에서 각 사용자마다 색깔을 넣어줘",
        "그 차트를 원으로 변경해줘",
        "그래프를 파이로 바꿔줘",
        "위 도표 색상 수정해줘",
        "방금 그래프에서 시리즈를 나눠줘",
        "차트에 평균선 추가해줘",
    ])
    def test_edit_requests(self, policy: ChartFollowupPolicy, question: str) -> None:
        assert policy.decide(question) == ChartFollowupDecision.EDIT


class TestNoneDecision:
    @pytest.mark.parametrize("question", [
        "부서별 대출 건수 그래프 그려줘",       # 신규 생성 → 기존 빌더 경로
        "이 문서 요약해줘",                     # 차트 무관
        "오늘 날씨 어때?",
        "매출 추이를 시각화해줘",               # 신규 생성
        "",
    ])
    def test_non_edit_requests(self, policy: ChartFollowupPolicy, question: str) -> None:
        assert policy.decide(question) == ChartFollowupDecision.NONE

    def test_none_question_is_none_decision(self, policy: ChartFollowupPolicy) -> None:
        assert policy.decide(None) == ChartFollowupDecision.NONE  # type: ignore[arg-type]


class TestEnglishMixed:
    def test_english_chart_noun_with_edit_verb(self, policy: ChartFollowupPolicy) -> None:
        assert policy.decide("chart 색깔 바꿔줘") == ChartFollowupDecision.EDIT
