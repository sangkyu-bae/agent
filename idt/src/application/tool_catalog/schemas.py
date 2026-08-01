"""ToolCatalog 애플리케이션 레이어 스키마."""
from pydantic import BaseModel


class ToolCatalogItemResponse(BaseModel):
    tool_id: str
    source: str
    name: str
    description: str
    mcp_server_id: str | None = None
    requires_env: list[str] = []
    # builtin-tools D4: 에이전트 생성 시 자동 주입되는 빌트인 여부
    is_builtin: bool = False


class ToolCatalogListResponse(BaseModel):
    tools: list[ToolCatalogItemResponse]


class SyncMcpToolsRequest(BaseModel):
    mcp_server_id: str | None = None


class SetBuiltinRequest(BaseModel):
    """builtin-tools D3: 빌트인 토글 요청 (tool_id는 카탈로그 형식)."""

    tool_id: str
    is_builtin: bool


class SetBuiltinResponse(BaseModel):
    tool_id: str
    is_builtin: bool
