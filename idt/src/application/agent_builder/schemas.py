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
    model_name: str = "gpt-4o-mini"


class CreateAgentResponse(BaseModel):
    agent_id: str
    name: str
    system_prompt: str
    tool_ids: list[str]
    workers: list[WorkerInfo]
    flow_hint: str
    model_name: str
    created_at: str


class UpdateAgentRequest(BaseModel):
    system_prompt: str | None = Field(None, max_length=4000)
    name: str | None = Field(None, max_length=200)


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
    model_name: str
    status: str
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
    model_name: str = "gpt-4o-mini"


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
