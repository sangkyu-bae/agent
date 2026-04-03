"""MCPServerRepository: MySQLBaseRepository 기반 MCP 서버 저장소."""
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.domain.mysql.schemas import MySQLQueryCondition
from src.infrastructure.mcp_registry.models import MCPServerModel
from src.infrastructure.persistence.mysql_base_repository import MySQLBaseRepository


def _to_model(entity: MCPServerRegistration) -> MCPServerModel:
    return MCPServerModel(
        id=entity.id,
        user_id=entity.user_id,
        name=entity.name,
        description=entity.description,
        endpoint=entity.endpoint,
        transport=entity.transport.value,
        input_schema=entity.input_schema,
        is_active=entity.is_active,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _to_entity(model: MCPServerModel) -> MCPServerRegistration:
    return MCPServerRegistration(
        id=model.id,
        user_id=model.user_id,
        name=model.name,
        description=model.description,
        endpoint=model.endpoint,
        transport=MCPTransportType(model.transport),
        input_schema=model.input_schema,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class MCPServerRepository(
    MySQLBaseRepository[MCPServerModel],
    MCPServerRegistryRepositoryInterface,
):
    def __init__(self, session: AsyncSession, logger: LoggerInterface):
        super().__init__(session, MCPServerModel, logger)

    # ── 내부 위임 메서드 (테스트 패치 포인트) ──────────────────────

    async def _base_save(self, model: MCPServerModel, request_id: str) -> MCPServerModel:
        return await MySQLBaseRepository.save(self, model, request_id)

    async def _base_find_by_id(self, id: str, request_id: str) -> MCPServerModel | None:
        return await MySQLBaseRepository.find_by_id(self, id, request_id)

    async def _base_find_by_conditions(
        self, conditions: list[MySQLQueryCondition], request_id: str
    ) -> list[MCPServerModel]:
        return await MySQLBaseRepository.find_by_conditions(self, conditions, request_id)

    async def _base_delete(self, id: str, request_id: str) -> bool:
        return await MySQLBaseRepository.delete(self, id, request_id)

    # ── MCPServerRegistryRepositoryInterface 구현 ──────────────────

    async def save(
        self, registration: MCPServerRegistration, request_id: str
    ) -> MCPServerRegistration:
        model = _to_model(registration)
        saved = await self._base_save(model, request_id)
        return _to_entity(saved)

    async def find_by_id(
        self, id: str, request_id: str
    ) -> MCPServerRegistration | None:
        model = await self._base_find_by_id(id, request_id)
        return _to_entity(model) if model else None

    async def find_all_active(self, request_id: str) -> list[MCPServerRegistration]:
        conditions = [MySQLQueryCondition(field="is_active", operator="eq", value=True)]
        models = await self._base_find_by_conditions(conditions, request_id)
        return [_to_entity(m) for m in models]

    async def find_by_user(
        self, user_id: str, request_id: str
    ) -> list[MCPServerRegistration]:
        conditions = [MySQLQueryCondition(field="user_id", operator="eq", value=user_id)]
        models = await self._base_find_by_conditions(conditions, request_id)
        return [_to_entity(m) for m in models]

    async def update(
        self, registration: MCPServerRegistration, request_id: str
    ) -> MCPServerRegistration:
        model = _to_model(registration)
        saved = await self._base_save(model, request_id)
        return _to_entity(saved)

    async def delete(self, id: str, request_id: str) -> bool:
        return await self._base_delete(id, request_id)
