"""SessionScopedExtractionJobStore — 추출 잡 영속화 (V088).

Design Ref: graph-rag-foundation §10.1 — 앱 수명 싱글턴. 호출마다 독립 짧은
세션·트랜잭션을 연다(SessionScopedSectionSummaryJobStore 선례). LLM·Neo4j 호출은
이 저장소 밖(트랜잭션 밖)에서 일어난다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from src.domain.graph_rag.extraction import (
    ACTIVE_JOB_STATUSES,
    ExtractionJob,
    JobCounters,
    JobMode,
    JobStatus,
    TriggerSource,
)
from src.domain.graph_rag.interfaces import ExtractionJobStorePort
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.graph_rag.models import GraphExtractionJobModel as JobModel

_INTERRUPTED = "interrupted"
_ACTIVE = [s.value for s in ACTIVE_JOB_STATUSES]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _counter_values(c: JobCounters) -> dict[str, int]:
    return {
        "processed_chunks": c.processed_chunks,
        "failed_chunks": c.failed_chunks,
        "llm_calls": c.llm_calls,
        "judge_calls": c.judge_calls,
        "entities_created": c.entities_created,
        "entities_linked": c.entities_linked,
        "relations_created": c.relations_created,
    }


def _to_domain(m: JobModel) -> ExtractionJob:
    return ExtractionJob(
        id=m.id,
        document_id=m.document_id,
        kb_id=m.kb_id,
        collection_name=m.collection_name,
        status=JobStatus(m.status),
        mode=JobMode(m.mode),
        trigger_source=TriggerSource(m.trigger_source),
        extractor_version=m.extractor_version,
        total_chunks=m.total_chunks,
        processed_chunks=m.processed_chunks,
        failed_chunks=m.failed_chunks,
        llm_calls=m.llm_calls,
        judge_calls=m.judge_calls,
        entities_created=m.entities_created,
        entities_linked=m.entities_linked,
        relations_created=m.relations_created,
        error_message=m.error_message,
        requested_by=m.requested_by,
        started_at=m.started_at,
        finished_at=m.finished_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SessionScopedExtractionJobStore(ExtractionJobStorePort):
    def __init__(self, session_factory: Callable[[], Any], logger: LoggerInterface):
        self._session_factory = session_factory
        self._logger = logger

    async def _update(self, job_id: str, **values: Any) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(JobModel)
                .where(JobModel.id == job_id)
                .values(updated_at=_now(), **values)
            )

    async def create(self, job: ExtractionJob, request_id: str) -> ExtractionJob:
        now = _now()
        async with self._session_factory() as session, session.begin():
            session.add(
                JobModel(
                    id=job.id,
                    document_id=job.document_id,
                    kb_id=job.kb_id,
                    collection_name=job.collection_name,
                    status=job.status.value,
                    mode=job.mode.value,
                    trigger_source=job.trigger_source.value,
                    extractor_version=job.extractor_version,
                    requested_by=job.requested_by,
                    created_at=now,
                    updated_at=now,
                )
            )
        self._logger.info(
            "graph extraction job created",
            request_id=request_id,
            job_id=job.id,
            document_id=job.document_id,
            mode=job.mode.value,
            trigger=job.trigger_source.value,
        )
        return await self.get(job.id, request_id)  # type: ignore[return-value]

    async def get(self, job_id: str, request_id: str) -> ExtractionJob | None:
        async with self._session_factory() as session:
            row = await session.get(JobModel, job_id)
            return _to_domain(row) if row else None

    async def find_active(
        self, document_id: str, request_id: str
    ) -> ExtractionJob | None:
        stmt = (
            select(JobModel)
            .where(JobModel.document_id == document_id, JobModel.status.in_(_ACTIVE))
            .order_by(JobModel.created_at.desc())
            .limit(1)
        )
        async with self._session_factory() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _to_domain(row) if row else None

    async def latest_by_documents(
        self, document_ids: list[str], request_id: str
    ) -> dict[str, ExtractionJob]:
        if not document_ids:
            return {}
        stmt = (
            select(JobModel)
            .where(JobModel.document_id.in_(document_ids))
            .order_by(JobModel.created_at.asc(), JobModel.id.asc())
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()
        latest: dict[str, ExtractionJob] = {}
        for row in rows:  # 오름차순이라 마지막 값이 최신
            latest[row.document_id] = _to_domain(row)
        return latest

    async def mark_processing(
        self, job_id: str, total_chunks: int, request_id: str
    ) -> None:
        await self._update(
            job_id,
            status=JobStatus.PROCESSING.value,
            total_chunks=total_chunks,
            started_at=_now(),
        )

    async def save_progress(
        self, job_id: str, counters: JobCounters, request_id: str
    ) -> None:
        await self._update(job_id, **_counter_values(counters))

    async def finish(
        self,
        job_id: str,
        status: JobStatus,
        counters: JobCounters,
        error: str | None,
        request_id: str,
    ) -> None:
        await self._update(
            job_id,
            status=status.value,
            error_message=error,
            finished_at=_now(),
            **_counter_values(counters),
        )
        self._logger.info(
            "graph extraction job finished",
            request_id=request_id,
            job_id=job_id,
            status=status.value,
            processed=counters.processed_chunks,
            failed=counters.failed_chunks,
            llm_calls=counters.llm_calls,
        )

    async def fail_interrupted(self, request_id: str) -> int:
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(JobModel)
                .where(JobModel.status.in_(_ACTIVE))
                .values(
                    status=JobStatus.FAILED.value,
                    error_message=_INTERRUPTED,
                    finished_at=_now(),
                    updated_at=_now(),
                )
            )
        changed = int(result.rowcount or 0)
        if changed:
            self._logger.warning(
                "graph extraction jobs marked interrupted",
                request_id=request_id,
                count=changed,
            )
        return changed
