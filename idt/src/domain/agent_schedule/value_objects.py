"""agent-schedule 도메인 VO: ScheduleSpec (반복 규칙).

유형별 필수/금지 필드 조합을 생성 시점에 검증하는 불변 VO.
- once   : run_date + time_of_day
- daily  : time_of_day
- weekly : time_of_day + days_of_week (0=월..6=일)
- cron   : cron_expr (형식 유효성은 SchedulePolicy 담당)
"""
from dataclasses import dataclass
from datetime import date, time
from typing import Literal

ScheduleType = Literal["once", "daily", "weekly", "cron"]

_VALID_TYPES = ("once", "daily", "weekly", "cron")

# 유형별 (필수 필드, 금지 필드) 매트릭스 — if 중첩 없이 선언적으로 검증
_FIELD_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "once": (("run_date", "time_of_day"), ("days_of_week", "cron_expr")),
    "daily": (("time_of_day",), ("run_date", "days_of_week", "cron_expr")),
    "weekly": (("time_of_day", "days_of_week"), ("run_date", "cron_expr")),
    "cron": (("cron_expr",), ("run_date", "time_of_day", "days_of_week")),
}


@dataclass(frozen=True)
class ScheduleSpec:
    schedule_type: ScheduleType
    run_date: date | None = None
    time_of_day: time | None = None
    days_of_week: tuple[int, ...] | None = None
    cron_expr: str | None = None

    def __post_init__(self) -> None:
        if self.schedule_type not in _VALID_TYPES:
            raise ValueError(
                f"지원하지 않는 schedule_type 입니다: {self.schedule_type}"
            )
        required, forbidden = _FIELD_RULES[self.schedule_type]
        for field_name in required:
            if getattr(self, field_name) is None:
                raise ValueError(
                    f"{self.schedule_type} 유형에는 {field_name} 이(가) 필요합니다"
                )
        for field_name in forbidden:
            if getattr(self, field_name) is not None:
                raise ValueError(
                    f"{self.schedule_type} 유형에는 {field_name} 을(를) 지정할 수 없습니다"
                )
        if self.schedule_type == "weekly":
            self._validate_days_of_week()

    def _validate_days_of_week(self) -> None:
        days = self.days_of_week or ()
        if len(days) == 0:
            raise ValueError("weekly 유형에는 days_of_week 이(가) 필요합니다")
        if any(d < 0 or d > 6 for d in days):
            raise ValueError("days_of_week 값은 0..6 (월..일) 범위여야 합니다")
        if len(set(days)) != len(days):
            raise ValueError("days_of_week 에 중복 요일이 있습니다")
