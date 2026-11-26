"""회차 정책 — 언제 돌지, 어떤 종목을 분석할지.

Design Ref: stock-analysis-agents §2.2,
§6(RoundSchedulePolicy·RoundCapPolicy), Plan FR-02~FR-04, D6.
모든 시각 판단은 서울 기준이다. 한국은 서머타임이 없어 고정 +9시간으로 계산한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from src.domain.market_analysis.value_objects import RoundKind

KST_OFFSET = timedelta(hours=9)
CLOSE_FROM = time(15, 30)
HOLIDAY_CHECK_FROM = time(9, 10)
DUE_WINDOW = timedelta(minutes=30)


class SkipReason(StrEnum):
    DISABLED = "DISABLED"
    WEEKEND = "WEEKEND"
    HOLIDAY = "HOLIDAY"
    BUSY = "BUSY"


@dataclass(frozen=True)
class DueSlot:
    trade_date: date
    slot: str
    kind: RoundKind


def _parse(slot: str) -> time:
    hour, minute = slot.split(":")
    return time(int(hour), int(minute))


class RoundSchedulePolicy:
    @staticmethod
    def to_kst(now_utc: datetime) -> datetime:
        return now_utc + KST_OFFSET

    @staticmethod
    def kind_for(slot: str) -> RoundKind:
        return RoundKind.CLOSE if _parse(slot) >= CLOSE_FROM else RoundKind.INTRADAY

    @staticmethod
    def due_slots(now_utc: datetime, round_times: tuple[str, ...]) -> list[DueSlot]:
        """설정 시각이 지났고 30분이 안 된 슬롯.
        주말·스위치 판단은 호출자가 한다(기록을 남기려고)."""
        now = RoundSchedulePolicy.to_kst(now_utc)
        due: list[DueSlot] = []
        for slot in round_times:
            start = datetime.combine(now.date(), _parse(slot))
            if start <= now < start + DUE_WINDOW:
                due.append(
                    DueSlot(now.date(), slot, RoundSchedulePolicy.kind_for(slot))
                )
        return due

    @staticmethod
    def is_weekend(day: date) -> bool:
        return day.weekday() >= 5

    @staticmethod
    def next_slot(now_utc: datetime, round_times: tuple[str, ...]) -> datetime | None:
        """다음 자동 회차 시각(UTC, 주말 건너뜀) — 대시보드 표시용. 시각이 없으면 None.
        휴장일은 알 수 없으므로 평일이면 그대로 둔다."""
        slots = sorted(
            time(int(t[:2]), int(t[3:5])) for t in round_times if len(t) == 5
        )
        if not slots:
            return None
        now_kst = now_utc + KST_OFFSET
        day = now_kst.date()
        for _ in range(8):
            if not RoundSchedulePolicy.is_weekend(day):
                for slot in slots:
                    at = datetime.combine(day, slot)
                    if at > now_kst:
                        return at - KST_OFFSET
            day = day + timedelta(days=1)
        return None

    @staticmethod
    def is_holiday(now_kst: datetime, last_index_day: date | None) -> bool:
        """평일 09:10 이후인데 오늘 지수 봉이
        없으면 휴장. 지수를 못 읽었으면 단정하지 않는다."""
        if last_index_day is None or now_kst.time() < HOLIDAY_CHECK_FROM:
            return False
        return last_index_day < now_kst.date()


@dataclass(frozen=True)
class Candidate:
    """순위·조건검색에서 모은 후보 종목 (신호 판정 전)."""

    symbol: str
    name: str
    volume: int | None
    group: str | None = None
    """한투 증권그룹(ST·EF·EN …) — KIS 가 종목 마스터에서 붙인 값. 모르면 None."""


# KIS 전 종목 적재의 기본 대상("주식류")과 같다 — 주식·외국주식·예탁증서·리츠
EQUITY_GROUPS = frozenset({"ST", "FS", "DR", "RT"})
SPAC_MARK = "스팩"


class EquityPolicy:
    """분석 대상은 주식류만 — ETF·ETN 은 지수를 따라가 재무·기업 분석이 의미가 없다.

    실화면 확인(2026-11-26): 거래량 순위 상위가 레버리지·인버스 ETF·ETN 으로 채워졌다.
    - 한투 증권그룹이 있으면 그것을 따른다(종목 마스터 = 공식 구분)
    - 스팩은 한투 그룹이 ST 라 이름(법정 명칭에 '스팩')으로 뺀다
    - 그룹을 모르면(마스터 장애) 확실한 것만 뺀다: 7자리 Q 코드(ETN)·스팩.
      ETF 는 이름 목록으로 추측하지 않는다 — 브랜드가 계속 늘어 목록이 틀린다
    """

    @staticmethod
    def is_equity(symbol: str, name: str, group: str | None) -> bool:
        if SPAC_MARK in name:
            return False
        if group is not None:
            return group in EQUITY_GROUPS
        return not (len(symbol) == 7 and symbol.startswith("Q"))


@dataclass(frozen=True)
class SignaledCandidate:
    symbol: str
    name: str
    volume: int | None
    signals: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class RoundItemDraft:
    """ma_round_item 한 행 — 회차가 종목별로 남기는 처리 결과의 시작 상태."""

    symbol: str
    name: str
    signals: tuple[dict[str, Any], ...]
    status: str


@dataclass(frozen=True)
class RoundCounts:
    candidates: int = 0
    signaled: int = 0
    analyzed: int = 0
    over_cap: int = 0
    failed: int = 0
    tokens: int = 0
    cost_usd: Decimal = Decimal("0")


@dataclass(frozen=True)
class CapDecision:
    selected: tuple[SignaledCandidate, ...]
    over_cap: tuple[SignaledCandidate, ...]
    held: tuple[SignaledCandidate, ...]
    duplicate: tuple[SignaledCandidate, ...]


class RoundCapPolicy:
    @staticmethod
    def decide(
        signaled: list[SignaledCandidate],
        *,
        analyzed_today: set[str],
        held: set[str],
        max_per_round: int,
        max_per_day: int,
    ) -> CapDecision:
        """D6 '신호 종목 전부' + FR-02 사고 방지
        상한. 넘친 종목은 버리지 않고 over_cap 으로 남긴다."""
        duplicate = tuple(c for c in signaled if c.symbol in analyzed_today)
        held_items = tuple(
            c for c in signaled if c.symbol in held and c.symbol not in analyzed_today
        )
        rest = [
            c
            for c in signaled
            if c.symbol not in analyzed_today and c.symbol not in held
        ]
        rest.sort(key=lambda c: (-len(c.signals), -(c.volume or 0), c.symbol))
        cap = max(0, min(max_per_round, max_per_day - len(analyzed_today)))
        return CapDecision(
            selected=tuple(rest[:cap]),
            over_cap=tuple(rest[cap:]),
            held=held_items,
            duplicate=duplicate,
        )
