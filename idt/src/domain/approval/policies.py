"""approval-gate 도메인 정책.

Design Ref: §2.2 (게이트 발동 합성 규칙·상태 기계), §9.3 (레이어 배치).

- ApprovalPolicy: 발동 판정·승인 권한·상태 전이·만료·멱등 키의 단일 결정 지점
- ApprovalSignalPolicy: 미들웨어 마커의 render ↔ extract 왕복

두 Policy 모두 순수 함수다 — DB·langchain·env 를 모른다. 덕분에
ApprovalGateMiddleware 를 DB 없이 단위 테스트할 수 있다 (Option C 의 이점).
"""
import json
from datetime import datetime, timedelta, timezone

from src.domain.agent_run.clock import to_local
from src.domain.approval.entity import (
    DEFAULT_EXPIRES_HOURS,
    DEFAULT_TIMEZONE,
    MAX_EXPIRES_HOURS,
    MAX_SNAPSHOT_BYTES,
    MIN_EXPIRES_HOURS,
    ApprovalSignal,
    ApprovalStatus,
    GateSettings,
    transition,
)


class ApprovalPolicy:
    """승인 게이트의 모든 판정을 모은 단일 지점.

    역할 기반 승인자로 확장할 때 건드릴 곳은 `can_decide` 하나다 —
    라우터·UseCase 에 권한 분기를 흩지 않기 위한 격리 (Plan FR-08).
    """

    DEFAULT_EXPIRES_HOURS: int = DEFAULT_EXPIRES_HOURS
    MIN_EXPIRES_HOURS: int = MIN_EXPIRES_HOURS
    MAX_EXPIRES_HOURS: int = MAX_EXPIRES_HOURS
    MAX_SNAPSHOT_BYTES: int = MAX_SNAPSHOT_BYTES
    DEFAULT_TIMEZONE: str = DEFAULT_TIMEZONE

    @staticmethod
    def should_gate(
        *, tool_requires_approval: bool, gate: GateSettings | None
    ) -> bool:
        """Design §2.2 — 도구 축 AND 에이전트 축의 합성.

        도구 축(`requires_approval`)은 "무엇이 위험한가", 에이전트 축(게이트
        적용 여부)은 "누가 통제받는가" 로 직교하므로 둘 다 참이어야 발동한다.
        `is_enforced` 는 `mode="off"` 를 이기지만, 도구 축까지 이기지는
        않는다 — 부작용 없는 도구만 쓰는 에이전트는 강제 정책과 무관하다.
        """
        if not tool_requires_approval or gate is None:
            return False
        if gate.is_enforced:
            return True
        return gate.mode != "off"

    @staticmethod
    def can_decide(*, user_id: str, agent_owner_id: str) -> bool:
        """승인 권한 — 현재는 에이전트 소유자.

        빈 신원을 거부하는 이유: 스케줄·웹훅 런의 `requested_by` 는 시스템
        식별자이거나 빈 값일 수 있는데, 그것이 소유자와 우연히 같아져
        '시스템이 스스로를 승인' 하는 경로가 열리면 안 된다.
        """
        if not user_id or not agent_owner_id:
            return False
        return user_id == agent_owner_id

    @staticmethod
    def next_status(current: str, event: str) -> ApprovalStatus:
        """전이표 기반 상태 전이. 역방향·건너뛰기는 ValueError."""
        return transition(current, event)

    @staticmethod
    def resolve_expires_at(now: datetime, expires_hours: int) -> datetime:
        return now + timedelta(hours=expires_hours)

    @staticmethod
    def is_expired(expires_at: datetime, *, now: datetime) -> bool:
        """경계(정각)는 만료로 본다 — 애매한 순간에 집행하지 않는 쪽이 안전."""
        return expires_at <= now

    @staticmethod
    def validate_window(
        *, execute_after: datetime | None, expires_at: datetime
    ) -> None:
        """FR-26 — 집행 예정이 만료보다 늦으면 영원히 집행되지 않는다.

        승인 시점에 거부해, 사용자가 승인했는데 아무 일도 안 일어나는
        침묵 실패를 막는다.
        """
        if execute_after is not None and execute_after >= expires_at:
            raise ValueError(
                f"execute_after({execute_after}) must be before "
                f"expires_at({expires_at})"
            )

    @staticmethod
    def build_idempotency_key(
        *, run_id: str, worker_id: str, tool_call_id: str
    ) -> str:
        """이중 집행 방어 키. 빈 구성요소는 UNIQUE 제약을 무력화하므로 거부."""
        if not run_id or not worker_id or not tool_call_id:
            raise ValueError(
                "idempotency key requires run_id, worker_id and tool_call_id"
            )
        return f"{run_id}:{worker_id}:{tool_call_id}"

    @staticmethod
    def next_execute_after(
        cron: str | None, *, now_utc: datetime, tz: str
    ) -> datetime | None:
        """Check G13 — 다음 집행 시각(UTC naive). cron 이 없으면 None(즉시 집행).

        cron 은 **사용자 벽시계(tz)** 로 해석해야 한다. UTC 로 계산하면
        '0 0 * * *' 가 KST 오전 9시에 발화한다. agent_schedule 의
        SchedulePolicy.compute_next_run 과 같은 절차(to_local → croniter →
        UTC naive 복귀)를 따른다 — 두 기능이 같은 시각 규약을 쓴다.
        croniter 는 순수 계산이라 domain 사용이 허용된다.
        """
        if not cron:
            return None
        from croniter import croniter

        local = to_local(now_utc, tz)
        nxt = croniter(cron, local).get_next(datetime)
        return nxt.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def exceeds_snapshot_limit(payload: bytes) -> bool:
        return len(payload) > MAX_SNAPSHOT_BYTES


class ApprovalSignalPolicy:
    """미들웨어 마커의 생성·파싱 — render 와 extract 를 한 곳에 둔다.

    Design Ref: §2.1 — 포맷이 두 모듈로 갈라지면 조용히 어긋나므로, 쓰는 쪽과
    읽는 쪽을 같은 Policy 가 소유한다. `ToolErrorPolicy.summarize` 와 같은
    계열(워커 트레이스 → SupervisorState 승격)이다.
    """

    MARKER = "[APPROVAL_REQUIRED]"

    @classmethod
    def render(
        cls, *, tool_id: str, tool_args: dict, draft: str, tool_call_id: str
    ) -> str:
        """미들웨어가 실도구 대신 반환할 ToolMessage 본문.

        사람이 읽는 안내 문구를 함께 담는다 — 워커 LLM 이 이 문자열을 보고
        "보냈다" 가 아니라 "승인 대기로 등록했다" 로 답하게 하기 위함.
        """
        payload = json.dumps(
            {
                "tool_id": tool_id,
                "tool_args": tool_args,
                "draft": draft,
                "tool_call_id": tool_call_id,
            },
            ensure_ascii=False,
        )
        return (
            f"{cls.MARKER}{payload}\n"
            "이 작업은 사람의 승인이 필요해 실행되지 않았습니다. "
            "승인 요청이 등록되었음을 사용자에게 알리고 마무리하세요."
        )

    @classmethod
    def extract(cls, messages: list) -> ApprovalSignal | None:
        """트레이스에서 첫 마커를 파싱한다. 없거나 깨졌으면 None.

        첫 건만 채택하는 이유: 런당 활성 pending 1건 불변식(FR-06).
        파싱 실패를 예외로 올리지 않는 이유: 게이트 신호 파싱이 워커 전체를
        죽이면, 정작 차단은 이미 성공했는데 사용자는 오류만 보게 된다.
        """
        for message in messages or []:
            signal = cls._parse_one(getattr(message, "content", None))
            if signal is not None:
                return signal
        return None

    @classmethod
    def _parse_one(cls, content: object) -> ApprovalSignal | None:
        if not isinstance(content, str) or cls.MARKER not in content:
            return None
        body = content.split(cls.MARKER, 1)[1]
        raw = cls._load_leading_json(body)
        if raw is None:
            return None
        return ApprovalSignal(
            tool_id=str(raw.get("tool_id", "")),
            tool_args=raw.get("tool_args") or {},
            draft=str(raw.get("draft", "")),
            tool_call_id=str(raw.get("tool_call_id", "")),
        )

    @staticmethod
    def _load_leading_json(body: str) -> dict | None:
        """마커 뒤 JSON 객체만 떼어 읽는다 (뒤에 안내 문구가 붙어 있음)."""
        decoder = json.JSONDecoder()
        try:
            raw, _ = decoder.raw_decode(body.lstrip())
        except ValueError:
            return None
        return raw if isinstance(raw, dict) else None
