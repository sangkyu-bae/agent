"""런타임 시각 계산 헬퍼 (runtime-datetime-context Design D2).

순수 계산만 담당한다 — 외부 I/O·config 참조 없음.
`SchedulePolicy`(agent_schedule)와 `render_datetime_block`(agent_run)이 공유한다.

시각 규격:
- 입력 `now_utc`는 aware(UTC 또는 다른 tz) 또는 naive(=UTC 가정) 모두 허용.
  naive 허용은 agent_schedule의 "UTC naive" DB 규격과의 호환을 위함.
- 잘못된 tz 문자열은 `ZoneInfoNotFoundError`를 그대로 전파한다.
  degraded 처리(빈 블록 + warning)는 application 소비자의 책임.
"""
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

WEEKDAY_KO = "월화수목금토일"


def to_local(now_utc: datetime, tz: str) -> datetime:
    """UTC 시각 → `tz` 로컬 aware datetime. naive 입력은 UTC로 간주."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    return now_utc.astimezone(ZoneInfo(tz))


def weekday_ko(d: date) -> str:
    """date.weekday()(월=0) → 한국어 한 글자 요일."""
    return WEEKDAY_KO[d.weekday()]
