"""SectionSummaryJobPolicy 단위 테스트 (card-section-summary Design D4, D10)."""
from datetime import datetime, timedelta

import pytest

from src.domain.section_summary.entities import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_PROCESSING,
    SectionSummaryJob,
)
from src.domain.section_summary.policy import SectionSummaryJobPolicy

STALE_SECONDS = 600


def _job(status: str, updated_ago_seconds: int = 0) -> SectionSummaryJob:
    now = datetime.now()
    return SectionSummaryJob(
        id="job-1",
        document_id="doc-1",
        kb_id="kb-1",
        collection_name="col",
        chunking_profile_id="prof-1",
        llm_model_id="model-1",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        status=status,
        updated_at=now - timedelta(seconds=updated_ago_seconds),
    )


class TestValidateTransition:
    @pytest.mark.parametrize(
        "current,new",
        [
            (JOB_STATUS_PENDING, JOB_STATUS_PROCESSING),
            (JOB_STATUS_PENDING, JOB_STATUS_FAILED),
            (JOB_STATUS_PROCESSING, JOB_STATUS_COMPLETED),
            (JOB_STATUS_PROCESSING, JOB_STATUS_FAILED),
            (JOB_STATUS_PROCESSING, JOB_STATUS_PROCESSING),
            (JOB_STATUS_FAILED, JOB_STATUS_PROCESSING),
        ],
    )
    def test_allowed(self, current, new):
        SectionSummaryJobPolicy.validate_transition(current, new)

    @pytest.mark.parametrize(
        "current,new",
        [
            (JOB_STATUS_COMPLETED, JOB_STATUS_PROCESSING),
            (JOB_STATUS_COMPLETED, JOB_STATUS_FAILED),
            (JOB_STATUS_PENDING, JOB_STATUS_COMPLETED),
            (JOB_STATUS_FAILED, JOB_STATUS_COMPLETED),
        ],
    )
    def test_rejected(self, current, new):
        with pytest.raises(ValueError):
            SectionSummaryJobPolicy.validate_transition(current, new)


class TestCanRetry:
    def test_failed_is_retryable(self):
        assert SectionSummaryJobPolicy.can_retry(
            _job(JOB_STATUS_FAILED), datetime.now(), STALE_SECONDS
        )

    def test_completed_is_not_retryable(self):
        assert not SectionSummaryJobPolicy.can_retry(
            _job(JOB_STATUS_COMPLETED), datetime.now(), STALE_SECONDS
        )

    def test_fresh_processing_is_not_retryable(self):
        assert not SectionSummaryJobPolicy.can_retry(
            _job(JOB_STATUS_PROCESSING, updated_ago_seconds=10),
            datetime.now(),
            STALE_SECONDS,
        )

    def test_stale_processing_is_retryable(self):
        assert SectionSummaryJobPolicy.can_retry(
            _job(JOB_STATUS_PROCESSING, updated_ago_seconds=STALE_SECONDS + 1),
            datetime.now(),
            STALE_SECONDS,
        )

    def test_stale_pending_is_retryable(self):
        assert SectionSummaryJobPolicy.can_retry(
            _job(JOB_STATUS_PENDING, updated_ago_seconds=STALE_SECONDS + 1),
            datetime.now(),
            STALE_SECONDS,
        )


class TestIsStale:
    def test_processing_past_threshold(self):
        assert SectionSummaryJobPolicy.is_stale(
            _job(JOB_STATUS_PROCESSING, updated_ago_seconds=STALE_SECONDS + 1),
            datetime.now(),
            STALE_SECONDS,
        )

    def test_completed_never_stale(self):
        assert not SectionSummaryJobPolicy.is_stale(
            _job(JOB_STATUS_COMPLETED, updated_ago_seconds=STALE_SECONDS * 2),
            datetime.now(),
            STALE_SECONDS,
        )

    def test_missing_updated_at_not_stale(self):
        job = _job(JOB_STATUS_PROCESSING)
        job.updated_at = None
        assert not SectionSummaryJobPolicy.is_stale(
            job, datetime.now(), STALE_SECONDS
        )


class TestAggregateKeywords:
    """문서 키워드 = 섹션 키워드 빈도 집계 (document-summary-routing D9, LLM 0회)."""

    def test_frequency_descending(self):
        result = SectionSummaryJobPolicy.aggregate_keywords(
            [["대출", "금리"], ["대출", "한도"], ["대출"]]
        )
        assert result[0] == "대출"

    def test_tie_broken_by_first_appearance(self):
        result = SectionSummaryJobPolicy.aggregate_keywords(
            [["금리", "한도"], ["한도", "금리"]]
        )
        assert result == ["금리", "한도"]

    def test_blank_keywords_dropped_and_capped(self):
        lists = [["", "  "]] + [[f"kw{i}"] for i in range(20)]
        result = SectionSummaryJobPolicy.aggregate_keywords(lists)
        assert len(result) == SectionSummaryJobPolicy.MAX_DOC_KEYWORDS
        assert "" not in result

    def test_empty_input_returns_empty(self):
        assert SectionSummaryJobPolicy.aggregate_keywords([]) == []


class TestSanitizeDocumentOutput:
    """문서 요약 방어 절단 — 5줄·라인 300자 (document-summary-routing D9)."""

    def test_capped_to_five_lines(self):
        lines = [f"line {i}" for i in range(8)]
        result = SectionSummaryJobPolicy.sanitize_document_output(lines)
        assert len(result) == SectionSummaryJobPolicy.DOC_SUMMARY_LINES

    def test_long_line_truncated(self):
        result = SectionSummaryJobPolicy.sanitize_document_output(["가" * 500])
        assert len(result[0]) == SectionSummaryJobPolicy.MAX_LINE_CHARS

    def test_fewer_lines_kept(self):
        assert SectionSummaryJobPolicy.sanitize_document_output(
            ["한 줄", "", "  "]
        ) == ["한 줄"]

    def test_no_usable_lines_raises(self):
        with pytest.raises(ValueError):
            SectionSummaryJobPolicy.sanitize_document_output(["", "  "])


class TestSanitizeOutput:
    def test_keywords_deduped_stripped_capped(self):
        keywords = [" 대출 ", "대출", "", "  "] + [f"kw{i}" for i in range(15)]
        result = SectionSummaryJobPolicy.sanitize_output(
            keywords, ["첫째 줄", "둘째 줄", "셋째 줄"]
        )
        assert result.keywords[0] == "대출"
        assert len(result.keywords) == SectionSummaryJobPolicy.MAX_KEYWORDS
        assert "" not in result.keywords

    def test_summary_lines_truncated_and_capped_to_three(self):
        long_line = "가" * 500
        result = SectionSummaryJobPolicy.sanitize_output(
            ["kw"], [long_line, "b", "c", "d"]
        )
        assert len(result.summary_lines) == 3
        assert len(result.summary_lines[0]) == SectionSummaryJobPolicy.MAX_LINE_CHARS

    def test_fewer_lines_are_kept(self):
        result = SectionSummaryJobPolicy.sanitize_output(["kw"], ["한 줄만"])
        assert result.summary_lines == ["한 줄만"]
        assert result.summary_text == "한 줄만"

    def test_no_usable_lines_raises(self):
        with pytest.raises(ValueError):
            SectionSummaryJobPolicy.sanitize_output(["kw"], ["", "  "])

    def test_summary_text_joins_lines(self):
        result = SectionSummaryJobPolicy.sanitize_output(
            ["kw"], ["a", "b", "c"]
        )
        assert result.summary_text == "a\nb\nc"
