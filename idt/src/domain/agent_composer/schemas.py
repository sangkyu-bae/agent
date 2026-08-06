"""agent_composer 도메인 VO — 외부 의존 없음(순수 dataclass)."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CandidateTool:
    """LLM 조합 후보 도구 메타.

    tool_id 형태:
    - 내부 도구: "excel_export" (TOOL_REGISTRY 키)
    - MCP 개별 도구(tool_catalog): "mcp:{server_id}:{tool_name}"
    - MCP 서버 단위 폴백(D2): "mcp_{server_id}"
    """

    tool_id: str
    name: str
    description: str
    source: str  # "internal" | "mcp"
    mcp_server_id: str | None = None
    server_level: bool = False


@dataclass(frozen=True)
class MissingCapability:
    """요청 역량 중 현재 도구로 커버할 수 없는 항목."""

    capability: str
    reason: str
    suggestion: str = ""


@dataclass(frozen=True)
class ToolDirectionHint:
    """계획의 역량→도구 방향 힌트 (fix-agent-planner-hitl D5).

    확정 선택이 아니다 — 최종 도구 결정·검증은 Composer와 서버 보정이 수행한다.
    """

    capability: str
    suggested_tool_ids: list[str]
    note: str = ""


@dataclass(frozen=True)
class ClarifyingQuestion:
    """HITL 구조화 질문. options가 비면 자유 입력 전용."""

    id: str
    question: str
    options: list[str]
    allow_free_text: bool = True


@dataclass(frozen=True)
class ClarificationAnswer:
    """사용자 답변. answer==""는 무응답(부분 답변 허용).

    question 텍스트는 stateless 재구성용 에코백이다(D8) — 서버 세션이 없으므로
    요청만으로 이전 Q/A 맥락을 복원한다.
    """

    question_id: str
    question: str
    answer: str = ""


@dataclass(frozen=True)
class BuildPlan:
    """Planner 산출 빌드 계획 — Composer 프롬프트 주입 단위."""

    requirement_summary: str
    tool_hints: list[ToolDirectionHint]
    plan_summary: str
    confidence: float


@dataclass(frozen=True)
class ComposedDraft:
    """초안 조립 결과 — 응답 조립의 입력."""

    coverage: str  # "full" | "partial" | "none"
    name_suggestion: str
    system_prompt: str
    workers: list  # list[WorkerDefinition]
    flow_hint: str
    missing_capabilities: list[MissingCapability] = field(default_factory=list)
    notes: str = ""
