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


class UpdateMCPServerRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    endpoint: str | None = None
    input_schema: dict | None = None
    is_active: bool | None = None


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


class ListMCPServersResponse(BaseModel):
    items: list[MCPServerResponse]
    total: int


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
    )
