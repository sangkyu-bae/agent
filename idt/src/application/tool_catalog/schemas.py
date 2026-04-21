"""ToolCatalog 애플리케이션 레이어 스키마."""
from pydantic import BaseModel


class ToolCatalogItemResponse(BaseModel):
    tool_id: str
    source: str
    name: str
    description: str
    mcp_server_id: str | None = None
    requires_env: list[str] = []


class ToolCatalogListResponse(BaseModel):
    tools: list[ToolCatalogItemResponse]


class SyncMcpToolsRequest(BaseModel):
    mcp_server_id: str | None = None
