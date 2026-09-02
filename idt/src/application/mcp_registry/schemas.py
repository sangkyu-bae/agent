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


class ToolSyncResultResponse(BaseModel):
    """MCP 도구 동기화 결과 (mcp-tool-auto-sync FR-09).

    등록/수정 응답에만 실린다. 조회 응답에서는 상위 필드가 None이며,
    이는 "이번 응답은 sync를 수행하지 않았다"를 뜻한다 — ok=false(시도 후 실패)와
    구분된다(Design §4.2).
    """

    ok: bool
    synced_count: int
    error_hint: str | None = None


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
    # mcp-tool-auto-sync FR-09: sync 미수행(GET)·미주입(FR-06) 시 None
    tool_sync: ToolSyncResultResponse | None = None


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


def to_response(entity, tool_sync=None) -> MCPServerResponse:
    """엔티티 → 응답 스키마.

    tool_sync는 mcp-tool-auto-sync에서 추가된 선택 인자다. 기존 호출부(인자 1개)를
    그대로 지원하며, sync를 시도하지 않은 경우(attempted=False)에도 None을 반환해
    FR-06의 "기존과 동일하게 동작"을 응답 수준에서 보장한다.
    """
    return MCPServerResponse(
        tool_sync=(
            ToolSyncResultResponse(
                ok=tool_sync.ok,
                synced_count=tool_sync.synced_count,
                error_hint=tool_sync.error_hint,
            )
            if tool_sync is not None and tool_sync.attempted
            else None
        ),
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
