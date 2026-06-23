"""MCP Registry 도메인 스키마: MCPServerRegistration 엔티티."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

_MASK = "****"


class MCPTransportType(str, Enum):
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


def mask_secrets(data: dict | None) -> dict | None:
    """시크릿 dict의 값을 마스킹한다. 키만 노출하고 값은 '****'로 치환.

    중첩 dict(headers 등)도 재귀적으로 마스킹한다.
    """
    if data is None:
        return None
    masked: dict = {}
    for key, value in data.items():
        masked[key] = mask_secrets(value) if isinstance(value, dict) else _MASK
    return masked


@dataclass
class MCPServerRegistration:
    """MCP 서버 등록 도메인 엔티티."""

    id: str
    user_id: str
    name: str
    description: str
    endpoint: str
    transport: MCPTransportType
    input_schema: dict | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # transport별 인증/서버 config (평문, 앱 메모리 한정 — 저장 경계에서 암호화)
    auth_config: dict | None = field(default=None)
    server_config: dict | None = field(default=None)

    @property
    def tool_id(self) -> str:
        """내부 도구와 충돌 방지를 위한 고유 tool_id."""
        return f"mcp_{self.id}"

    def masked_auth(self) -> dict | None:
        """응답/로깅용 마스킹된 auth_config."""
        return mask_secrets(self.auth_config)

    def masked_server_config(self) -> dict | None:
        """응답/로깅용 마스킹된 server_config."""
        return mask_secrets(self.server_config)

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True

    def apply_update(
        self,
        name: str | None,
        description: str | None,
        endpoint: str | None,
        input_schema: dict | None,
        is_active: bool | None,
        updated_at: datetime,
        transport: "MCPTransportType | None" = None,
        auth_config: dict | None = None,
        server_config: dict | None = None,
    ) -> None:
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if endpoint is not None:
            self.endpoint = endpoint
        if input_schema is not None:
            self.input_schema = input_schema
        if is_active is not None:
            self.is_active = is_active
        if transport is not None:
            self.transport = transport
        if auth_config is not None:
            self.auth_config = auth_config
        if server_config is not None:
            self.server_config = server_config
        self.updated_at = updated_at
