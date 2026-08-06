"""agent_composer 애플리케이션 인터페이스 — Planner 교체 지점 (fix-agent-planner-hitl D2/D9).

PlannerInterface는 파라미터가 application DTO(ComposeCurrentConfig)를 포함하므로
domain이 아닌 application 레이어 Protocol로 둔다. UseCase는 이 Protocol에만
의존하고 main.py DI가 구현(AgentPlanner 등)을 바인딩한다 — 추후 LangGraph
interrupt 기반 구현체로 DI 교체만으로 대체 가능.
"""
from typing import NamedTuple, Protocol

from src.application.agent_composer.schemas import ComposeCurrentConfig
from src.domain.agent_composer.schemas import (
    BuildPlan,
    CandidateTool,
    ClarificationAnswer,
    ClarifyingQuestion,
)


class PlanResult(NamedTuple):
    """Planner 산출 — 빌드 계획 + (있다면) 보충 질문."""

    plan: BuildPlan
    questions: list[ClarifyingQuestion]


class PlannerInterface(Protocol):
    async def plan(
        self,
        user_request: str,
        candidates: list[CandidateTool],
        request_id: str,
        current_config: ComposeCurrentConfig | None = None,
        history: list[dict] | None = None,
        answers: list[ClarificationAnswer] | None = None,
        round_: int = 0,
    ) -> PlanResult: ...
