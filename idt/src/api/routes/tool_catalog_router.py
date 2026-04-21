"""Tool Catalog Router: 도구 카탈로그 조회 + MCP 동기화 API."""
import uuid

from fastapi import APIRouter, Depends

from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user, require_role

from src.application.tool_catalog.schemas import (
    SyncMcpToolsRequest,
    ToolCatalogListResponse,
)

router = APIRouter(prefix="/api/v1/tool-catalog", tags=["Tool Catalog"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_list_tool_catalog_use_case():
    raise NotImplementedError


def get_sync_mcp_tools_use_case():
    raise NotImplementedError


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.get("", response_model=ToolCatalogListResponse)
async def list_tool_catalog(
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_tool_catalog_use_case),
):
    request_id = str(uuid.uuid4())
    return await use_case.execute(request_id)


@router.post("/sync")
async def sync_mcp_tools(
    body: SyncMcpToolsRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_sync_mcp_tools_use_case),
):
    request_id = str(uuid.uuid4())
    count = await use_case.execute(body.mcp_server_id, request_id)
    return {"synced_count": count}
