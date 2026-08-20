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


class PipelineStop(StrEnum):
    """위저드 정지 지점 — 요청 `stop_after` 의 wire 계약.

    agent-create-wizard Design Ref: §3.1.

    값은 `PipelineStage` 와 **의도적으로 동일한 문자열**이다: "어느 단계 직후에
    멈출 것인가"를 표현하므로 별도 이름 체계를 두면 매핑 표가 하나 더 생긴다.
    `PipelinePolicy` 가 이 동일성에 의존한다 (test_stages 가 고정).

    create/bind 는 정지 지점이 될 수 없다 — 생성 뒤에 멈춰봐야 되돌릴 수 없고,
    위저드는 애초에 생성 전에 끝난다.
    """

    TOOLS = "tools"
    PROMPT = "prompt"


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
