"""agent-create-pipeline API 스키마 — Design §4.2/§4.3.

steps 는 항상 5단계 전체(고정 순서)로 직렬화된다 — 화면이 단계 바를 고정
렌더하는 계약 (§5). degraded_stages 는 steps 에서 파생되는 편의 필드다.
"""
from typing import Literal

from pydantic import BaseModel, Field


class PipelineTurnIn(BaseModel):
    """대화 이력 1턴 (intent/compose 의 Turn 계약과 동일)."""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class PipelineAnswerIn(BaseModel):
    """되묻기 답변 에코백 — stateless 왕복 (Design §2.2)."""

    slot_key: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)


class IntentEchoIn(BaseModel):
    """확정된 의도 에코백 (agent-create-wizard §4.2 / D2).

    `IntentSummaryOut` 을 그대로 되돌려 보내는 형태다 — 서버가 자신이 낸
    산출물을 다시 받는 stateless HITL 관례와 같은 계열.

    `complete`/`missing_slots` 는 **받지 않는다**: 계산 필드를 외부 입력으로
    받으면 오염값이 판정을 뒤집는다. 서버가 spec 으로 재계산한다.
    """

    label: str | None = Field(None, max_length=100)
    filled_slots: dict[str, str] = Field(default_factory=dict)
    degraded: bool = False


class AgentPipelineRequest(BaseModel):
    """두 엔드포인트(동기/SSE) 공용 요청. 검증 규칙: Design §4.2."""

    user_request: str = Field(..., min_length=1, max_length=1000)
    # prompt_composer 요청 스키마와 동일 상한 — 다운스트림 절단(20턴)과 별개로
    # 요청 파싱 비용을 상한한다 (Analysis G-08)
    history: list[PipelineTurnIn] = Field(default_factory=list, max_length=20)
    answers: list[PipelineAnswerIn] = Field(default_factory=list)
    round: int = Field(0, ge=0)
    tool_ids: list[str] = Field(default_factory=list, max_length=50)
    name: str | None = Field(None, max_length=200)
    llm_model_id: str | None = None
    session_id: str | None = None

    # --- agent-create-wizard §4.2 (위저드 전용, 전부 no-op 기본값) ---
    stop_after: Literal["tools", "prompt"] | None = None
    """지정 단계 직후 정지. 미지정이면 기존 논스톱 실행과 완전히 동일하다."""

    tools_confirmed: bool = False
    """true 면 `tool_ids` 가 사용자 확정 목록이므로 셀렉터를 돌리지 않는다 (D1)."""

    intent: IntentEchoIn | None = None
    """확정된 의도 재사용. 서버가 spec 으로 재검증한 뒤에만 신뢰한다 (D2)."""


class StageRecordOut(BaseModel):
    """단계 1개의 wire 표현 — steps[] 원소이자 SSE 이벤트 payload."""

    stage: str
    status: str
    reason: str | None = None
    elapsed_ms: int = 0


class QuestionOut(BaseModel):
    slot_key: str
    question: str
    options: list[str] = Field(default_factory=list)
    allow_free_text: bool = True


class IntentSummaryOut(BaseModel):
    """화면 표시용 의도 요약 — 판정 원본 전체를 노출하지 않는다."""

    label: str | None = None
    filled_slots: dict[str, str] = Field(default_factory=dict)
    missing_slots: list[str] = Field(default_factory=list)
    degraded: bool = False


class AgentPipelineResponse(BaseModel):
    """동기 200 응답 = SSE 최종 이벤트 payload (FR-15)."""

    status: Literal["need_input", "tools_proposed", "prompt_ready", "created"]
    round: int = 0
    steps: list[StageRecordOut]
    degraded_stages: list[str] = Field(default_factory=list)
    questions: list[QuestionOut] = Field(default_factory=list)
    intent: IntentSummaryOut | None = None
    recommended_tool_ids: list[str] = Field(default_factory=list)
    final_tool_ids: list[str] = Field(default_factory=list)
    # 카탈로그에 없거나 비활성이라 반영되지 않은 tool_id 에코백 (Plan FR-03)
    unknown_tool_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None
    version_id: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    assembled_prompt: str | None = None
    bind_ok: bool | None = None
    # --- agent-create-wizard §4.3 (정지 응답 전용, optional) ---
    suggested_name: str | None = None
    prompt_clamp_reason: str | None = None
