"""DocumentGenerationTypeRepository: document_generation_type MySQL CRUD.

DB-001 §10.3 준수 — commit/rollback은 세션 관리자(get_session) 책임.
SessionScoped 어댑터는 WorkflowCompiler(앱 싱글톤)의 생성 노드가 런타임에
유형을 읽을 때 사용 (SessionScopedDocumentTemplateRepository 패턴).
"""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.document_generator.interfaces import (
    DocumentGenerationTypeRepositoryInterface,
)
from src.domain.document_generator.schemas import (
    GENERATION_TYPE_STATUS_ACTIVE,
    GENERATION_TYPE_STATUS_DELETED,
    DocumentGenerationType,
    DocumentSection,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.document_generator.models import DocumentGenerationTypeModel


class DocumentGenerationTypeRepository(DocumentGenerationTypeRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(
        self, gen_type: DocumentGenerationType, request_id: str
    ) -> DocumentGenerationType:
        self._logger.info(
            "DocumentGenerationType save",
            request_id=request_id,
            type_id=gen_type.id,
            agent_id=gen_type.agent_id,
        )
        try:
            self._session.add(self._to_orm(gen_type))
            await self._session.flush()
            return gen_type
        except Exception as e:
            self._logger.error(
                "DocumentGenerationType save failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def find_by_id(
        self, type_id: str, request_id: str
    ) -> DocumentGenerationType | None:
        try:
            stmt = select(DocumentGenerationTypeModel).where(
                DocumentGenerationTypeModel.id == type_id
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            return self._to_domain(row) if row else None
        except Exception as e:
            self._logger.error(
                "DocumentGenerationType find_by_id failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def find_active_by_agent_worker(
        self, agent_id: str, worker_id: str, request_id: str
    ) -> DocumentGenerationType | None:
        try:
            stmt = select(DocumentGenerationTypeModel).where(
                DocumentGenerationTypeModel.agent_id == agent_id,
                DocumentGenerationTypeModel.worker_id == worker_id,
                DocumentGenerationTypeModel.status == GENERATION_TYPE_STATUS_ACTIVE,
            )
            result = await self._session.execute(stmt)
            row = result.scalars().first()
            return self._to_domain(row) if row else None
        except Exception as e:
            self._logger.error(
                "DocumentGenerationType find_active_by_agent_worker failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def soft_delete(self, type_id: str, request_id: str) -> None:
        self._logger.info(
            "DocumentGenerationType soft_delete",
            request_id=request_id,
            type_id=type_id,
        )
        try:
            stmt = (
                update(DocumentGenerationTypeModel)
                .where(DocumentGenerationTypeModel.id == type_id)
                .values(
                    status=GENERATION_TYPE_STATUS_DELETED,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self._session.execute(stmt)
        except Exception as e:
            self._logger.error(
                "DocumentGenerationType soft_delete failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def soft_delete_by_agent(self, agent_id: str, request_id: str) -> int:
        self._logger.info(
            "DocumentGenerationType soft_delete_by_agent",
            request_id=request_id,
            agent_id=agent_id,
        )
        try:
            stmt = (
                update(DocumentGenerationTypeModel)
                .where(
                    DocumentGenerationTypeModel.agent_id == agent_id,
                    DocumentGenerationTypeModel.status
                    == GENERATION_TYPE_STATUS_ACTIVE,
                )
                .values(
                    status=GENERATION_TYPE_STATUS_DELETED,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            result = await self._session.execute(stmt)
            return result.rowcount or 0
        except Exception as e:
            self._logger.error(
                "DocumentGenerationType soft_delete_by_agent failed",
                exception=e,
                request_id=request_id,
            )
            raise

    @staticmethod
    def _to_orm(gen_type: DocumentGenerationType) -> DocumentGenerationTypeModel:
        return DocumentGenerationTypeModel(
            id=gen_type.id,
            agent_id=gen_type.agent_id,
            worker_id=gen_type.worker_id,
            name=gen_type.name,
            description=gen_type.description,
            sections=[
                {"title": s.title, "guidance": s.guidance}
                for s in gen_type.sections
            ],
            output_format=gen_type.output_format,
            status=gen_type.status,
            created_at=gen_type.created_at,
            updated_at=gen_type.updated_at,
        )

    @staticmethod
    def _to_domain(row: DocumentGenerationTypeModel) -> DocumentGenerationType:
        return DocumentGenerationType(
            id=row.id,
            agent_id=row.agent_id,
            worker_id=row.worker_id,
            name=row.name,
            description=row.description,
            sections=[
                DocumentSection(
                    title=item["title"], guidance=item.get("guidance", "")
                )
                for item in (row.sections or [])
            ],
            output_format=row.output_format,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class SessionScopedDocumentGenerationTypeRepository(
    DocumentGenerationTypeRepositoryInterface
):
    """매 호출마다 새 세션을 열어 DocumentGenerationTypeRepository에 위임."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def save(
        self, gen_type: DocumentGenerationType, request_id: str
    ) -> DocumentGenerationType:
        async with self._session_factory() as session:
            async with session.begin():
                return await DocumentGenerationTypeRepository(
                    session, self._logger
                ).save(gen_type, request_id)

    async def find_by_id(
        self, type_id: str, request_id: str
    ) -> DocumentGenerationType | None:
        async with self._session_factory() as session:
            return await DocumentGenerationTypeRepository(
                session, self._logger
            ).find_by_id(type_id, request_id)

    async def find_active_by_agent_worker(
        self, agent_id: str, worker_id: str, request_id: str
    ) -> DocumentGenerationType | None:
        async with self._session_factory() as session:
            return await DocumentGenerationTypeRepository(
                session, self._logger
            ).find_active_by_agent_worker(agent_id, worker_id, request_id)

    async def soft_delete(self, type_id: str, request_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await DocumentGenerationTypeRepository(
                    session, self._logger
                ).soft_delete(type_id, request_id)

    async def soft_delete_by_agent(self, agent_id: str, request_id: str) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                return await DocumentGenerationTypeRepository(
                    session, self._logger
                ).soft_delete_by_agent(agent_id, request_id)
