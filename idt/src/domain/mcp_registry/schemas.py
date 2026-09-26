"""MCP Registry 도메인 스키마: MCPServerRegistration 엔티티."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.domain.mcp_registry.identity import IdentityHeaderConfig

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
    # approval-gate-phase2 D-07: 이 서버의 도구가 카탈로그에 "처음" 들어올 때의
    # requires_approval 초기값. 기존 엔트리에는 소급하지 않는다 — 그 값의
    # 주인은 관리자(tool_catalog.requires_approval)다.
    default_requires_approval: bool = False
    # Design Ref: mcp-identity-header §3.1 — None 이면 신원 헤더 미사용 (FR-08).
    # 서명 비밀을 품으므로 auth_config 와 같은 저장 경계에서 암호화한다.
    identity_config: IdentityHeaderConfig | None = field(default=None)
    # Check G-3: 저장된 암호문을 복호화하지 못했다(키 누락·교체·손상). '미설정'과
    # 구분해야 헤더 없이 나가거나 다음 수정에서 조용히 지워지지 않는다.
    identity_config_unreadable: bool = False

    @property
    def requires_identity(self) -> bool:
        return self.identity_config is not None or self.identity_config_unreadable

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

    def masked_identity(self) -> dict | None:
        """응답/로깅용 신원 설정. secret 만 가린다."""
        return self.identity_config.masked() if self.identity_config else None

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
        default_requires_approval: bool | None = None,
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
        if default_requires_approval is not None:
            self.default_requires_approval = default_requires_approval
        self.updated_at = updated_at
