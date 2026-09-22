"""MiddlewareCatalogRepository / AgentMiddlewareRepository: MySQL CRUD.

commit/rollback 금지 (세션 소유자는 상위 — 프로젝트 공통 규칙).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.middleware.entities import (
    AgentMiddlewareRecord,
    MiddlewareCatalogEntry,
    MiddlewareType,
)
from src.domain.middleware.interfaces import (
    AgentMiddlewareRepositoryInterface,
    MiddlewareCatalogRepositoryInterface,
)
from src.infrastructure.middleware.models import (
    AgentMiddlewareModel,
    MiddlewareCatalogModel,
)


class MiddlewareCatalogRepository(MiddlewareCatalogRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def list_all(self, request_id: str) -> list[MiddlewareCatalogEntry]:
        try:
            stmt = select(MiddlewareCatalogModel).order_by(
                MiddlewareCatalogModel.sort_order
            )
            result = await self._session.execute(stmt)
            return self._to_domain_list(result.scalars().all(), request_id)
        except Exception as e:
            self._logger.error(
                "MiddlewareCatalog list_all failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def find_by_type(
        self, middleware_type: str, request_id: str
    ) -> MiddlewareCatalogEntry | None:
        try:
            model = await self._find_model(middleware_type)
            if model is None:
                return None
            return self._to_domain_or_none(model, request_id)
        except Exception as e:
            self._logger.error(
                "MiddlewareCatalog find_by_type failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def update_flags(
        self,
        middleware_type: str,
        *,
        is_builtin: bool | None,
        is_enforced: bool | None,
        default_config: dict | None,
        request_id: str,
    ) -> MiddlewareCatalogEntry | None:
        try:
            model = await self._find_model(middleware_type)
            if model is None:
                return None
            if is_builtin is not None:
                model.is_builtin = is_builtin
            if is_enforced is not None:
                model.is_enforced = is_enforced
            if default_config is not None:
                model.default_config = default_config
            model.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
            self._logger.info(
                "MiddlewareCatalog update_flags done",
                request_id=request_id,
                middleware_type=middleware_type,
            )
            return self._to_domain_or_none(model, request_id)
        except Exception as e:
            self._logger.error(
                "MiddlewareCatalog update_flags failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def list_builtin(self, request_id: str) -> list[MiddlewareCatalogEntry]:
        try:
            stmt = (
                select(MiddlewareCatalogModel)
                .where(
                    MiddlewareCatalogModel.is_builtin.is_(True),
                    MiddlewareCatalogModel.is_active.is_(True),
                )
                .order_by(MiddlewareCatalogModel.sort_order)
            )
            result = await self._session.execute(stmt)
            return self._to_domain_list(result.scalars().all(), request_id)
        except Exception as e:
            self._logger.error(
                "MiddlewareCatalog list_builtin failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def _find_model(
        self, middleware_type: str
    ) -> MiddlewareCatalogModel | None:
        stmt = select(MiddlewareCatalogModel).where(
            MiddlewareCatalogModel.middleware_type == middleware_type
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    def _to_domain_list(
        self, models, request_id: str
    ) -> list[MiddlewareCatalogEntry]:
        entries = [self._to_domain_or_none(m, request_id) for m in models]
        return [e for e in entries if e is not None]

    def _to_domain_or_none(
        self, model: MiddlewareCatalogModel, request_id: str
    ) -> MiddlewareCatalogEntry | None:
        # 후속 미들웨어를 마이그레이션 INSERT만 하고 enum 추가를 빠뜨려도
        # 전 에이전트 실행·카탈로그 API가 깨지지 않도록 미지 타입은 제외한다.
        try:
            return self._to_domain(model)
        except ValueError:
            self._logger.warning(
                "MiddlewareCatalog unknown middleware_type skipped",
                request_id=request_id,
                middleware_type=model.middleware_type,
            )
            return None

    @staticmethod
    def _to_domain(model: MiddlewareCatalogModel) -> MiddlewareCatalogEntry:
        return MiddlewareCatalogEntry(
            id=model.id,
            middleware_type=MiddlewareType(model.middleware_type),
            name=model.name,
            description=model.description,
            is_builtin=model.is_builtin,
            is_enforced=model.is_enforced,
            default_config=model.default_config or {},
            is_active=model.is_active,
            sort_order=model.sort_order,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class AgentMiddlewareRepository(AgentMiddlewareRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def list_by_agent(
        self, agent_id: str, request_id: str
    ) -> list[AgentMiddlewareRecord]:
        try:
            stmt = (
                select(AgentMiddlewareModel)
                .where(AgentMiddlewareModel.agent_id == agent_id)
                .order_by(AgentMiddlewareModel.sort_order)
            )
            result = await self._session.execute(stmt)
            return [
                AgentMiddlewareRecord(
                    agent_id=m.agent_id,
                    middleware_type=m.middleware_type,
                    sort_order=m.sort_order,
                    config=m.config,
                )
                for m in result.scalars().all()
            ]
        except Exception as e:
            self._logger.error(
                "AgentMiddleware list_by_agent failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def upsert_config(
        self, *, agent_id: str, middleware_type: str, config: dict,
        request_id: str,
    ) -> None:
        """approval-gate Check G3 — 에이전트별 config 저장.

        uq_agent_middleware(agent_id, middleware_type) 가 한 행만 보장하므로
        있으면 config 만 갱신하고, 없으면 적용 행을 새로 만든다.
        sort_order 는 체인 순서에 영향이 없다(MergePolicy 가 카탈로그 순서로
        정렬) — 끝에 붙인다.
        """
        try:
            existing = (await self._session.execute(
                select(AgentMiddlewareModel).where(
                    AgentMiddlewareModel.agent_id == agent_id,
                    AgentMiddlewareModel.middleware_type == middleware_type,
                )
            )).scalar_one_or_none()
            if existing is not None:
                existing.config = dict(config)
            else:
                count = (await self._session.execute(
                    select(func.count()).select_from(AgentMiddlewareModel).where(
                        AgentMiddlewareModel.agent_id == agent_id
                    )
                )).scalar() or 0
                self._session.add(AgentMiddlewareModel(
                    id=str(uuid.uuid4()), agent_id=agent_id,
                    middleware_type=middleware_type, config=dict(config),
                    sort_order=int(count),
                    created_at=datetime.now(timezone.utc),
                ))
            await self._session.flush()
        except Exception as e:
            self._logger.error(
                "AgentMiddleware upsert_config failed",
                exception=e, request_id=request_id,
                agent_id=agent_id, middleware_type=middleware_type,
            )
            raise
