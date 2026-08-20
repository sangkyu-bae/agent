"""시스템 프롬프트 생성 엔드포인트 — /api/v1/prompt-composer.

Design Ref: §4.1~§4.3.

- **LLM 실패는 5xx 가 아니라 200 + degraded=true** 로 응답한다 (Plan D6).
  호출자가 에러 핸들링 없이 "기본 문안이라도 받는다"로 진행할 수 있어야 한다.
- 반면 **DB 실패는 숨기지 않는다** (§6.2): 저장이 실패하면 version_id 를 줄 수
  없으므로 200 으로 위장하면 호출자가 없는 버전을 참조하게 된다. 예외를 잡지
  않고 그대로 올려 `get_session` 이 rollback 하게 둔다.
- 타인 세션은 403 이 아니라 **404** 다 — 존재 여부를 노출하지 않는다 (SC-07).

DI placeholder 는 main.py 에서 override 한다.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.application.prompt_composer.append_human_version_use_case import (
    AppendHumanVersionUseCase,
)
from src.application.prompt_composer.compose_prompt_use_case import (
    ComposePromptUseCase,
    ComposeResult,
)
from src.application.prompt_composer.errors import (
    AgentAlreadyBoundError,
    PromptSessionNotFoundError,
)
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user
from src.interfaces.schemas.prompt_composer import (
    AppendVersionRequest,
    AppendVersionResponse,
    BindAgentRequest,
    ComposePromptRequest,
    ComposePromptResponse,
    PromptSessionResponse,
    RoleOut,
    SectionsOut,
    ToolGuideOut,
    VersionSummaryOut,
)

router = APIRouter(prefix="/api/v1/prompt-composer", tags=["prompt-composer"])

_NOT_FOUND = "세션을 찾을 수 없습니다"
_CONFLICT = "이미 에이전트가 연결된 세션입니다"


def get_prompt_composer_use_case() -> ComposePromptUseCase:
    raise NotImplementedError("ComposePromptUseCase not initialized")


def get_append_human_version_use_case() -> AppendHumanVersionUseCase:
    raise NotImplementedError("AppendHumanVersionUseCase not initialized")


@router.post("/compose", response_model=ComposePromptResponse)
async def compose_prompt(
    request: ComposePromptRequest,
    current_user: User = Depends(get_current_user),
    use_case: ComposePromptUseCase = Depends(get_prompt_composer_use_case),
) -> ComposePromptResponse:
    """채팅 + 의도 + 도구 → 시스템 프롬프트 생성 및 버전 저장.

    Returns:
        200: 생성 결과. degraded=true 면 LLM 실패로 규칙기반 폴백이며 에러가 아니다.

    Errors:
        401: 인증 실패
        404: session_id 가 없거나 타인 소유
        422: 입력 검증 실패
        500: 저장 실패 (LLM 실패와 구분된다 — Design §6.2)
    """
    try:
        result = await use_case.compose(
            user_id=str(current_user.id),
            user_request=request.user_request,
            request_id=str(uuid.uuid4()),
            history=[turn.model_dump() for turn in request.history],
            intent=request.intent.model_dump() if request.intent else None,
            tool_ids=tuple(request.tool_ids),
            session_id=request.session_id,
            agent_id=request.agent_id,
        )
    except PromptSessionNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return _to_response(result)


@router.get("/sessions/{session_id}", response_model=PromptSessionResponse)
async def get_prompt_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    use_case: ComposePromptUseCase = Depends(get_prompt_composer_use_case),
) -> PromptSessionResponse:
    """세션 메타 + 버전 목록(최신순). 본인 세션만 조회된다."""
    try:
        session, versions = await use_case.get_session(
            session_id, str(current_user.id)
        )
    except PromptSessionNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return PromptSessionResponse(
        session_id=session.id,
        agent_id=session.agent_id,
        user_request=session.user_request,
        created_at=session.created_at,
        versions=[_to_summary(v) for v in versions],
    )


@router.post(
    "/sessions/{session_id}/versions",
    status_code=201,
    response_model=AppendVersionResponse,
)
async def append_human_prompt_version(
    session_id: str,
    request: AppendVersionRequest,
    current_user: User = Depends(get_current_user),
    use_case: AppendHumanVersionUseCase = Depends(
        get_append_human_version_use_case
    ),
) -> AppendVersionResponse:
    """사용자가 편집한 시스템 프롬프트를 새 버전으로 저장한다.

    agent-create-wizard Design Ref: §4.5 — 위저드 4단계의 편집본 저장 경로.
    LLM 재생성이 아니므로 `/compose` 를 타지 않는다.

    Returns:
        201: 저장된 버전. `source` 는 항상 `human` 이다.

    Errors:
        401: 인증 실패
        404: session_id 가 없거나 타인 소유 (존재 비노출)
        422: 입력 검증 실패 (assembled 1~4000자 · tool_ids 50개 이하)
        500: 저장 실패 (201 로 위장하지 않는다 — Design §6.2)
    """
    try:
        result = await use_case.append(
            session_id=session_id,
            user_id=str(current_user.id),
            assembled=request.assembled,
            tool_ids=tuple(request.tool_ids),
        )
    except PromptSessionNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return AppendVersionResponse(
        session_id=result.session_id,
        version_id=result.version_id,
        version_no=result.version_no,
        source=result.source,
    )


@router.patch("/sessions/{session_id}", status_code=200)
async def bind_prompt_session_agent(
    session_id: str,
    request: BindAgentRequest,
    current_user: User = Depends(get_current_user),
    use_case: ComposePromptUseCase = Depends(get_prompt_composer_use_case),
) -> dict:
    """생성된 에이전트를 세션에 연결한다 (agent_id 백필).

    `agent_id` 의 실존 여부는 검증하지 않는다 — agent_builder 리포지토리에
    의존하면 "기존 경로 물리적 무변경"(Design D1)이 깨진다.
    """
    try:
        await use_case.bind_agent(session_id, str(current_user.id), request.agent_id)
    except PromptSessionNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    except AgentAlreadyBoundError:
        raise HTTPException(status_code=409, detail=_CONFLICT)
    return {"session_id": session_id, "agent_id": request.agent_id}


# ── 직렬화 ──────────────────────────────────────────────────────────────────


def _to_response(result: ComposeResult) -> ComposePromptResponse:
    prompt = result.prompt
    return ComposePromptResponse(
        session_id=result.session_id,
        version_id=result.version_id,
        version_no=result.version_no,
        sections=_to_sections_out(prompt.sections),
        assembled=prompt.assembled,
        degraded=prompt.degraded,
        reason=prompt.reason,
        dropped_tool_ids=list(prompt.dropped_tool_ids),
        unknown_tool_ids=list(prompt.unknown_tool_ids),
        elapsed_ms=prompt.elapsed_ms,
    )


def _to_sections_out(sections) -> SectionsOut:
    return SectionsOut(
        purpose=sections.purpose,
        roles=[RoleOut(title=r.title, detail=r.detail) for r in sections.roles],
        tool_guides=[
            ToolGuideOut(
                tool_id=g.tool_id,
                name=g.name,
                when=g.when,
                how=g.how,
                caution=g.caution,
            )
            for g in sections.tool_guides
        ],
        principles=list(sections.principles),
    )


def _to_summary(version) -> VersionSummaryOut:
    return VersionSummaryOut(
        version_id=version.id,
        version_no=version.version_no,
        degraded=version.degraded,
        reason=version.reason,
        tool_ids=list(version.tool_ids or []),
        assembled=version.assembled,
        created_at=version.created_at,
        source=version.source,
    )
