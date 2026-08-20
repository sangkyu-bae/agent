"""prompt-composer 요청/응답 스키마.

Design Ref: §4.1~§4.3 · FR-12.

`IntentSnapshot` 이 `extra="allow"` 인 이유(§3.4): 의도 모듈은 사이클마다 필드가
바뀐다. 이 모듈이 읽는 필드는 `degraded`/`label`/`reason` 3개뿐이며 나머지는
해석하지 않고 통과 저장한다. 스키마를 좁게 잡으면 의도 모듈이 자랄 때마다
여기가 함께 깨진다.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain.prompt_composer.schemas import PROMPT_SOURCE_LLM

MAX_USER_REQUEST_CHARS = 1000
MAX_TOOL_IDS = 50
MAX_HISTORY_TURNS = 20
# agent-create-wizard Design Ref: §4.5 — CreateAgentRequest.system_prompt 및
# PipelinePolicy.PROMPT_MAX_CHARS 와 **같은 상한**이다. 여기서 더 받아주면
# 저장 단계에서 422 가 나 사용자가 마지막에 실패한다.
MAX_ASSEMBLED_CHARS = 4000


class HistoryTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(default="", max_length=8000)


class IntentSnapshot(BaseModel):
    """주입된 의도 판정. 알 수 없는 필드도 그대로 보존한다 (§3.4)."""

    model_config = ConfigDict(extra="allow")

    label: str | None = Field(default=None, max_length=100)
    degraded: bool = False
    reason: str = ""


class ComposePromptRequest(BaseModel):
    user_request: str = Field(..., min_length=1, max_length=MAX_USER_REQUEST_CHARS)
    history: list[HistoryTurn] = Field(
        default_factory=list, max_length=MAX_HISTORY_TURNS
    )
    intent: IntentSnapshot | None = None
    tool_ids: list[str] = Field(default_factory=list, max_length=MAX_TOOL_IDS)
    session_id: str | None = Field(default=None, max_length=36)
    agent_id: str | None = Field(default=None, max_length=36)


class RoleOut(BaseModel):
    title: str
    detail: str


class ToolGuideOut(BaseModel):
    tool_id: str
    name: str
    when: str
    how: str
    caution: str


class SectionsOut(BaseModel):
    purpose: str
    roles: list[RoleOut]
    tool_guides: list[ToolGuideOut]
    principles: list[str]


class ComposePromptResponse(BaseModel):
    session_id: str
    version_id: str
    version_no: int
    sections: SectionsOut
    assembled: str
    degraded: bool
    """true 면 LLM 생성 실패로 규칙기반 폴백이 쓰였다. 에러가 아니다 (Plan D6)."""
    reason: str | None
    dropped_tool_ids: list[str]
    unknown_tool_ids: list[str]
    elapsed_ms: int


class VersionSummaryOut(BaseModel):
    """목록용 요약 — `sections` 는 싣지 않는다 (페이로드 비대화 방지, §4.2)."""

    version_id: str
    version_no: int
    degraded: bool
    reason: str | None
    tool_ids: list[str]
    assembled: str
    created_at: datetime
    # agent-create-wizard §3.4 — additive. 구형 소비자는 무시하면 되고,
    # 이 필드가 없으면 목록에서 LLM 생성본과 사람 편집본을 구분할 수 없다.
    source: str = PROMPT_SOURCE_LLM


class PromptSessionResponse(BaseModel):
    session_id: str
    agent_id: str | None
    user_request: str
    created_at: datetime
    versions: list[VersionSummaryOut]


class BindAgentRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=36)


class AppendVersionRequest(BaseModel):
    """사람이 편집한 프롬프트 저장 요청 (agent-create-wizard §4.5)."""

    assembled: str = Field(..., min_length=1, max_length=MAX_ASSEMBLED_CHARS)
    tool_ids: list[str] = Field(default_factory=list, max_length=MAX_TOOL_IDS)


class AppendVersionResponse(BaseModel):
    session_id: str
    version_id: str
    version_no: int
    source: str
    """항상 `human` — LLM 생성본은 이 엔드포인트로 들어올 수 없다."""
