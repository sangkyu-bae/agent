"""Agent Builder Router: 에이전트 생성/조회/수정/실행 API.

agent-run-streaming-sse Design §5.5 (2026-05-24):
GET /{agent_id}/run/stream — SSE 엔드포인트. RunAgentUseCase.stream()의
AgentRunEvent를 EventSource API 호환 wire 라인으로 송출.
"""
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from src.domain.auth.entities import User
from src.infrastructure.agent_run.sse_formatter import AgentRunEventSseFormatter
from src.domain.agent_run.auth_context import AuthContext
from src.interfaces.dependencies.auth import (
    get_current_user,
    get_current_user_from_query_token,
    get_auth_context,
    get_auth_context_from_query_token,
)

from src.application.agent_builder.schemas import (
    AvailableSubAgentsResponse,
    AvailableToolsResponse,
    CreateAgentRequest,
    CreateAgentResponse,
    ForkAgentRequest,
    ForkAgentResponse,
    ForkStatsResponse,
    GetAgentResponse,
    ListAgentsRequest,
    ListAgentsResponse,
    ListMyAgentsResponse,
    RunAgentRequest,
    RunAgentResponse,
    SubscribeResponse,
    ToolMetaResponse,
    UpdateAgentRequest,
    UpdateAgentResponse,
    UpdateSubscriptionRequest,
    WorkerInfo,
)

from src.application.agent_skill.schemas import (
    AttachSkillRequest,
    AttachSkillResponse,
    ListAttachedSkillsResponse,
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


def get_load_mcp_tools_use_case():
    raise NotImplementedError


def get_list_agents_use_case():
    raise NotImplementedError


def get_delete_agent_use_case():
    raise NotImplementedError


def get_subscribe_use_case():
    raise NotImplementedError


def get_fork_agent_use_case():
    raise NotImplementedError


def get_list_my_agents_use_case():
    raise NotImplementedError


def get_list_available_sub_agents_use_case():
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
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_create_agent_use_case),
):
    """에이전트 생성 (LLM이 도구 자동 선택 + 시스템 프롬프트 자동 생성)."""
    request_id = str(uuid.uuid4())
    body.user_id = str(current_user.id)
    try:
        return await use_case.execute(
            body, request_id, viewer_role=current_user.role.value
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise _attach_skill_http_error(e)


@router.get("/my", response_model=ListMyAgentsResponse)
async def list_my_agents(
    filter: str = Query("all", pattern="^(all|owned|subscribed|forked)$"),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_my_agents_use_case),
):
    """내 에이전트 통합 목록 (소유+구독+포크)."""
    request_id = str(uuid.uuid4())
    return await use_case.execute(
        user_id=str(current_user.id),
        filter_type=filter,
        search=search,
        page=page,
        size=size,
        request_id=request_id,
    )


@router.get("/available-sub-agents", response_model=AvailableSubAgentsResponse)
async def list_available_sub_agents(
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_available_sub_agents_use_case),
):
    """서브 에이전트로 사용 가능한 에이전트 목록 (본인 소유 + 전체공개 + 부서공개)."""
    request_id = str(uuid.uuid4())
    return await use_case.execute(
        user_id=str(current_user.id),
        request_id=request_id,
    )


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
            viewer_role=current_user.role.value,
        )
    except PermissionError as e:
        # kb-rag-filter Act-1: KB 읽기권한 거부 등 원인별 메시지를 그대로 노출
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e) or "수정 권한 없음",
        )
    except ValueError as e:
        msg = str(e)
        if "찾을 수 없" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if ("이미 부착" in msg) or ("최대" in msg):
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=422, detail=msg)


@router.post("/{agent_id}/run", response_model=RunAgentResponse)
async def run_agent(
    agent_id: str,
    body: RunAgentRequest,
    auth_ctx: AuthContext = Depends(get_auth_context),
    use_case=Depends(get_run_agent_use_case),
):
    """에이전트 실행 (DB에서 워크플로우 로드 → LangGraph 동적 컴파일 → 응답)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id,
            body,
            request_id,
            auth_ctx=auth_ctx,
            viewer_user_id=str(auth_ctx.user_id),
            viewer_department_ids=list(auth_ctx.department_ids),
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="실행 권한 없음"
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


_SSE_HEARTBEAT_INTERVAL_SEC = 15.0


@router.get(
    "/{agent_id}/run/stream",
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def run_agent_stream(
    agent_id: str,
    request: Request,
    query: str = Query(..., min_length=1, max_length=2000),
    user_id: str = Query(...),
    session_id: str | None = Query(None),
    auth_ctx: AuthContext = Depends(get_auth_context_from_query_token),
    use_case=Depends(get_run_agent_use_case),
):
    """에이전트 실행 (SSE 스트리밍).

    이벤트 시퀀스: run_started → (node_*|tool_*|token)* → answer_completed
    → run_completed | run_failed
    """
    if user_id != str(auth_ctx.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user_id mismatch with token sub",
        )

    request_id = str(uuid.uuid4())
    body = RunAgentRequest(query=query, user_id=user_id, session_id=session_id)
    formatter = AgentRunEventSseFormatter

    async def _generator():
        last_seq = 0
        aiter = use_case.stream(
            agent_id, body, request_id,
            auth_ctx=auth_ctx,
            viewer_user_id=str(auth_ctx.user_id),
            viewer_department_ids=list(auth_ctx.department_ids),
        ).__aiter__()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        aiter.__anext__(),
                        timeout=_SSE_HEARTBEAT_INTERVAL_SEC,
                    )
                except asyncio.TimeoutError:
                    yield formatter.format_heartbeat()
                    continue
                except StopAsyncIteration:
                    break
                last_seq = event.seq
                yield formatter.format(event)
        except ValueError as e:
            yield formatter.format_error(
                "AGENT_NOT_FOUND", str(e), last_seq + 1,
            )
        except PermissionError as e:
            yield formatter.format_error(
                "PERMISSION_DENIED", str(e), last_seq + 1,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            yield formatter.format_error(
                "STREAM_GENERATOR_FAILED", str(e)[:512], last_seq + 1,
            )

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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


# ── 구독 / 포크 엔드포인트 ──────────────────────────────────────


@router.post(
    "/{agent_id}/subscribe",
    response_model=SubscribeResponse,
    status_code=201,
)
async def subscribe_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_subscribe_use_case),
):
    """에이전트 구독."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.subscribe(
            agent_id=agent_id,
            user_id=str(current_user.id),
            viewer_department_ids=current_user.department_ids
            if hasattr(current_user, "department_ids")
            else [],
            request_id=request_id,
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="접근 권한 없음"
        )
    except ValueError as e:
        msg = str(e)
        if "이미 구독" in msg:
            raise HTTPException(status_code=409, detail=msg)
        if "자신의" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=404, detail=msg)


@router.delete(
    "/{agent_id}/subscribe",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unsubscribe_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_subscribe_use_case),
):
    """구독 해제."""
    request_id = str(uuid.uuid4())
    try:
        await use_case.unsubscribe(
            agent_id=agent_id,
            user_id=str(current_user.id),
            request_id=request_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch(
    "/{agent_id}/subscribe",
    response_model=SubscribeResponse,
)
async def update_subscription(
    agent_id: str,
    body: UpdateSubscriptionRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_subscribe_use_case),
):
    """구독 설정 변경 (즐겨찾기)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.update_pin(
            agent_id=agent_id,
            user_id=str(current_user.id),
            is_pinned=body.is_pinned,
            request_id=request_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{agent_id}/fork",
    response_model=ForkAgentResponse,
    status_code=201,
)
async def fork_agent(
    agent_id: str,
    body: ForkAgentRequest | None = None,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_fork_agent_use_case),
):
    """에이전트 포크 (전체 복사)."""
    request_id = str(uuid.uuid4())
    custom_name = body.name if body else None
    try:
        return await use_case.execute(
            source_agent_id=agent_id,
            user_id=str(current_user.id),
            custom_name=custom_name,
            viewer_department_ids=current_user.department_ids
            if hasattr(current_user, "department_ids")
            else [],
            request_id=request_id,
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="접근 권한 없음"
        )
    except ValueError as e:
        msg = str(e)
        if "자신의" in msg:
            raise HTTPException(status_code=400, detail=msg)
        if "삭제된" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=404, detail=msg)


@router.get(
    "/{agent_id}/forks",
    response_model=ForkStatsResponse,
)
async def get_fork_stats(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_my_agents_use_case),
):
    """포크 통계 (원본 소유자 전용)."""
    from src.application.agent_builder.fork_agent_use_case import ForkAgentUseCase

    request_id = str(uuid.uuid4())
    agent_repo = use_case._agent_repo
    agent = await agent_repo.find_by_id(agent_id, request_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다")
    if agent.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="원본 소유자만 조회 가능")

    fork_count = await agent_repo.count_forks(agent_id, request_id)
    subscriber_count = await agent_repo.count_subscribers(agent_id, request_id)
    return ForkStatsResponse(
        agent_id=agent_id,
        fork_count=fork_count,
        subscriber_count=subscriber_count,
    )


# ── Skill 부착 (skill-agent-integration Phase A) ──────────────────

def get_attach_skill_use_case():
    raise NotImplementedError


def get_detach_skill_use_case():
    raise NotImplementedError


def get_list_attached_skills_use_case():
    raise NotImplementedError


def _attach_skill_http_error(e: ValueError) -> HTTPException:
    msg = str(e)
    if "찾을 수 없" in msg:
        return HTTPException(status_code=404, detail=msg)
    if ("이미 부착" in msg) or ("최대" in msg):
        return HTTPException(status_code=409, detail=msg)
    return HTTPException(status_code=422, detail=msg)


@router.get("/{agent_id}/skills", response_model=ListAttachedSkillsResponse)
async def list_attached_skills(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_attached_skills_use_case),
):
    """에이전트에 부착된 Skill 목록 조회."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, request_id,
            viewer_user_id=str(current_user.id),
            viewer_role=current_user.role.value,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{agent_id}/skills",
    response_model=AttachSkillResponse,
    status_code=201,
)
async def attach_skill(
    agent_id: str,
    body: AttachSkillRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_attach_skill_use_case),
):
    """에이전트에 Skill 부착 (instruction만 주입, script는 실행되지 않음)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, body.skill_id, request_id,
            viewer_user_id=str(current_user.id),
            viewer_role=current_user.role.value,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise _attach_skill_http_error(e)


@router.delete("/{agent_id}/skills/{skill_id}", status_code=204)
async def detach_skill(
    agent_id: str,
    skill_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_detach_skill_use_case),
):
    """에이전트에서 Skill 부착 해제 (멱등)."""
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(
            agent_id, skill_id, request_id,
            viewer_user_id=str(current_user.id),
            viewer_role=current_user.role.value,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
