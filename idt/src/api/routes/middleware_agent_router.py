"""미들웨어 에이전트 빌더 라우터 (/api/v2/agents)."""
from fastapi import APIRouter, Depends

from src.application.middleware_agent.create_middleware_agent_use_case import CreateMiddlewareAgentUseCase
from src.application.middleware_agent.get_middleware_agent_use_case import GetMiddlewareAgentUseCase
from src.application.middleware_agent.run_middleware_agent_use_case import RunMiddlewareAgentUseCase
from src.application.middleware_agent.schemas import (
    CreateMiddlewareAgentRequest,
    CreateMiddlewareAgentResponse,
    GetMiddlewareAgentResponse,
    RunMiddlewareAgentRequest,
    RunMiddlewareAgentResponse,
    UpdateMiddlewareAgentRequest,
)
from src.application.middleware_agent.update_middleware_agent_use_case import UpdateMiddlewareAgentUseCase
from src.domain.agent_builder.tool_registry import get_all_tools

router = APIRouter(prefix="/api/v2/agents", tags=["middleware-agent"])


# DI placeholders → main.py에서 dependency_overrides로 교체
def get_create_use_case() -> CreateMiddlewareAgentUseCase:
    raise NotImplementedError

def get_get_use_case() -> GetMiddlewareAgentUseCase:
    raise NotImplementedError

def get_run_use_case() -> RunMiddlewareAgentUseCase:
    raise NotImplementedError

def get_update_use_case() -> UpdateMiddlewareAgentUseCase:
    raise NotImplementedError


@router.get("/tools")
async def list_tools():
    """사용 가능한 도구 목록 (AGENT-004 tool_registry 재사용)."""
    return {
        "tools": [
            {"tool_id": t.tool_id, "name": t.name, "description": t.description}
            for t in get_all_tools()
        ]
    }


@router.post("", response_model=CreateMiddlewareAgentResponse, status_code=201)
async def create_agent(
    request: CreateMiddlewareAgentRequest,
    use_case: CreateMiddlewareAgentUseCase = Depends(get_create_use_case),
):
    return await use_case.execute(request)


@router.get("/{agent_id}", response_model=GetMiddlewareAgentResponse)
async def get_agent(
    agent_id: str,
    request_id: str = "no-request-id",
    use_case: GetMiddlewareAgentUseCase = Depends(get_get_use_case),
):
    return await use_case.execute(agent_id, request_id=request_id)


@router.patch("/{agent_id}", response_model=GetMiddlewareAgentResponse)
async def update_agent(
    agent_id: str,
    request: UpdateMiddlewareAgentRequest,
    use_case: UpdateMiddlewareAgentUseCase = Depends(get_update_use_case),
):
    return await use_case.execute(agent_id, request)


@router.post("/{agent_id}/run", response_model=RunMiddlewareAgentResponse)
async def run_agent(
    agent_id: str,
    request: RunMiddlewareAgentRequest,
    use_case: RunMiddlewareAgentUseCase = Depends(get_run_use_case),
):
    return await use_case.execute(agent_id, request)
