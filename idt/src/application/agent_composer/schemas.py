"""agent_composer 애플리케이션 요청/응답 스키마."""
from typing import Literal

from pydantic import BaseModel, Field

from src.application.agent_builder.schemas import WorkerInfo


class ComposeCurrentConfig(BaseModel):
    """증분 수정용 현재 폼 스냅샷 (fix-agent-composer). 모두 optional — 빈 폼 허용."""

    name: str | None = Field(None, max_length=200)
    system_prompt: str | None = Field(None, max_length=4000)
    tool_ids: list[str] = Field(default_factory=list, max_length=10)
    llm_model_id: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)


class ComposeHistoryTurn(BaseModel):
    """Fix 채팅 이전 대화 턴. 서버가 최근 6턴·500자로 재절단한다(ComposePolicy)."""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2000)


class ClarificationAnswerDto(BaseModel):
    """HITL 질문 답변 (fix-agent-planner-hitl). answer==""는 무응답(부분 답변).

    question 텍스트는 stateless 재구성용 에코백(D8) — 서버가 세션 없이
    요청만으로 이전 Q/A 맥락을 복원한다.
    """

    question_id: str = Field(..., max_length=50)
    question: str = Field(..., min_length=1, max_length=500)
    answer: str = Field("", max_length=1000)


class ClarifyingQuestionDto(BaseModel):
    """HITL 구조화 질문 — 선택지+자유 입력 허용 플래그."""

    id: str
    question: str
    options: list[str] = Field(default_factory=list)
    allow_free_text: bool = True


class ComposeAgentRequest(BaseModel):
    """자연어 → 에이전트 초안 조합 요청."""

    user_request: str = Field(..., min_length=1, max_length=1000)
    name: str | None = Field(None, max_length=200)  # 없으면 LLM 제안 사용
    llm_model_id: str | None = None
    # fix-agent-composer: 증분 수정 컨텍스트 (미전송 시 기존 단발성 동작과 동일)
    current_config: ComposeCurrentConfig | None = None
    history: list[ComposeHistoryTurn] | None = Field(None, max_length=20)
    # fix-agent-planner-hitl: HITL 왕복 (미전송 시 기존 동작과 동일한 opt-in 계약)
    clarification_answers: list[ClarificationAnswerDto] | None = Field(
        None, max_length=6
    )
    clarification_round: int = Field(0, ge=0, le=10)  # 서버가 정책으로 재clamp


class MissingCapabilityDto(BaseModel):
    capability: str
    reason: str
    suggestion: str = ""


class ComposeAgentDraftResponse(BaseModel):
    """에이전트 초안 (무저장) — CreateAgentRequest 프리필 호환.

    coverage=="none"이면 초안 필드(tool_ids/workers/system_prompt/flow_hint)는
    빈 값이고 missing_capabilities/notes만 채워진다.

    fix-agent-planner-hitl: status=="needs_clarification"이면 questions가
    채워지고 초안 필드는 빈 값 + coverage=="none" (status를 모르는 구형
    소비자의 안전 강하, D7).
    """

    status: Literal["draft", "needs_clarification"] = "draft"
    questions: list[ClarifyingQuestionDto] = Field(default_factory=list)
    plan_summary: str = ""
    coverage: str  # "full" | "partial" | "none"
    name_suggestion: str = ""
    system_prompt: str = ""
    tool_ids: list[str] = Field(default_factory=list)  # mcp_* 포함, 저장 호환
    workers: list[WorkerInfo] = Field(default_factory=list)
    flow_hint: str = ""
    llm_model_id: str = ""
    temperature: float = 0.70
    missing_capabilities: list[MissingCapabilityDto] = Field(default_factory=list)
    notes: str = ""
