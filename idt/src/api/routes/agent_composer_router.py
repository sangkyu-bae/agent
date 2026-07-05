"""Agent Composer Router: 자연어 → 에이전트 초안 조합 API (무저장).

nl-agent-composer D4: agent_builder_router와 분리된 신규 라우터.
초안은 DB에 저장되지 않으며, 확정 저장은 기존 POST /api/v1/agents가 담당한다.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.application.agent_composer.schemas import (
    ComposeAgentDraftResponse,
    ComposeAgentRequest,
)
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/agents", tags=["Agent Composer"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_compose_agent_use_case():
    raise NotImplementedError


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.post("/compose", response_model=ComposeAgentDraftResponse)
async def compose_agent(
    body: ComposeAgentRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_compose_agent_use_case),
):
    """자연어 요청 → 에이전트 초안 반환 (DB 저장 없음).

    응답을 생성 폼에 프리필한 뒤, 사용자가 저장 시 POST /api/v1/agents로 생성한다.
    """
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(body, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
