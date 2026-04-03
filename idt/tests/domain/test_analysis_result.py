"""Tests for AnalysisResult and AnalysisAttempt."""

import pytest
from datetime import datetime

from src.domain.entities.analysis_result import AnalysisAttempt, AnalysisResult


class TestAnalysisAttempt:

    def test_create_attempt(self):
        now = datetime.utcnow()
        attempt = AnalysisAttempt(
            attempt_number=1,
            analysis_text="분석 결과",
            confidence_score=0.9,
            hallucination_score=0.1,
            used_web_search=False,
            timestamp=now,
        )
        assert attempt.attempt_number == 1
        assert attempt.analysis_text == "분석 결과"
        assert attempt.confidence_score == 0.9
        assert attempt.hallucination_score == 0.1
        assert attempt.used_web_search is False
        assert attempt.error is None

    def test_create_attempt_with_error(self):
        attempt = AnalysisAttempt(
            attempt_number=2,
            analysis_text="",
            confidence_score=0.0,
            hallucination_score=0.0,
            used_web_search=True,
            timestamp=datetime.utcnow(),
            error="LLM timeout",
        )
        assert attempt.error == "LLM timeout"


class TestAnalysisResult:

    def _make_attempt(
        self,
        number: int = 1,
        confidence: float = 0.9,
        hallucination: float = 0.1,
        web_search: bool = False,
    ) -> AnalysisAttempt:
        return AnalysisAttempt(
            attempt_number=number,
            analysis_text=f"분석 {number}",
            confidence_score=confidence,
            hallucination_score=hallucination,
            used_web_search=web_search,
            timestamp=datetime.utcnow(),
        )

    def test_create_result(self):
        attempt = self._make_attempt()
        result = AnalysisResult(
            request_id="req-1",
            user_query="데이터 요약",
            excel_summary={"rows": 100},
            final_answer="분석 결과",
            is_successful=True,
            attempts=[attempt],
        )
        assert result.request_id == "req-1"
        assert result.is_successful is True

    def test_total_attempts(self):
        attempts = [self._make_attempt(i) for i in range(1, 4)]
        result = AnalysisResult(
            request_id="req-2",
            user_query="분석",
            excel_summary={},
            final_answer="결과",
            is_successful=True,
            attempts=attempts,
        )
        assert result.total_attempts == 3

    def test_final_quality_score(self):
        attempt = self._make_attempt(confidence=0.85, hallucination=0.15)
        result = AnalysisResult(
            request_id="req-3",
            user_query="분석",
            excel_summary={},
            final_answer="결과",
            is_successful=True,
            attempts=[attempt],
        )
        assert result.final_quality_score == pytest.approx(0.7)

    def test_final_quality_score_no_attempts(self):
        result = AnalysisResult(
            request_id="req-4",
            user_query="분석",
            excel_summary={},
            final_answer="",
            is_successful=False,
            attempts=[],
        )
        assert result.final_quality_score == 0.0

    def test_created_at_auto_generated(self):
        result = AnalysisResult(
            request_id="req-5",
            user_query="분석",
            excel_summary={},
            final_answer="결과",
            is_successful=True,
            attempts=[self._make_attempt()],
        )
        assert result.created_at is not None
        assert isinstance(result.created_at, datetime)

    def test_optional_code_fields(self):
        result = AnalysisResult(
            request_id="req-6",
            user_query="분석",
            excel_summary={},
            final_answer="결과",
            is_successful=True,
            attempts=[self._make_attempt()],
            executed_code="print('hello')",
            code_output={"output": "hello"},
        )
        assert result.executed_code == "print('hello')"
        assert result.code_output == {"output": "hello"}
