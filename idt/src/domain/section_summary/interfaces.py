"""SectionSummary 도메인 인터페이스 (card-section-summary Design §3).

구현체는 infrastructure에 두고 application이 이 추상에 의존한다.
JobStore는 세션 관리를 캡슐화한다(호출마다 독립 짧은 세션, DB-001) —
장수명 러너/런처가 per-request 세션에 의존하지 않게 하는 경계.
"""
from abc import ABC, abstractmethod

from src.domain.section_summary.entities import (
    SectionCard,
    SectionSummaryJob,
    SectionSummaryRecord,
    SectionSummaryResult,
)


class SectionSummaryJobStoreInterface(ABC):
    """잡 영속화 — 각 메서드가 자체 단기 세션/트랜잭션으로 완결된다."""

    @abstractmethod
    async def create(
        self, job: SectionSummaryJob, request_id: str
    ) -> SectionSummaryJob: ...

    @abstractmethod
    async def find_by_id(
        self, job_id: str, request_id: str
    ) -> SectionSummaryJob | None: ...

    @abstractmethod
    async def find_by_document(
        self, document_id: str, request_id: str
    ) -> SectionSummaryJob | None: ...

    @abstractmethod
    async def update_status(
        self,
        job_id: str,
        status: str,
        error: str | None,
        request_id: str,
    ) -> None: ...

    @abstractmethod
    async def start_progress(
        self, job_id: str, total: int, done: int, request_id: str
    ) -> None:
        """러너 시작 시 total 확정 + done(기완료분)/failed(0) 리셋 (D3, 재시도 멱등)."""

    @abstractmethod
    async def increment_progress(
        self, job_id: str, done_delta: int, failed_delta: int, request_id: str
    ) -> None:
        """섹션 완료마다 카운트 증가 — updated_at 갱신이 heartbeat 역할 (D12)."""


class DocumentSummaryStepInterface(ABC):
    """섹션 요약 완료 후 문서 요약 생성·저장 단계 (document-summary-routing D2).

    실패는 raise로 전파 — 러너가 잡을 failed("document summary failed: ...")로
    마감한다. 섹션 요약이 0건이면 스킵(정상 반환, D5).
    """

    @abstractmethod
    async def run(self, job: SectionSummaryJob, request_id: str) -> None: ...


class SectionSourceInterface(ABC):
    """카드 섹션 소스 추상화 (D1) — v1은 Qdrant parent 청크."""

    @abstractmethod
    async def list_sections(
        self, collection_name: str, document_id: str, request_id: str
    ) -> list[SectionCard]: ...

    @abstractmethod
    async def list_done_refs(
        self, collection_name: str, document_id: str, request_id: str
    ) -> set[str]:
        """이미 요약 point가 존재하는 section_ref 집합 (재시도 멱등, D6)."""


class SectionSummarizerInterface(ABC):
    """섹션 1건 → 키워드+3줄 요약 (D10)."""

    @abstractmethod
    async def summarize(
        self, card: SectionCard, request_id: str
    ) -> SectionSummaryResult: ...


class SummaryWriterInterface(ABC):
    """요약 1건 저장 — ES 먼저, Qdrant 마지막(완료 마커) (D5/D6/D7)."""

    @abstractmethod
    async def write(
        self, record: SectionSummaryRecord, request_id: str
    ) -> None: ...
