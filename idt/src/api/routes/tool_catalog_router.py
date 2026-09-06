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
    ToolMetadataRequest,
    ToolMetadataResponse,
)

router = APIRouter(prefix="/api/v1/tool-catalog", tags=["Tool Catalog"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_list_tool_catalog_use_case():
    raise NotImplementedError


def get_sync_mcp_tools_use_case():
    raise NotImplementedError


def get_set_builtin_use_case():
    raise NotImplementedError


def get_update_tool_metadata_use_case():
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


@router.patch("/metadata", response_model=ToolMetadataResponse)
async def update_tool_metadata(
    body: ToolMetadataRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_update_tool_metadata_use_case),
):
    """mcp-tool-category-routing §4.2 (FR-13): 도구 분류·호출 상한 지정.

    tool_id는 body로 받는다 — set_builtin과 같은 이유(카탈로그 형식이 콜론·
    임의 도구명을 포함해 path 세그먼트로 부적합)로 형태를 맞춘다.

    부분 갱신: body에 없는 필드는 유스케이스에 넘기지 않아 해당 컬럼이
    그대로 유지된다. 명시적 null은 '미분류/기본값으로 되돌리기'라 전달한다 —
    pydantic model_fields_set이 '생략'과 'null'을 가른다.
    """
    request_id = str(uuid.uuid4())
    changes = {
        field: getattr(body, field)
        for field in ("category", "max_tool_calls")
        if field in body.model_fields_set
    }
    try:
        updated = await use_case.execute(body.tool_id, request_id, **changes)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        # 도메인 정책 위반(허용값 밖 / collect 지정 불가 도구 — D-04)
        raise HTTPException(status_code=400, detail=str(e))
    return ToolMetadataResponse(
        tool_id=updated.tool_id,
        category=updated.category,
        max_tool_calls=updated.max_tool_calls,
    )


@router.post("/sync")
async def sync_mcp_tools(
    body: SyncMcpToolsRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_sync_mcp_tools_use_case),
):
    request_id = str(uuid.uuid4())
    count = await use_case.execute(body.mcp_server_id, request_id)
    return {"synced_count": count}
