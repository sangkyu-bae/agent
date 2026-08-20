"""파이프라인 이벤트/결과 DTO — Design §3.1.

UseCase 의 async generator 가 yield 하는 두 타입. 라우터가 소비 방식만 바꾼다:
동기 POST 는 마지막 PipelineOutcome 만, SSE 는 StageEvent 를 실시간 송출 —
같은 제너레이터를 공유하므로 두 경로의 결과 의미가 구조적으로 동일하다 (FR-15).
"""
from dataclasses import dataclass
from typing import Literal

from src.domain.agent_create_pipeline.stages import StageRecord
from src.domain.intent.schemas import IntentResult, SlotQuestion

EventKind = Literal["stage_started", "stage_completed", "stage_failed"]


@dataclass(frozen=True)
class StageEvent:
    """단계 진행 이벤트 — SSE 로 그대로 흘러간다.

    stage_started 의 record 는 진행 표시용이며 status 는 의미가 없다.
    stage_failed 는 UseCase 가 만들지 않는다 — 예외는 전파되고(§6.2),
    SSE 라우터가 마지막 started 기록으로 합성한다 (module-3).
    """

    kind: EventKind
    record: StageRecord


@dataclass(frozen=True)
class PipelineOutcome:
    """제너레이터의 마지막 yield — 동기 응답/SSE 최종 이벤트의 본문."""

    status: Literal["need_input", "created"]
    steps: tuple[StageRecord, ...]
    """항상 5단계 전체 (PipelinePolicy.finalize_steps 계약)."""

    questions: tuple[SlotQuestion, ...] = ()
    round: int = 0
    """need_input 이면 '다음 재호출에 실을 round', created 면 이번 라운드."""

    intent: IntentResult | None = None
    recommended_tool_ids: tuple[str, ...] = ()
    final_tool_ids: tuple[str, ...] = ()
    unknown_tool_ids: tuple[str, ...] = ()
    """카탈로그에 없거나 비활성이라 프롬프트에 반영되지 않은 tool_id (FR-03 에코백)."""
    session_id: str | None = None
    version_id: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    assembled_prompt: str | None = None
    """에이전트에 실제 저장된 프롬프트 (4000자 clamp 반영값)."""

    bind_ok: bool | None = None
