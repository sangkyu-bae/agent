"""Agent Builder Router: 에이전트 생성/조회/수정/실행 API."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user, require_role

from src.application.agent_builder.schemas import (
    AvailableToolsResponse,
    CreateAgentRequest,
    CreateAgentResponse,
    GetAgentResponse,
    InterviewAnswerRequest,
    InterviewAnswerResponse,
    InterviewFinalizeRequest,
    InterviewStartRequest,
    InterviewStartResponse,
    ListAgentsRequest,
    ListAgentsResponse,
    RunAgentRequest,
    RunAgentResponse,
    ToolMetaResponse,
    UpdateAgentRequest,
    UpdateAgentResponse,
    WorkerInfo,
)

router = APIRouter(prefix="/api/v1/agents", tags=["Agent Builder"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_create_agent_use_case():
    raise NotImplementedError


def get_update_agent_use_case():
    raise NotImplementedError


def get_run_agent_use_case():
    raise NotImplementedError


def get_get_agent_use_case():
    raise NotImplementedError


def get_interview_use_case():
    raise NotImplementedError


def get_load_mcp_tools_use_case():
    raise NotImplementedError


def get_list_agents_use_case():
    raise NotImplementedError


def get_delete_agent_use_case():
    raise NotImplementedError


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.get("/tools", response_model=AvailableToolsResponse)
async def list_tools(
    load_mcp_use_case=Depends(get_load_mcp_tools_use_case),
):
    """사용 가능한 도구 목록 조회 (내부 도구 + DB 등록 MCP 도구)."""
    import uuid
    from src.domain.agent_builder.tool_registry import get_all_tools

    request_id = str(uuid.uuid4())

    # 1. 내부 도구 (TOOL_REGISTRY)
    configurable_tools = {"internal_document_search"}
    rag_config_schema = {
        "collection_name": {"type": "string", "nullable": True},
        "es_index": {"type": "string", "nullable": True},
        "metadata_filter": {"type": "object", "additionalProperties": {"type": "string"}},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
        "search_mode": {"type": "string", "enum": ["hybrid", "vector_only", "bm25_only"], "default": "hybrid"},
        "rrf_k": {"type": "integer", "minimum": 1, "default": 60},
        "tool_name": {"type": "string", "maxLength": 100},
        "tool_description": {"type": "string", "maxLength": 500},
    }
    internal = [
        ToolMetaResponse(
            tool_id=t.tool_id,
            name=t.name,
            description=t.description,
            configurable=t.tool_id in configurable_tools,
            config_schema=rag_config_schema if t.tool_id in configurable_tools else None,
        )
        for t in get_all_tools()
    ]

    # 2. DB 등록 MCP 도구 메타 (연결 없이 DB 조회만)
    mcp_registrations = await load_mcp_use_case.list_meta(request_id)
    mcp = [
        ToolMetaResponse(
            tool_id=r.tool_id, name=r.name, description=r.description
        )
        for r in mcp_registrations
    ]

    return AvailableToolsResponse(tools=internal + mcp)


@router.get("", response_model=ListAgentsResponse)
async def list_agents(
    scope: str = Query("all", pattern="^(mine|department|public|all)$"),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_agents_use_case),
):
    """에이전트 목록 조회 (scope 기반 필터링)."""
    request_id = str(uuid.uuid4())
    request = ListAgentsRequest(scope=scope, search=search, page=page, size=size)
    return await use_case.execute(
        viewer_user_id=str(current_user.id),
        viewer_role=current_user.role.value,
        request=request,
        request_id=request_id,
    )


@router.post("", response_model=CreateAgentResponse, status_code=201)
async def create_agent(
    body: CreateAgentRequest,
    use_case=Depends(get_create_agent_use_case),
):
    """에이전트 생성 (LLM이 도구 자동 선택 + 시스템 프롬프트 자동 생성)."""
    request_id = str(uuid.uuid4())
    return await use_case.execute(body, request_id)


@router.get("/{agent_id}", response_model=GetAgentResponse)
async def get_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_get_agent_use_case),
):
    """에이전트 정의 조회."""
    request_id = str(uuid.uuid4())
    result = await use_case.execute(
        agent_id,
        request_id,
        viewer_user_id=str(current_user.id),
        viewer_role=current_user.role.value,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return result


@router.patch("/{agent_id}", response_model=UpdateAgentResponse)
async def update_agent(
    agent_id: str,
    body: UpdateAgentRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_update_agent_use_case),
):
    """에이전트 시스템 프롬프트 / 이름 수정."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, body, request_id,
            viewer_user_id=str(current_user.id),
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="수정 권한 없음"
        )
    except ValueError as e:
        msg = str(e)
        if "찾을 수 없" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)


@router.post("/{agent_id}/run", response_model=RunAgentResponse)
async def run_agent(
    agent_id: str,
    body: RunAgentRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_run_agent_use_case),
):
    """에이전트 실행 (DB에서 워크플로우 로드 → LangGraph 동적 컴파일 → 응답)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id,
            body,
            request_id,
            viewer_user_id=str(current_user.id),
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="실행 권한 없음"
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_delete_agent_use_case),
):
    """에이전트 소프트 삭제."""
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(
            agent_id=agent_id,
            viewer_user_id=str(current_user.id),
            viewer_role=current_user.role.value,
            request_id=request_id,
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="삭제 권한 없음"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


# ── Human-in-the-Loop 인터뷰 엔드포인트 ──────────────────────────


@router.post("/interview", response_model=InterviewStartResponse, status_code=201)
async def start_interview(
    body: InterviewStartRequest,
    use_case=Depends(get_interview_use_case),
):
    """인터뷰 시작 — LLM이 에이전트 설계를 위한 명확화 질문 생성."""
    request_id = str(uuid.uuid4())
    return await use_case.start(body, request_id)


@router.post(
    "/interview/{session_id}/answer",
    response_model=InterviewAnswerResponse,
)
async def answer_interview(
    session_id: str,
    body: InterviewAnswerRequest,
    use_case=Depends(get_interview_use_case),
):
    """질문 답변 제출 — 추가 질문 반환 또는 에이전트 초안 미리보기 반환."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.answer(session_id, body, request_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/interview/{session_id}/finalize",
    response_model=CreateAgentResponse,
    status_code=201,
)
async def finalize_interview(
    session_id: str,
    body: InterviewFinalizeRequest,
    use_case=Depends(get_interview_use_case),
):
    """에이전트 초안 확정 — 시스템 프롬프트 수정(선택) 후 DB 저장."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.finalize(session_id, body, request_id)
    except ValueError as e:
        msg = str(e)
        if "세션" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
