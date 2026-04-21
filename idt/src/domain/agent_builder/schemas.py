"""도메인 스키마: AgentDefinition, WorkerDefinition, WorkflowDefinition, WorkflowSkeleton."""
from dataclasses import dataclass, field
from datetime import datetime

from src.domain.llm_model.entity import LlmModel


@dataclass(frozen=True)
class ToolMeta:
    """도구 메타데이터 (TOOL_REGISTRY 값)."""

    tool_id: str
    name: str
    description: str
    requires_env: list[str] = field(default_factory=list)


@dataclass
class WorkerDefinition:
    """에이전트가 사용할 단일 워커 정의."""

    tool_id: str
    worker_id: str
    description: str
    sort_order: int = 0


@dataclass
class WorkflowSkeleton:
    """ToolSelector 출력: 도구 선택 결과 (시스템 프롬프트 제외)."""

    workers: list[WorkerDefinition]
    flow_hint: str


@dataclass
class WorkflowDefinition:
    """WorkflowCompiler 입력: LangGraph 컴파일 전용 Value Object."""

    supervisor_prompt: str
    workers: list[WorkerDefinition]
    flow_hint: str


@dataclass
class AgentDefinition:
    """에이전트 정의 도메인 객체 (agent_definition + agent_tool JOIN 결과)."""

    id: str
    user_id: str
    name: str
    description: str
    system_prompt: str
    flow_hint: str
    workers: list[WorkerDefinition]
    llm_model_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    visibility: str = "private"
    department_id: str | None = None
    temperature: float = 0.70
    llm_model: LlmModel | None = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError(f"temperature must be 0.0~2.0, got {self.temperature}")
        if self.visibility == "department" and self.department_id is None:
            raise ValueError("department visibility requires department_id")

    def to_workflow_definition(self) -> WorkflowDefinition:
        """LangGraph 컴파일용 Value Object로 변환. workers를 sort_order 기준 정렬."""
        return WorkflowDefinition(
            supervisor_prompt=self.system_prompt,
            workers=sorted(self.workers, key=lambda w: w.sort_order),
            flow_hint=self.flow_hint,
        )

    def apply_update(
        self,
        system_prompt: str | None,
        name: str | None,
        visibility: str | None = None,
        department_id: str | None = None,
        temperature: float | None = None,
    ) -> None:
        """업데이트 적용."""
        if system_prompt is not None:
            self.system_prompt = system_prompt
        if name is not None:
            self.name = name
        if visibility is not None:
            self.visibility = visibility
        if department_id is not None:
            self.department_id = department_id
        if temperature is not None:
            self.temperature = temperature
        self.__post_init__()
