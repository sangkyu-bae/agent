"""LlmModelRepository: llm_model MySQL CRUD."""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.llm_model.models import LlmModelModel


class LlmModelRepository(LlmModelRepositoryInterface):
    """MySQL 구현. DB-001 §10.3 준수 — commit/rollback은 get_session이 담당."""

    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, model: LlmModel, request_id: str) -> LlmModel:
        self._logger.info(
            "LlmModel save", request_id=request_id, model_id=model.id
        )
        try:
            row = self._to_orm(model)
            self._session.add(row)
            await self._session.flush()
            return model
        except Exception as e:
            self._logger.error(
                "LlmModel save failed", exception=e, request_id=request_id
            )
            raise

    async def find_by_id(
        self, model_id: str, request_id: str
    ) -> LlmModel | None:
        try:
            stmt = select(LlmModelModel).where(LlmModelModel.id == model_id)
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            return self._to_domain(row) if row else None
        except Exception as e:
            self._logger.error(
                "LlmModel find_by_id failed", exception=e, request_id=request_id
            )
            raise

    async def find_by_provider_and_name(
        self, provider: str, model_name: str, request_id: str
    ) -> LlmModel | None:
        try:
            stmt = select(LlmModelModel).where(
                LlmModelModel.provider == provider,
                LlmModelModel.model_name == model_name,
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            return self._to_domain(row) if row else None
        except Exception as e:
            self._logger.error(
                "LlmModel find_by_provider_and_name failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def find_default(self, request_id: str) -> LlmModel | None:
        try:
            stmt = select(LlmModelModel).where(LlmModelModel.is_default.is_(True))
            result = await self._session.execute(stmt)
            row = result.scalars().first()
            return self._to_domain(row) if row else None
        except Exception as e:
            self._logger.error(
                "LlmModel find_default failed", exception=e, request_id=request_id
            )
            raise

    async def list_active(self, request_id: str) -> list[LlmModel]:
        try:
            stmt = (
                select(LlmModelModel)
                .where(LlmModelModel.is_active.is_(True))
                .order_by(LlmModelModel.created_at.asc())
            )
            result = await self._session.execute(stmt)
            return [self._to_domain(r) for r in result.scalars().all()]
        except Exception as e:
            self._logger.error(
                "LlmModel list_active failed", exception=e, request_id=request_id
            )
            raise

    async def list_all(self, request_id: str) -> list[LlmModel]:
        try:
            stmt = select(LlmModelModel).order_by(
                LlmModelModel.created_at.asc()
            )
            result = await self._session.execute(stmt)
            return [self._to_domain(r) for r in result.scalars().all()]
        except Exception as e:
            self._logger.error(
                "LlmModel list_all failed", exception=e, request_id=request_id
            )
            raise

    async def update(self, model: LlmModel, request_id: str) -> LlmModel:
        self._logger.info(
            "LlmModel update", request_id=request_id, model_id=model.id
        )
        try:
            stmt = select(LlmModelModel).where(LlmModelModel.id == model.id)
            result = await self._session.execute(stmt)
            row = result.scalar_one()
            row.provider = model.provider
            row.model_name = model.model_name
            row.display_name = model.display_name
            row.description = model.description
            row.api_key_env = model.api_key_env
            row.max_tokens = model.max_tokens
            row.is_active = model.is_active
            row.is_default = model.is_default
            row.updated_at = model.updated_at
            await self._session.flush()
            return model
        except Exception as e:
            self._logger.error(
                "LlmModel update failed", exception=e, request_id=request_id
            )
            raise

    async def unset_all_defaults(self, request_id: str) -> None:
        try:
            stmt = (
                update(LlmModelModel)
                .where(LlmModelModel.is_default.is_(True))
                .values(is_default=False)
            )
            await self._session.execute(stmt)
            await self._session.flush()
        except Exception as e:
            self._logger.error(
                "LlmModel unset_all_defaults failed",
                exception=e,
                request_id=request_id,
            )
            raise

    def _to_orm(self, model: LlmModel) -> LlmModelModel:
        return LlmModelModel(
            id=model.id,
            provider=model.provider,
            model_name=model.model_name,
            display_name=model.display_name,
            description=model.description,
            api_key_env=model.api_key_env,
            max_tokens=model.max_tokens,
            is_active=model.is_active,
            is_default=model.is_default,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_domain(self, row: LlmModelModel) -> LlmModel:
        return LlmModel(
            id=row.id,
            provider=row.provider,
            model_name=row.model_name,
            display_name=row.display_name,
            description=row.description,
            api_key_env=row.api_key_env,
            max_tokens=row.max_tokens,
            is_active=row.is_active,
            is_default=row.is_default,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
