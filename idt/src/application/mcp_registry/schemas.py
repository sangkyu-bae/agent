"""MCP Registry Application 스키마: Request/Response Pydantic 모델."""
from datetime import datetime

from pydantic import BaseModel, Field


class RegisterMCPServerRequest(BaseModel):
    user_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    endpoint: str = Field(description="MCP SSE endpoint URL (http/https)")
    input_schema: dict | None = Field(
        default=None, description="JSON Schema for input parameters"
    )
    transport: str = Field(
        default="sse", description="연결 방식: 'sse' | 'streamable_http'"
    )
    auth_config: dict | None = Field(
        default=None,
        description="플랫폼 인증 {'api_key','profile','headers'} (Smithery 등)",
    )
    server_config: dict | None = Field(
        default=None,
        description="다운스트림 서버 config {'NAVER_CLIENT_ID', ...}",
    )


class UpdateMCPServerRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    endpoint: str | None = None
    input_schema: dict | None = None
    is_active: bool | None = None
    transport: str | None = None
    auth_config: dict | None = None
    server_config: dict | None = None


class MCPServerResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    endpoint: str
    transport: str
    input_schema: dict | None
    is_active: bool
    tool_id: str
    created_at: datetime
    updated_at: datetime
    auth_config: dict | None = None
    server_config: dict | None = None


class ListMCPServersResponse(BaseModel):
    items: list[MCPServerResponse]
    total: int


class MCPConnectionTestResponse(BaseModel):
    """MCP 서버 연결 테스트 결과.

    연결/조회 실패는 예외가 아닌 ok=False + error로 표현한다.
    """

    ok: bool
    tools: list[dict] | None = None  # [{"name": str, "description": str}]
    error: str | None = None
    elapsed_ms: int | None = None


def to_response(entity) -> MCPServerResponse:
    return MCPServerResponse(
        id=entity.id,
        user_id=entity.user_id,
        name=entity.name,
        description=entity.description,
        endpoint=entity.endpoint,
        transport=entity.transport.value,
        input_schema=entity.input_schema,
        is_active=entity.is_active,
        tool_id=entity.tool_id,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        auth_config=entity.masked_auth(),
        server_config=entity.masked_server_config(),
    )
