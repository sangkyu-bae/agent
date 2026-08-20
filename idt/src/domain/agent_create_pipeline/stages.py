"""파이프라인 단계 상태 VO — Design §3.1 / Plan D8.

단계 상태는 1급 계약이다: StageRecord 가 응답 `steps[]` 원소이자 SSE 이벤트
payload 가 된다. Enum 의 .value 문자열은 wire 에 그대로 실리므로 변경은 곧
프론트 계약 파괴다.
"""
from dataclasses import dataclass
from enum import StrEnum


class PipelineStage(StrEnum):
    """고정 5단계. 화면은 이 순서로 단계 바를 렌더한다 (Design §5)."""

    INTENT = "intent"
    TOOLS = "tools"
    PROMPT = "prompt"
    CREATE = "create"
    BIND = "bind"


STAGE_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage.INTENT,
    PipelineStage.TOOLS,
    PipelineStage.PROMPT,
    PipelineStage.CREATE,
    PipelineStage.BIND,
)


class StageStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class StageRecord:
    """단계 1개의 실행 결과.

    reason 은 degraded/failed 사유를 사람이 읽는 한국어로 담는다 — 화면이
    툴팁으로 그대로 노출한다 (Design §5). ok 여도 부가 기록(프롬프트 절단 등)이
    있으면 reason 을 쓴다.
    """

    stage: PipelineStage
    status: StageStatus
    reason: str | None = None
    elapsed_ms: int = 0
