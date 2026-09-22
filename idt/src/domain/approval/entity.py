"""approval-gate 도메인 엔티티/VO.

Design Ref: §3.1 — 부작용 도구의 사람 승인 요청과 런 재개 스냅샷.
시각 규격: 모든 datetime 은 UTC naive (agent_schedule·background_job 관례 동일).

도메인 순수성: langchain·SQLAlchemy·env 를 참조하지 않는다. 상한 상수는
ApprovalPolicy 가 소유하고, 어댑터가 config 에서 읽어 주입한다.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

ApprovalStatus = Literal[
    "pending",    # 적재 직후 — 사람의 결정 대기
    "approved",   # 승인됨 — 집행 경로 확정 전
    "scheduled",  # execute_after 도래 대기
    "executed",   # 집행 완료
    "rejected",   # 거절됨 (사유 필수)
    "expired",    # 만료 — 승인 불가
    "failed",     # 집행 실패 — 자동 재시도 없음 (FR-25)
]

GateMode = Literal["always", "off"]

# 상한 상수는 엔티티가 소유한다 — VO 해석(GateSettings.from_config)이 이 값을
# 쓰므로 policies 에 두면 entity→policies 역참조로 순환 import 가 된다.
# ApprovalPolicy 가 같은 이름으로 재노출해 호출자는 Policy 한 곳만 보면 된다.
DEFAULT_EXPIRES_HOURS = 168  # 7일
MIN_EXPIRES_HOURS = 1
MAX_EXPIRES_HOURS = 720  # 30일
MAX_SNAPSHOT_BYTES = 262_144  # 256KB — 초과 시 messages 절단 후 경고
# Check G13: 예약 집행 cron 을 해석할 기준 타임존. agent_schedule 의
# SchedulePolicy.DEFAULT_TIMEZONE 과 같은 값 — 두 기능이 같은 벽시계를 쓴다.
DEFAULT_TIMEZONE = "Asia/Seoul"

# 상태 기계 전이표 (Design §2.2). 여기 없는 조합은 전부 금지.
# 역방향·건너뛰기를 데이터로 막아 if 분기가 흩어지지 않게 한다.
_TRANSITIONS: dict[tuple[str, str], ApprovalStatus] = {
    ("pending", "approve"): "approved",
    ("pending", "reject"): "rejected",
    ("pending", "expire"): "expired",
    ("approved", "schedule"): "scheduled",
    ("approved", "execute"): "executed",
    ("approved", "fail"): "failed",
    ("scheduled", "execute"): "executed",
    ("scheduled", "fail"): "failed",
    ("scheduled", "expire"): "expired",
}


@dataclass(frozen=True)
class GateSettings:
    """에이전트별 승인 게이트 설정 — agent_middleware.config 해석 결과.

    Design Ref: §3.4. `is_enforced` 는 config 가 아니라 카탈로그에서 오며,
    True 면 `mode="off"` 를 무시한다 (안전 기능의 끌 권한 차단).
    """

    mode: GateMode
    execute_after: str | None  # cron 문자열. None 이면 승인 즉시 집행
    expires_hours: int
    is_enforced: bool
    # Check G13: cron 을 해석할 벽시계. 없으면 KST — '0 0 * * *' 가 사용자
    # 의도대로 새벽 0시에 발화하게 한다 (이전엔 UTC 로 계산돼 오전 9시).
    timezone: str = DEFAULT_TIMEZONE

    @classmethod
    def from_config(cls, config: dict, *, is_enforced: bool) -> "GateSettings":
        """카탈로그 default_config ∪ 에이전트 override 를 VO 로 해석한다.

        값 검증은 MiddlewareConfigPolicy 가 저장 시점에 하지만, 런타임에도
        상한을 다시 clamp 한다 — 저장 후 DB 직접 수정 같은 경로를 방어
        (stateless-hitl 의 "클라 신고값 재clamp" 와 같은 계열).
        """
        mode = config.get("mode", "always")
        return cls(
            mode="off" if mode == "off" else "always",
            execute_after=config.get("execute_after") or None,
            expires_hours=_clamp_expires_hours(config.get("expires_hours")),
            is_enforced=is_enforced,
            timezone=config.get("timezone") or DEFAULT_TIMEZONE,
        )


@dataclass(frozen=True)
class ApprovalSignal:
    """워커 트레이스에서 건져 올린 게이트 발동 신호.

    Design Ref: §2.1 ② — 미들웨어가 남긴 마커를 래퍼가 파싱한 결과.
    ToolErrorPolicy.summarize 산출물과 같은 계열(트레이스 → state 승격).
    """

    tool_id: str
    tool_args: dict
    draft: str
    tool_call_id: str


@dataclass(frozen=True)
class ResumeSnapshot:
    """워커 진입 시점 SupervisorState 직렬화 스냅샷.

    재개 단위가 '워커 1홉' 인 이유: 위키 supervisor-graph-contracts 의
    "워커 산출물 = AIMessage(name) 1건" 계약 덕에 react 내부 트레이스를
    복원할 필요가 없다. 단독 워커 제약(FR-05)이 중간 결과 유실도 막는다.
    """

    schema_version: int
    agent_updated_at: datetime  # 재개 전 정의 변경 대조 (FR-14)
    worker_id: str
    state_json: str


@dataclass
class ApprovalRequest:
    id: str
    run_id: str
    agent_id: str
    requested_by: str  # 런 실행 신원. 스케줄·웹훅이면 시스템 식별자
    worker_id: str
    tool_id: str
    tool_args: dict
    draft: str
    status: ApprovalStatus
    idempotency_key: str  # UNIQUE — 이중 집행 방어 1차 저지선
    snapshot: ResumeSnapshot
    expires_at: datetime
    request_id: str
    created_at: datetime
    updated_at: datetime
    execute_after: datetime | None = None  # None = 승인 즉시 집행
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None  # 거절 사유 — 재개 시 주입
    executed_at: datetime | None = None
    error_message: str | None = None
    seen_at: datetime | None = None  # NULL=미확인 (벨 배지 기준)
    # 재개 답변을 저장할 원래 대화 세션 (V074). 없으면 재개 답변을 저장하지
    # 못하므로 반드시 적재 시점에 채운다 — Check G1: 빈 값으로 저장하다
    # SessionId("") 예외로 최종 답변이 유실됐다.
    session_id: str | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        """더 이상 전이가 없는 상태 — 목록 필터·정리 배치의 판정 기준."""
        return self.status in ("executed", "rejected", "expired", "failed")


def transition(current: str, event: str) -> ApprovalStatus:
    """전이표 조회. 허용되지 않으면 ValueError."""
    nxt = _TRANSITIONS.get((current, event))
    if nxt is None:
        raise ValueError(f"invalid transition: {current!r} --{event}-->")
    return nxt


def _clamp_expires_hours(raw: object) -> int:
    """정수가 아니거나 범위를 벗어나면 안전한 값으로 접는다.

    bool 을 별도로 거르는 이유: 파이썬에서 bool 은 int 의 서브클래스라
    `True` 가 1시간으로 통과해 버린다.
    """
    if not isinstance(raw, int) or isinstance(raw, bool):
        return DEFAULT_EXPIRES_HOURS
    return max(MIN_EXPIRES_HOURS, min(raw, MAX_EXPIRES_HOURS))
