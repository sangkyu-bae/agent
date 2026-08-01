"""Tool Catalog Router: 도구 카탈로그 조회 + MCP 동기화 + 빌트인 토글 API."""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user, require_role

from src.application.tool_catalog.schemas import (
    SetBuiltinRequest,
    SetBuiltinResponse,
    SyncMcpToolsRequest,
    ToolCatalogListResponse,
)

router = APIRouter(prefix="/api/v1/tool-catalog", tags=["Tool Catalog"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_list_tool_catalog_use_case():
    raise NotImplementedError


def get_sync_mcp_tools_use_case():
    raise NotImplementedError


def get_set_builtin_use_case():
    raise NotImplementedError


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.get("", response_model=ToolCatalogListResponse)
async def list_tool_catalog(
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_tool_catalog_use_case),
):
    request_id = str(uuid.uuid4())
    return await use_case.execute(request_id)


@router.patch("/builtin", response_model=SetBuiltinResponse)
async def set_builtin(
    body: SetBuiltinRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_set_builtin_use_case),
):
    """builtin-tools D3: 빌트인 등록/해제 (관리자 전용).

    tool_id는 body로 받는다 — 카탈로그 형식(mcp:{uuid}:{tool})이 콜론·임의
    도구명을 포함해 path 세그먼트로 부적합하기 때문(기존 /sync 스타일 정합).
    """
    request_id = str(uuid.uuid4())
    try:
        updated = await use_case.execute(body.tool_id, body.is_builtin, request_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return SetBuiltinResponse(tool_id=updated.tool_id, is_builtin=updated.is_builtin)


@router.post("/sync")
async def sync_mcp_tools(
    body: SyncMcpToolsRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_sync_mcp_tools_use_case),
):
    request_id = str(uuid.uuid4())
    count = await use_case.execute(body.mcp_server_id, request_id)
    return {"synced_count": count}
