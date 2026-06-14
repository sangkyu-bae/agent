"""ANALYSIS_OUTPUT_GUIDE 공용 프롬프트 가이드 회귀 테스트.

분석 노드 프롬프트가 약화(원래 2줄)로 회귀하지 않도록 핵심 제약 문구를 고정한다.
"""
from src.application.visualization.analysis_prompt import ANALYSIS_OUTPUT_GUIDE


class TestAnalysisOutputGuide:
    def test_natural_language_only(self) -> None:
        assert "자연어" in ANALYSIS_OUTPUT_GUIDE

    def test_forbids_output(self) -> None:
        assert "절대 출력 금지" in ANALYSIS_OUTPUT_GUIDE
        assert "JSON" in ANALYSIS_OUTPUT_GUIDE
        assert "코드블록" in ANALYSIS_OUTPUT_GUIDE

    def test_no_direct_chart(self) -> None:
        assert "차트를 직접 만들지 않는다" in ANALYSIS_OUTPUT_GUIDE

    def test_numbers_as_text(self) -> None:
        assert "항목별 수치를 자연어로 나열" in ANALYSIS_OUTPUT_GUIDE

    def test_no_meta_exposure(self) -> None:
        """결정 4: 파이프라인/다음 단계 같은 메타 설명을 답변에 노출 금지."""
        assert "메타 설명" in ANALYSIS_OUTPUT_GUIDE

    def test_scope_limited(self) -> None:
        assert "요청한 범위만" in ANALYSIS_OUTPUT_GUIDE
