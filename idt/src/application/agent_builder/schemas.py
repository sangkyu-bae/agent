"""애플리케이션 레이어 요청/응답 스키마."""
from pydantic import BaseModel, Field


class WorkerInfo(BaseModel):
    tool_id: str
    worker_id: str
    description: str
    sort_order: int


class CreateAgentRequest(BaseModel):
    user_request: str = Field(..., max_length=1000)
    name: str = Field(..., max_length=200)
    user_id: str
    llm_model_id: str | None = None
    visibility: str = Field("private", pattern="^(private|department|public)$")
    department_id: str | None = None
    temperature: float = Field(0.70, ge=0.0, le=2.0)


class CreateAgentResponse(BaseModel):
    agent_id: str
    name: str
    system_prompt: str
    tool_ids: list[str]
    workers: list[WorkerInfo]
    flow_hint: str
    llm_model_id: str
    visibility: str
    department_id: str | None = None
    temperature: float
    created_at: str


class UpdateAgentRequest(BaseModel):
    system_prompt: str | None = Field(None, max_length=4000)
    name: str | None = Field(None, max_length=200)
    visibility: str | None = Field(None, pattern="^(private|department|public)$")
    department_id: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)


class UpdateAgentResponse(BaseModel):
    agent_id: str
    name: str
    system_prompt: str
    updated_at: str


class GetAgentResponse(BaseModel):
    agent_id: str
    name: str
    description: str
    system_prompt: str
    tool_ids: list[str]
    workers: list[WorkerInfo]
    flow_hint: str
    llm_model_id: str
    status: str
    visibility: str
    department_id: str | None = None
    department_name: str | None = None
    temperature: float
    owner_user_id: str
    can_edit: bool
    can_delete: bool
    created_at: str
    updated_at: str


class RunAgentRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    user_id: str


class RunAgentResponse(BaseModel):
    agent_id: str
    query: str
    answer: str
    tools_used: list[str]
    request_id: str


class ToolMetaResponse(BaseModel):
    tool_id: str
    name: str
    description: str


class AvailableToolsResponse(BaseModel):
    tools: list[ToolMetaResponse]


# ── Human-in-the-Loop Interview ─────────────────────────────────

class InterviewStartRequest(BaseModel):
    user_request: str = Field(..., max_length=1000)
    name: str = Field(..., max_length=200)
    user_id: str
    llm_model_id: str | None = None


class InterviewStartResponse(BaseModel):
    session_id: str
    questions: list[str]
    guidance: str = "아래 질문에 답해주시면 더 정확한 에이전트를 만들 수 있습니다."


class AgentDraftPreview(BaseModel):
    tool_ids: list[str]
    workers: list[WorkerInfo]
    flow_hint: str
    system_prompt: str  # LLM 자동 생성, 수정 가능


class InterviewAnswerRequest(BaseModel):
    answers: list[str] = Field(..., description="현재 질문 목록에 대한 순서대로의 답변")


class InterviewAnswerResponse(BaseModel):
    session_id: str
    status: str  # "questioning" | "reviewing"
    questions: list[str] | None = None   # status == "questioning"
    preview: AgentDraftPreview | None = None  # status == "reviewing"


class InterviewFinalizeRequest(BaseModel):
    system_prompt: str | None = Field(None, max_length=4000, description="None이면 자동 생성된 프롬프트 사용")


# ── List / Delete ─────────────────────────────────────────────────


class ListAgentsRequest(BaseModel):
    scope: str = Field("all", pattern="^(mine|department|public|all)$")
    search: str | None = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class AgentSummary(BaseModel):
    agent_id: str
    name: str
    description: str
    visibility: str
    department_name: str | None = None
    owner_user_id: str
    owner_email: str | None = None
    temperature: float
    can_edit: bool
    can_delete: bool
    created_at: str


class ListAgentsResponse(BaseModel):
    agents: list[AgentSummary]
    total: int
    page: int
    size: int
