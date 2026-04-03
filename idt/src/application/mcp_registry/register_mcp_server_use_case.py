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
    ):
        self._repo = repository
        self._logger = logger

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

        now = datetime.utcnow()
        registration = MCPServerRegistration(
            id=str(uuid.uuid4()),
            user_id=request.user_id,
            name=request.name,
            description=request.description,
            endpoint=request.endpoint,
            transport=MCPTransportType.SSE,
            input_schema=request.input_schema,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        saved = await self._repo.save(registration, request_id)
        self._logger.info(
            "RegisterMCPServerUseCase done",
            request_id=request_id,
            id=saved.id,
        )
        return to_response(saved)
