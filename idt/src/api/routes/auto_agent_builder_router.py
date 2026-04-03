"""자동 에이전트 빌더 라우터 (/api/v3/agents/auto)."""
from fastapi import APIRouter, Depends, HTTPException

from src.application.auto_agent_builder.auto_build_reply_use_case import AutoBuildReplyUseCase
from src.application.auto_agent_builder.auto_build_use_case import AutoBuildUseCase
from src.application.auto_agent_builder.schemas import (
    AutoBuildReplyRequest,
    AutoBuildRequest,
    AutoBuildResponse,
    AutoBuildSessionStatusResponse,
)

router = APIRouter(prefix="/api/v3/agents/auto", tags=["auto-agent-builder"])


def get_auto_build_use_case() -> AutoBuildUseCase:
    raise NotImplementedError


def get_auto_build_reply_use_case() -> AutoBuildReplyUseCase:
    raise NotImplementedError


def get_session_repository():
    raise NotImplementedError


@router.post("", response_model=AutoBuildResponse, status_code=202)
async def auto_build(
    request: AutoBuildRequest,
    use_case: AutoBuildUseCase = Depends(get_auto_build_use_case),
):
    """자연어 요청 → 자동 에이전트 빌드 시작."""
    return await use_case.execute(request)


@router.post("/{session_id}/reply", response_model=AutoBuildResponse)
async def auto_build_reply(
    session_id: str,
    request: AutoBuildReplyRequest,
    use_case: AutoBuildReplyUseCase = Depends(get_auto_build_reply_use_case),
):
    """보충 질문 답변 제출 → 재추론 → 에이전트 생성."""
    return await use_case.execute(session_id, request)


@router.get("/{session_id}", response_model=AutoBuildSessionStatusResponse)
async def get_session_status(
    session_id: str,
    session_repo=Depends(get_session_repository),
):
    """빌드 세션 상태 조회."""
    session = await session_repo.find(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return AutoBuildSessionStatusResponse(
        session_id=session.session_id,
        status=session.status,
        attempt_count=session.attempt_count,
        user_request=session.user_request,
        created_agent_id=session.created_agent_id,
    )
