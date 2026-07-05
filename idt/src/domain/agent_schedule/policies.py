"""agent-schedule 도메인 정책: 검증·next_run 계산·지침 렌더링.

시각 규격: 모든 입출력 datetime 은 UTC naive (DB DATETIME 규격).
타임존은 계산 시에만 ZoneInfo 로 적용한다.
croniter 는 외부 I/O 없는 순수 계산 라이브러리로 domain 사용이 허용된다
(agent-schedule.design.md §1.3).
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from src.domain.agent_schedule.value_objects import ScheduleSpec

_WEEKDAY_KO = "월화수목금토일"


def _to_local(after_utc: datetime, tz: str) -> datetime:
    return after_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))


def _to_utc_naive(local: datetime) -> datetime:
    return local.astimezone(timezone.utc).replace(tzinfo=None)


class SchedulePolicy:
    MAX_SCHEDULES_PER_AGENT = 10
    MIN_CRON_INTERVAL_MINUTES = 10
    MAX_INSTRUCTION_LENGTH = 1900
    RENDERED_QUERY_MAX_LENGTH = 2000  # RunAgentRequest.query 제약
    DEFAULT_TIMEZONE = "Asia/Seoul"
    PLACEHOLDERS = ("{today}", "{now}", "{weekday}")  # R9 지원 변수

    # ── next_run 계산 ────────────────────────────────────────────

    @staticmethod
    def compute_next_run(
        spec: ScheduleSpec, tz: str, after_utc: datetime
    ) -> datetime | None:
        """after_utc 이후 첫 발화 시각을 UTC naive 로 반환. once 소진 시 None."""
        local = _to_local(after_utc, tz)
        if spec.schedule_type == "once":
            candidate = datetime.combine(
                spec.run_date, spec.time_of_day, tzinfo=ZoneInfo(tz)
            )
            return _to_utc_naive(candidate) if candidate > local else None
        if spec.schedule_type == "cron":
            nxt = croniter(spec.cron_expr, local).get_next(datetime)
            return _to_utc_naive(nxt)
        return SchedulePolicy._next_time_of_day(spec, local, tz)

    @staticmethod
    def _next_time_of_day(
        spec: ScheduleSpec, local: datetime, tz: str
    ) -> datetime:
        """daily/weekly: local 이후 가장 가까운 time_of_day 발화 시각."""
        allowed_days = (
            set(spec.days_of_week) if spec.schedule_type == "weekly" else None
        )
        for offset in range(8):  # weekly 도 7일 안에 반드시 존재
            day = (local + timedelta(days=offset)).date()
            if allowed_days is not None and day.weekday() not in allowed_days:
                continue
            candidate = datetime.combine(day, spec.time_of_day, tzinfo=ZoneInfo(tz))
            if candidate > local:
                return _to_utc_naive(candidate)
        raise ValueError("next_run 계산 실패: 8일 내 발화 시각 없음")  # 도달 불가

    # ── 검증 ─────────────────────────────────────────────────────

    @staticmethod
    def validate_spec(spec: ScheduleSpec, tz: str, now_utc: datetime) -> None:
        SchedulePolicy._validate_timezone(tz)
        if spec.schedule_type == "cron":
            SchedulePolicy._validate_cron(spec.cron_expr, tz)
        if spec.schedule_type == "once":
            if SchedulePolicy.compute_next_run(spec, tz, now_utc) is None:
                raise ValueError("once 스케줄의 실행 시각은 미래여야 합니다")

    @staticmethod
    def _validate_timezone(tz: str) -> None:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError, KeyError) as e:
            raise ValueError(f"유효하지 않은 timezone 입니다: {tz}") from e

    @staticmethod
    def _validate_cron(expr: str, tz: str) -> None:
        if not croniter.is_valid(expr):
            raise ValueError(f"유효하지 않은 cron 표현식입니다: {expr}")
        base = datetime(2026, 1, 1, tzinfo=ZoneInfo(tz))
        it = croniter(expr, base)
        fires = [it.get_next(datetime) for _ in range(6)]
        min_gap = min(
            (b - a).total_seconds() / 60 for a, b in zip(fires, fires[1:])
        )
        if min_gap < SchedulePolicy.MIN_CRON_INTERVAL_MINUTES:
            raise ValueError(
                f"cron 최소 간격은 {SchedulePolicy.MIN_CRON_INTERVAL_MINUTES}분 입니다"
                f" (현재 최소 {min_gap:.0f}분)"
            )

    @staticmethod
    def validate_instruction(instruction: str) -> None:
        if not instruction or not instruction.strip():
            raise ValueError("지침(instruction)이 비어 있습니다")
        if len(instruction) > SchedulePolicy.MAX_INSTRUCTION_LENGTH:
            raise ValueError(
                f"지침은 최대 {SchedulePolicy.MAX_INSTRUCTION_LENGTH}자 입니다"
            )

    @staticmethod
    def validate_count(existing_count: int) -> None:
        if existing_count >= SchedulePolicy.MAX_SCHEDULES_PER_AGENT:
            raise ValueError(
                f"에이전트당 스케줄은 최대 "
                f"{SchedulePolicy.MAX_SCHEDULES_PER_AGENT}개 입니다"
            )

    @staticmethod
    def can_modify(schedule_user_id: str, viewer_user_id: str) -> bool:
        return schedule_user_id == viewer_user_id

    # ── 지침 렌더링 (R9) ─────────────────────────────────────────

    @staticmethod
    def render_instruction(instruction: str, tz: str, now_utc: datetime) -> str:
        """{today}/{now}/{weekday} 를 스케줄 tz 기준 현재 시각으로 치환.

        미지원 플레이스홀더는 원문 유지. 결과는 2000자로 절단.
        """
        local = _to_local(now_utc, tz)
        values = {
            "{today}": local.strftime("%Y-%m-%d"),
            "{now}": local.strftime("%H:%M"),
            "{weekday}": _WEEKDAY_KO[local.weekday()],
        }
        rendered = instruction
        for placeholder in SchedulePolicy.PLACEHOLDERS:
            rendered = rendered.replace(placeholder, values[placeholder])
        return rendered[: SchedulePolicy.RENDERED_QUERY_MAX_LENGTH]
