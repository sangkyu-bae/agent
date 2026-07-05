"""UpdateMCPServerUseCase: MCP 서버 정보 수정."""
from datetime import datetime

from src.application.mcp_registry.schemas import (
    MCPServerResponse,
    UpdateMCPServerRequest,
    to_response,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.policies import MCPRegistrationPolicy
from src.domain.mcp_registry.schemas import MCPTransportType


class UpdateMCPServerUseCase:

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
        self, id: str, request: UpdateMCPServerRequest, request_id: str
    ) -> MCPServerResponse:
        self._logger.info(
            "UpdateMCPServerUseCase start", request_id=request_id, id=id
        )

        existing = await self._repo.find_by_id(id, request_id)
        if existing is None:
            raise ValueError(f"MCP 서버를 찾을 수 없습니다: {id}")

        if request.name is not None and not MCPRegistrationPolicy.validate_name(request.name):
            raise ValueError(f"Invalid name: {request.name!r}")
        if request.endpoint is not None and not MCPRegistrationPolicy.validate_endpoint(request.endpoint):
            raise ValueError(f"Invalid endpoint URL: {request.endpoint!r}")
        if request.transport is not None and not MCPRegistrationPolicy.validate_transport(request.transport):
            raise ValueError(f"Invalid transport: {request.transport!r}")
        # transport/auth가 바뀌는 경우에만 병합 후 상태로 인증 필수 필드 검증
        # (api_key 누락 → Smithery 404 → 'Session terminated' 사전 차단)
        if request.transport is not None or request.auth_config is not None:
            effective_transport = (
                request.transport
                if request.transport is not None
                else existing.transport.value
            )
            effective_auth = (
                request.auth_config
                if request.auth_config is not None
                else existing.auth_config
            )
            if not MCPRegistrationPolicy.validate_auth(
                effective_transport, effective_auth
            ):
                raise ValueError(
                    "Invalid auth_config: api_key required for streamable_http"
                )
            if (
                MCPRegistrationPolicy.requires_secret_storage(effective_transport)
                and not self._secrets_enabled
            ):
                raise ValueError(
                    "MCP_SECRET_KEY가 설정되지 않아 streamable_http 시크릿을 저장할 수 "
                    "없습니다. .env에 MCP_SECRET_KEY를 설정하세요"
                )

        new_transport = (
            MCPTransportType(request.transport) if request.transport is not None else None
        )
        existing.apply_update(
            name=request.name,
            description=request.description,
            endpoint=request.endpoint,
            input_schema=request.input_schema,
            is_active=request.is_active,
            updated_at=datetime.utcnow(),
            transport=new_transport,
            auth_config=request.auth_config,
            server_config=request.server_config,
        )

        saved = await self._repo.update(existing, request_id)
        self._logger.info(
            "UpdateMCPServerUseCase done", request_id=request_id, id=id
        )
        return to_response(saved)
