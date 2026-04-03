"""Request / Response Pydantic 모델."""
from typing import Literal
from pydantic import BaseModel


class AutoBuildRequest(BaseModel):
    user_request: str
    user_id: str
    model_name: str = "gpt-4o"
    name: str | None = None
    request_id: str


class AutoBuildReplyRequest(BaseModel):
    answers: list[str]
    request_id: str


class AutoBuildResponse(BaseModel):
    status: Literal["created", "needs_clarification", "failed"]
    session_id: str
    agent_id: str | None = None
    explanation: str | None = None
    tool_ids: list[str] | None = None
    middlewares_applied: list[str] | None = None
    questions: list[str] | None = None
    partial_info: str | None = None


class AutoBuildSessionStatusResponse(BaseModel):
    session_id: str
    status: str
    attempt_count: int
    user_request: str
    created_agent_id: str | None
