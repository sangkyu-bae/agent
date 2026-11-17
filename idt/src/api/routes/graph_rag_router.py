"""graph-rag capabilities: GET /api/v1/graph-rag/capabilities (Plan FR-24).

프론트는 이 응답의 visible 로만 그래프 관련 UI 노출을 정한다. 일반 사용자 응답에는
stage 를 넣지 않는다. 모듈 미등록이면 라우터 자체가 없다(404 → 프론트는 숨김).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.application.graph_rag.hooks import capabilities_for
from src.domain.auth.entities import User, UserRole
from src.domain.graph_rag.interfaces import GraphSettingsReaderPort
from src.interfaces.dependencies.auth import get_current_user
from src.interfaces.schemas.graph_rag import CapabilitiesResponse

router = APIRouter(prefix="/api/v1/graph-rag", tags=["graph-rag"])


def get_graph_settings_reader() -> GraphSettingsReaderPort:
    raise NotImplementedError("graph settings reader not wired (wire_graph_rag)")


@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    response_model_exclude_none=True,
)
async def capabilities(
    current_user: User = Depends(get_current_user),
    reader: GraphSettingsReaderPort = Depends(get_graph_settings_reader),
) -> CapabilitiesResponse:
    data = await capabilities_for(
        reader, caller_is_admin=current_user.role == UserRole.ADMIN
    )
    return CapabilitiesResponse(**data)
