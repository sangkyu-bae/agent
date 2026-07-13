"""SectionSummaryJobPolicy — 상태 전이·재시도·stale 판정·출력 방어 절단 (Design D4, D10).

domain 레이어 규칙 준수: 표준 라이브러리만 사용, 외부 의존 없음.
"""
from datetime import datetime

from src.domain.section_summary.entities import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_PROCESSING,
    SectionSummaryJob,
    SectionSummaryResult,
)

# processing→processing은 stale 재시도 재진입 허용 (D4)
_VALID_TRANSITIONS: dict[str, set[str]] = {
    JOB_STATUS_PENDING: {JOB_STATUS_PROCESSING, JOB_STATUS_FAILED},
    JOB_STATUS_PROCESSING: {
        JOB_STATUS_PROCESSING,
        JOB_STATUS_COMPLETED,
        JOB_STATUS_FAILED,
    },
    JOB_STATUS_FAILED: {JOB_STATUS_PROCESSING},
    JOB_STATUS_COMPLETED: set(),
}


class SectionSummaryJobPolicy:
    MAX_KEYWORDS = 10
    MAX_LINE_CHARS = 300
    SUMMARY_LINES = 3
    # 문서 요약 (document-summary-routing D9)
    DOC_SUMMARY_LINES = 5
    MAX_DOC_KEYWORDS = 15

    @staticmethod
    def validate_transition(current: str, new: str) -> None:
        allowed = _VALID_TRANSITIONS.get(current, set())
        if new not in allowed:
            raise ValueError(
                f"invalid job status transition: {current} -> {new}"
            )

    @classmethod
    def is_stale(
        cls, job: SectionSummaryJob, now: datetime, stale_seconds: int
    ) -> bool:
        """서버 재시작 등으로 고아화된 잡 판정 — 진행 갱신(updated_at) 경과 기준."""
        if job.status not in (JOB_STATUS_PENDING, JOB_STATUS_PROCESSING):
            return False
        if job.updated_at is None:
            return False
        return (now - job.updated_at).total_seconds() >= stale_seconds

    @classmethod
    def can_retry(
        cls, job: SectionSummaryJob, now: datetime, stale_seconds: int
    ) -> bool:
        if job.status == JOB_STATUS_FAILED:
            return True
        return cls.is_stale(job, now, stale_seconds)

    @classmethod
    def aggregate_keywords(
        cls, keyword_lists: list[list[str]], max_n: int | None = None
    ) -> list[str]:
        """문서 키워드 = 섹션 키워드 빈도 집계 — 내림차순·동률 등장순 (D9, LLM 0회)."""
        limit = max_n if max_n is not None else cls.MAX_DOC_KEYWORDS
        counts: dict[str, int] = {}
        order: dict[str, int] = {}
        for keywords in keyword_lists:
            for kw in keywords:
                word = kw.strip()
                if not word:
                    continue
                if word not in order:
                    order[word] = len(order)
                counts[word] = counts.get(word, 0) + 1
        ranked = sorted(counts, key=lambda w: (-counts[w], order[w]))
        return ranked[:limit]

    @classmethod
    def sanitize_document_output(cls, summary_lines: list[str]) -> list[str]:
        """문서 요약 방어 절단 — 5줄·라인 300자 (document-summary-routing D9)."""
        clean = [
            line.strip()[: cls.MAX_LINE_CHARS]
            for line in summary_lines
            if line and line.strip()
        ][: cls.DOC_SUMMARY_LINES]
        if not clean:
            raise ValueError("document summary output has no usable lines")
        return clean

    @classmethod
    def sanitize_output(
        cls, keywords: list[str], summary_lines: list[str]
    ) -> SectionSummaryResult:
        """LLM 출력 방어 절단 — 키워드 중복/공백 제거·상한, 라인 절단·3줄 상한 (NFR-08)."""
        clean_keywords: list[str] = []
        seen: set[str] = set()
        for kw in keywords:
            word = kw.strip()
            if word and word not in seen:
                seen.add(word)
                clean_keywords.append(word)
        clean_keywords = clean_keywords[: cls.MAX_KEYWORDS]

        clean_lines = [
            line.strip()[: cls.MAX_LINE_CHARS]
            for line in summary_lines
            if line and line.strip()
        ][: cls.SUMMARY_LINES]
        if not clean_lines:
            raise ValueError("summary output has no usable lines")
        return SectionSummaryResult(
            keywords=clean_keywords, summary_lines=clean_lines
        )
