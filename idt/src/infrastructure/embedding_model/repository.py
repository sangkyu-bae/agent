from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.embedding_model.interfaces import (
    EmbeddingModelRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.embedding_model.models import EmbeddingModelTable


class EmbeddingModelRepository(EmbeddingModelRepositoryInterface):
    def __init__(
        self, session: AsyncSession, logger: LoggerInterface
    ) -> None:
        self._session = session
        self._logger = logger

    @staticmethod
    def _to_entity(row: EmbeddingModelTable) -> EmbeddingModel:
        return EmbeddingModel(
            id=row.id,
            provider=row.provider,
            model_name=row.model_name,
            display_name=row.display_name,
            vector_dimension=row.vector_dimension,
            is_active=row.is_active,
            description=row.description,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def find_by_model_name(
        self, model_name: str, request_id: str
    ) -> EmbeddingModel | None:
        stmt = select(EmbeddingModelTable).where(
            EmbeddingModelTable.model_name == model_name
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def list_active(
        self, request_id: str
    ) -> list[EmbeddingModel]:
        stmt = (
            select(EmbeddingModelTable)
            .where(EmbeddingModelTable.is_active.is_(True))
            .order_by(
                EmbeddingModelTable.provider,
                EmbeddingModelTable.model_name,
            )
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(r) for r in result.scalars().all()]

    async def save(
        self, model: EmbeddingModel, request_id: str
    ) -> EmbeddingModel:
        row = EmbeddingModelTable(
            provider=model.provider,
            model_name=model.model_name,
            display_name=model.display_name,
            vector_dimension=model.vector_dimension,
            is_active=model.is_active,
            description=model.description,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
        self._session.add(row)
        await self._session.flush()
        self._logger.info(
            "embedding_model saved",
            request_id=request_id,
            model_name=model.model_name,
        )
        return self._to_entity(row)

    async def find_by_provider_and_name(
        self, provider: str, model_name: str, request_id: str
    ) -> EmbeddingModel | None:
        stmt = select(EmbeddingModelTable).where(
            EmbeddingModelTable.provider == provider,
            EmbeddingModelTable.model_name == model_name,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None
