"""MCP Registry 도메인 스키마: MCPServerRegistration 엔티티."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MCPTransportType(str, Enum):
    SSE = "sse"


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

    @property
    def tool_id(self) -> str:
        """내부 도구와 충돌 방지를 위한 고유 tool_id."""
        return f"mcp_{self.id}"

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
        self.updated_at = updated_at
