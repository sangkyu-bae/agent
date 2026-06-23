"""MCPServerRepository: MySQLBaseRepository 기반 MCP 서버 저장소."""
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.domain.mysql.schemas import MySQLQueryCondition
from src.infrastructure.mcp_registry.models import MCPServerModel
from src.infrastructure.persistence.mysql_base_repository import MySQLBaseRepository
from src.infrastructure.security.secret_cipher import SecretCipher


def _to_model(
    entity: MCPServerRegistration, cipher: SecretCipher | None = None
) -> MCPServerModel:
    auth_enc = cipher.encrypt_dict(entity.auth_config) if cipher else None
    server_enc = cipher.encrypt_dict(entity.server_config) if cipher else None
    return MCPServerModel(
        id=entity.id,
        user_id=entity.user_id,
        name=entity.name,
        description=entity.description,
        endpoint=entity.endpoint,
        transport=entity.transport.value,
        input_schema=entity.input_schema,
        auth_config_enc=auth_enc,
        server_config_enc=server_enc,
        is_active=entity.is_active,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _to_entity(
    model: MCPServerModel, cipher: SecretCipher | None = None
) -> MCPServerRegistration:
    auth_config = None
    server_config = None
    if cipher is not None:
        auth_config = cipher.decrypt_dict(getattr(model, "auth_config_enc", None))
        server_config = cipher.decrypt_dict(getattr(model, "server_config_enc", None))
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
        auth_config=auth_config,
        server_config=server_config,
    )


class MCPServerRepository(
    MySQLBaseRepository[MCPServerModel],
    MCPServerRegistryRepositoryInterface,
):
    def __init__(
        self,
        session: AsyncSession,
        logger: LoggerInterface,
        cipher: SecretCipher | None = None,
    ):
        super().__init__(session, MCPServerModel, logger)
        self._cipher = cipher

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
        model = _to_model(registration, self._cipher)
        saved = await self._base_save(model, request_id)
        return _to_entity(saved, self._cipher)

    async def find_by_id(
        self, id: str, request_id: str
    ) -> MCPServerRegistration | None:
        model = await self._base_find_by_id(id, request_id)
        return _to_entity(model, self._cipher) if model else None

    async def find_all_active(self, request_id: str) -> list[MCPServerRegistration]:
        conditions = [MySQLQueryCondition(field="is_active", operator="eq", value=True)]
        models = await self._base_find_by_conditions(conditions, request_id)
        return [_to_entity(m, self._cipher) for m in models]

    async def find_by_user(
        self, user_id: str, request_id: str
    ) -> list[MCPServerRegistration]:
        conditions = [MySQLQueryCondition(field="user_id", operator="eq", value=user_id)]
        models = await self._base_find_by_conditions(conditions, request_id)
        return [_to_entity(m, self._cipher) for m in models]

    async def update(
        self, registration: MCPServerRegistration, request_id: str
    ) -> MCPServerRegistration:
        model = _to_model(registration, self._cipher)
        saved = await self._base_save(model, request_id)
        return _to_entity(saved, self._cipher)

    async def delete(self, id: str, request_id: str) -> bool:
        return await self._base_delete(id, request_id)
