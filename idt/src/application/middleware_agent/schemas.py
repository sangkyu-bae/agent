"""Request / Response Pydantic 모델."""
from pydantic import BaseModel, Field


class MiddlewareConfigRequest(BaseModel):
    type: str = Field(..., description="summarization|pii|tool_retry|model_call_limit|model_fallback")
    config: dict = Field(default_factory=dict)
    sort_order: int = 0


class CreateMiddlewareAgentRequest(BaseModel):
    user_id: str
    name: str
    description: str
    system_prompt: str
    model_name: str = "gpt-4o"
    tool_ids: list[str]
    middleware: list[MiddlewareConfigRequest] = Field(default_factory=list)
    request_id: str


class CreateMiddlewareAgentResponse(BaseModel):
    agent_id: str
    name: str
    middleware_count: int
    status: str


class RunMiddlewareAgentRequest(BaseModel):
    query: str
    request_id: str


class RunMiddlewareAgentResponse(BaseModel):
    answer: str
    tools_used: list[str]
    middleware_applied: list[str]


class UpdateMiddlewareAgentRequest(BaseModel):
    system_prompt: str | None = None
    name: str | None = None
    middleware: list[MiddlewareConfigRequest] | None = None
    request_id: str


class GetMiddlewareAgentResponse(BaseModel):
    agent_id: str
    name: str
    description: str
    system_prompt: str
    model_name: str
    tool_ids: list[str]
    middleware: list[MiddlewareConfigRequest]
    status: str
