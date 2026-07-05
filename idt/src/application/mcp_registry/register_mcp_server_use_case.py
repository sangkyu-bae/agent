"""RegisterMCPServerUseCase: MCP 서버 등록."""
import uuid
from datetime import datetime

from src.application.mcp_registry.schemas import (
    MCPServerResponse,
    RegisterMCPServerRequest,
    to_response,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.policies import MCPRegistrationPolicy
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType


class RegisterMCPServerUseCase:

    def __init__(
        self,
        repository: MCPServerRegistryRepositoryInterface,
        logger: LoggerInterface,
        secrets_enabled: bool = True,
    ):
        self._repo = repository
        self._logger = logger
        # MCP_SECRET_KEY(암호화 키) 설정 여부. False면 시크릿 저장이 불가능하다.
        self._secrets_enabled = secrets_enabled

    async def execute(
        self, request: RegisterMCPServerRequest, request_id: str
    ) -> MCPServerResponse:
        self._logger.info(
            "RegisterMCPServerUseCase start",
            request_id=request_id,
            name=request.name,
        )

        if not MCPRegistrationPolicy.validate_name(request.name):
            raise ValueError(f"Invalid name: {request.name!r}")
        if not MCPRegistrationPolicy.validate_description(request.description):
            raise ValueError("Invalid description")
        if not MCPRegistrationPolicy.validate_endpoint(request.endpoint):
            raise ValueError(f"Invalid endpoint URL: {request.endpoint!r}")
        if not MCPRegistrationPolicy.validate_transport(request.transport):
            raise ValueError(f"Invalid transport: {request.transport!r}")
        if not MCPRegistrationPolicy.validate_auth(
            request.transport, request.auth_config
        ):
            raise ValueError("Invalid auth_config: api_key required for streamable_http")
        if (
            MCPRegistrationPolicy.requires_secret_storage(request.transport)
            and not self._secrets_enabled
        ):
            raise ValueError(
                "MCP_SECRET_KEY가 설정되지 않아 streamable_http 시크릿을 저장할 수 "
                "없습니다. .env에 MCP_SECRET_KEY를 설정하세요"
            )

        now = datetime.utcnow()
        registration = MCPServerRegistration(
            id=str(uuid.uuid4()),
            user_id=request.user_id,
            name=request.name,
            description=request.description,
            endpoint=request.endpoint,
            transport=MCPTransportType(request.transport),
            input_schema=request.input_schema,
            is_active=True,
            created_at=now,
            updated_at=now,
            auth_config=request.auth_config,
            server_config=request.server_config,
        )

        saved = await self._repo.save(registration, request_id)
        self._logger.info(
            "RegisterMCPServerUseCase done",
            request_id=request_id,
            id=saved.id,
        )
        return to_response(saved)
