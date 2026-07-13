"""SectionSummaryJob 영속화 (card-section-summary Design §4.2, D3/D12).

- SectionSummaryJobRepository: 세션 주입 저층 레포 (per-request 조회용).
- SessionScopedSectionSummaryJobStore: session_factory 기반 싱글턴 어댑터 —
  호출마다 독립 짧은 세션/트랜잭션(DB-001). 장수명 러너/런처가 사용한다.
  (SessionScopedLlmModelRepository 선례)
"""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.section_summary.entities import SectionSummaryJob
from src.domain.section_summary.interfaces import (
    SectionSummaryJobStoreInterface,
)
from src.infrastructure.persistence.models.section_summary_job import (
    SectionSummaryJobModel,
)


class SectionSummaryJobRepository:
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(
        self, job: SectionSummaryJob, request_id: str
    ) -> SectionSummaryJob:
        model = SectionSummaryJobModel(
            id=job.id,
            document_id=job.document_id,
            kb_id=job.kb_id,
            collection_name=job.collection_name,
            chunking_profile_id=job.chunking_profile_id,
            llm_model_id=job.llm_model_id,
            embedding_provider=job.embedding_provider,
            embedding_model=job.embedding_model,
            status=job.status,
            total_sections=job.total_sections,
            done_sections=job.done_sections,
            failed_sections=job.failed_sections,
            error=job.error,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def find_by_id(
        self, job_id: str, request_id: str
    ) -> SectionSummaryJob | None:
        stmt = select(SectionSummaryJobModel).where(
            SectionSummaryJobModel.id == job_id
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_by_document(
        self, document_id: str, request_id: str
    ) -> SectionSummaryJob | None:
        stmt = select(SectionSummaryJobModel).where(
            SectionSummaryJobModel.document_id == document_id
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model else None

    async def update_status(
        self, job_id: str, status: str, error: str | None, request_id: str
    ) -> None:
        stmt = (
            update(SectionSummaryJobModel)
            .where(SectionSummaryJobModel.id == job_id)
            .values(status=status, error=error)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def start_progress(
        self, job_id: str, total: int, done: int, request_id: str
    ) -> None:
        stmt = (
            update(SectionSummaryJobModel)
            .where(SectionSummaryJobModel.id == job_id)
            .values(total_sections=total, done_sections=done, failed_sections=0)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def increment_progress(
        self, job_id: str, done_delta: int, failed_delta: int, request_id: str
    ) -> None:
        stmt = (
            update(SectionSummaryJobModel)
            .where(SectionSummaryJobModel.id == job_id)
            .values(
                done_sections=SectionSummaryJobModel.done_sections + done_delta,
                failed_sections=(
                    SectionSummaryJobModel.failed_sections + failed_delta
                ),
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    @staticmethod
    def _to_domain(model: SectionSummaryJobModel) -> SectionSummaryJob:
        return SectionSummaryJob(
            id=model.id,
            document_id=model.document_id,
            kb_id=model.kb_id,
            collection_name=model.collection_name,
            chunking_profile_id=model.chunking_profile_id,
            llm_model_id=model.llm_model_id,
            embedding_provider=model.embedding_provider,
            embedding_model=model.embedding_model,
            status=model.status,
            total_sections=model.total_sections,
            done_sections=model.done_sections,
            failed_sections=model.failed_sections,
            error=model.error,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class SessionScopedSectionSummaryJobStore(SectionSummaryJobStoreInterface):
    """싱글턴 잡 스토어 — 매 호출 새 세션·짧은 트랜잭션 (D11/D12)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def create(
        self, job: SectionSummaryJob, request_id: str
    ) -> SectionSummaryJob:
        async with self._session_factory() as session:
            async with session.begin():
                return await SectionSummaryJobRepository(
                    session, self._logger
                ).save(job, request_id)

    async def find_by_id(
        self, job_id: str, request_id: str
    ) -> SectionSummaryJob | None:
        async with self._session_factory() as session:
            return await SectionSummaryJobRepository(
                session, self._logger
            ).find_by_id(job_id, request_id)

    async def find_by_document(
        self, document_id: str, request_id: str
    ) -> SectionSummaryJob | None:
        async with self._session_factory() as session:
            return await SectionSummaryJobRepository(
                session, self._logger
            ).find_by_document(document_id, request_id)

    async def update_status(
        self, job_id: str, status: str, error: str | None, request_id: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await SectionSummaryJobRepository(
                    session, self._logger
                ).update_status(job_id, status, error, request_id)

    async def start_progress(
        self, job_id: str, total: int, done: int, request_id: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await SectionSummaryJobRepository(
                    session, self._logger
                ).start_progress(job_id, total, done, request_id)

    async def increment_progress(
        self, job_id: str, done_delta: int, failed_delta: int, request_id: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await SectionSummaryJobRepository(
                    session, self._logger
                ).increment_progress(
                    job_id, done_delta, failed_delta, request_id
                )
