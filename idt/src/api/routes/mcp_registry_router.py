"""MCP Registry Router: MCP 서버 등록/조회/수정/삭제 API."""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.application.mcp_registry.schemas import (
    ListMCPServersResponse,
    MCPServerResponse,
    RegisterMCPServerRequest,
    UpdateMCPServerRequest,
)

router = APIRouter(prefix="/api/v1/mcp-registry", tags=["MCP Registry"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_register_use_case():
    raise NotImplementedError


def get_list_use_case():
    raise NotImplementedError


def get_update_use_case():
    raise NotImplementedError


def get_delete_use_case():
    raise NotImplementedError


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.post("", response_model=MCPServerResponse, status_code=201)
async def register_mcp_server(
    body: RegisterMCPServerRequest,
    use_case=Depends(get_register_use_case),
):
    """MCP 서버 등록."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(body, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("", response_model=ListMCPServersResponse)
async def list_mcp_servers(
    user_id: str | None = None,
    use_case=Depends(get_list_use_case),
):
    """MCP 서버 목록 조회 (user_id 필터 선택)."""
    request_id = str(uuid.uuid4())
    if user_id:
        return await use_case.execute_by_user(user_id, request_id)
    return await use_case.execute_all(request_id)


@router.get("/{id}", response_model=MCPServerResponse)
async def get_mcp_server(
    id: str,
    use_case=Depends(get_list_use_case),
):
    """특정 MCP 서버 조회."""
    request_id = str(uuid.uuid4())
    result = await use_case.execute_by_id(id, request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return result


@router.put("/{id}", response_model=MCPServerResponse)
async def update_mcp_server(
    id: str,
    body: UpdateMCPServerRequest,
    use_case=Depends(get_update_use_case),
):
    """MCP 서버 정보 수정."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(id, body, request_id)
    except ValueError as e:
        msg = str(e)
        raise HTTPException(
            status_code=404 if "찾을 수 없" in msg else 422, detail=msg
        )


@router.delete("/{id}", status_code=204)
async def delete_mcp_server(
    id: str,
    use_case=Depends(get_delete_use_case),
):
    """MCP 서버 삭제."""
    request_id = str(uuid.uuid4())
    deleted = await use_case.execute(id, request_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="MCP server not found")
