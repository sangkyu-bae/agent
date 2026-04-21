"""ToolCatalogRepository: tool_catalog MySQL CRUD."""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface
from src.infrastructure.tool_catalog.models import ToolCatalogModel


class ToolCatalogRepository(ToolCatalogRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, entry: ToolCatalogEntry, request_id: str) -> ToolCatalogEntry:
        self._logger.info("ToolCatalog save", request_id=request_id, tool_id=entry.tool_id)
        try:
            now = datetime.now(timezone.utc)
            model = ToolCatalogModel(
                id=entry.id,
                tool_id=entry.tool_id,
                source=entry.source,
                mcp_server_id=entry.mcp_server_id,
                name=entry.name,
                description=entry.description,
                requires_env=entry.requires_env or None,
                is_active=entry.is_active,
                created_at=entry.created_at or now,
                updated_at=entry.updated_at or now,
            )
            self._session.add(model)
            await self._session.flush()
            return entry
        except Exception as e:
            self._logger.error("ToolCatalog save failed", exception=e, request_id=request_id)
            raise

    async def upsert_by_tool_id(
        self, entry: ToolCatalogEntry, request_id: str
    ) -> ToolCatalogEntry:
        self._logger.info("ToolCatalog upsert", request_id=request_id, tool_id=entry.tool_id)
        try:
            existing = await self.find_by_tool_id(entry.tool_id, request_id)
            if existing is not None:
                now = datetime.now(timezone.utc)
                stmt = (
                    update(ToolCatalogModel)
                    .where(ToolCatalogModel.tool_id == entry.tool_id)
                    .values(
                        name=entry.name,
                        description=entry.description,
                        is_active=entry.is_active,
                        updated_at=now,
                    )
                )
                await self._session.execute(stmt)
                await self._session.flush()
                return entry
            return await self.save(entry, request_id)
        except Exception as e:
            self._logger.error("ToolCatalog upsert failed", exception=e, request_id=request_id)
            raise

    async def find_by_tool_id(
        self, tool_id: str, request_id: str
    ) -> ToolCatalogEntry | None:
        self._logger.info("ToolCatalog find_by_tool_id", request_id=request_id, tool_id=tool_id)
        try:
            stmt = select(ToolCatalogModel).where(ToolCatalogModel.tool_id == tool_id)
            result = await self._session.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_domain(model)
        except Exception as e:
            self._logger.error(
                "ToolCatalog find_by_tool_id failed", exception=e, request_id=request_id
            )
            raise

    async def list_active(self, request_id: str) -> list[ToolCatalogEntry]:
        self._logger.info("ToolCatalog list_active", request_id=request_id)
        try:
            stmt = (
                select(ToolCatalogModel)
                .where(ToolCatalogModel.is_active == True)  # noqa: E712
                .order_by(ToolCatalogModel.source, ToolCatalogModel.name)
            )
            result = await self._session.execute(stmt)
            return [self._to_domain(m) for m in result.scalars().all()]
        except Exception as e:
            self._logger.error("ToolCatalog list_active failed", exception=e, request_id=request_id)
            raise

    async def deactivate_by_mcp_server(
        self, mcp_server_id: str, request_id: str
    ) -> int:
        self._logger.info(
            "ToolCatalog deactivate_by_mcp_server",
            request_id=request_id,
            mcp_server_id=mcp_server_id,
        )
        try:
            stmt = (
                update(ToolCatalogModel)
                .where(
                    ToolCatalogModel.mcp_server_id == mcp_server_id,
                    ToolCatalogModel.is_active == True,  # noqa: E712
                )
                .values(is_active=False, updated_at=datetime.now(timezone.utc))
            )
            result = await self._session.execute(stmt)
            await self._session.flush()
            return result.rowcount
        except Exception as e:
            self._logger.error(
                "ToolCatalog deactivate_by_mcp_server failed",
                exception=e, request_id=request_id,
            )
            raise

    def _to_domain(self, model: ToolCatalogModel) -> ToolCatalogEntry:
        return ToolCatalogEntry(
            id=model.id,
            tool_id=model.tool_id,
            source=model.source,
            name=model.name,
            description=model.description,
            mcp_server_id=model.mcp_server_id,
            requires_env=model.requires_env or [],
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
