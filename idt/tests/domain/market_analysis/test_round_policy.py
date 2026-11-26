"""회차 정책 — 시각 판정 · 휴장 · 상한 (design §6
RoundSchedulePolicy·RoundCapPolicy, U6·U8)."""

from datetime import date, datetime, timedelta

from src.domain.market_analysis.round import (
    RoundCapPolicy,
    RoundSchedulePolicy,
    SignaledCandidate,
)
from src.domain.market_analysis.value_objects import RoundKind

TIMES = ("10:00", "14:00", "18:10")


def _utc(kst: str) -> datetime:
    """'2026-11-26 10:05' (서울) → naive UTC."""
    return datetime.strptime(kst, "%Y-%m-%d %H:%M") - timedelta(hours=9)


def test_due_within_thirty_minutes_after_slot():
    slots = RoundSchedulePolicy.due_slots(_utc("2026-11-26 10:05"), TIMES)
    assert [(s.trade_date, s.slot, s.kind) for s in slots] == [
        (date(2026, 11, 26), "10:00", RoundKind.INTRADAY)
    ]
    assert RoundSchedulePolicy.due_slots(_utc("2026-11-26 09:59"), TIMES) == []
    assert RoundSchedulePolicy.due_slots(_utc("2026-11-26 10:31"), TIMES) == []


def test_close_slot_kind():
    (slot,) = RoundSchedulePolicy.due_slots(_utc("2026-11-26 18:15"), TIMES)
    assert slot.kind is RoundKind.CLOSE
    assert RoundSchedulePolicy.kind_for("15:30") is RoundKind.CLOSE
    assert RoundSchedulePolicy.kind_for("15:29") is RoundKind.INTRADAY


def test_slot_crossing_midnight_utc_uses_seoul_date():
    # 서울 08:50 = 전날 23:50 UTC — 거래일은 서울 날짜
    (slot,) = RoundSchedulePolicy.due_slots(_utc("2026-11-27 08:55"), ("08:50",))
    assert slot.trade_date == date(2026, 11, 27)


def test_weekend_and_holiday():
    assert RoundSchedulePolicy.is_weekend(date(2026, 11, 28))  # 토
    assert not RoundSchedulePolicy.is_weekend(date(2026, 11, 27))
    now = datetime(2026, 11, 26, 10, 0)  # 서울 기준
    assert RoundSchedulePolicy.is_holiday(now, last_index_day=date(2026, 11, 25))
    assert not RoundSchedulePolicy.is_holiday(now, last_index_day=date(2026, 11, 26))
    # 09:10 전에는 오늘 봉이 없어도 휴장으로 보지 않는다
    assert not RoundSchedulePolicy.is_holiday(
        datetime(2026, 11, 26, 9, 5), date(2026, 11, 25)
    )
    # 지수를 못 읽었으면 휴장으로 단정하지 않는다
    assert not RoundSchedulePolicy.is_holiday(now, last_index_day=None)


def _c(symbol, n_signals=1, volume=100):
    return SignaledCandidate(
        symbol=symbol,
        name=symbol,
        volume=volume,
        signals=tuple({"rule": f"r{i}"} for i in range(n_signals)),
    )


def test_cap_policy_u6():
    # 신호 30, 오늘 분석 5, 보유 2, 회차 상한 20, 하루 상한 15(=남은 10) → 10 분석
    signaled = [_c(f"{i:06d}") for i in range(30)]
    analyzed = {f"{i:06d}" for i in range(5)}
    held = {"000005", "000006"}
    d = RoundCapPolicy.decide(
        signaled, analyzed_today=analyzed, held=held, max_per_round=20, max_per_day=15
    )
    assert len(d.duplicate) == 5 and len(d.held) == 2
    assert len(d.selected) == 10 and len(d.over_cap) == 13


def test_cap_orders_by_signal_count_then_volume():
    signaled = [_c("A", 1, 999), _c("B", 3, 1), _c("C", 3, 50), _c("D", 2, 0)]
    d = RoundCapPolicy.decide(
        signaled, analyzed_today=set(), held=set(), max_per_round=3, max_per_day=50
    )
    assert [c.symbol for c in d.selected] == ["C", "B", "D"]
    assert [c.symbol for c in d.over_cap] == ["A"]


def test_day_cap_exhausted():
    d = RoundCapPolicy.decide(
        [_c("A")],
        analyzed_today={f"{i}" for i in range(50)},
        held=set(),
        max_per_round=20,
        max_per_day=50,
    )
    assert d.selected == () and [c.symbol for c in d.over_cap] == ["A"]


def test_next_slot_today_tomorrow_and_weekend():
    times = ("10:00", "14:00", "18:10")
    # 목 서울 10:05 → 같은 날 14:00 (UTC 05:00)
    assert RoundSchedulePolicy.next_slot(
        datetime(2026, 11, 26, 1, 5), times
    ) == datetime(2026, 11, 26, 5, 0)
    # 금 서울 19:00 → 월 10:00 (UTC 01:00)
    assert RoundSchedulePolicy.next_slot(
        datetime(2026, 11, 27, 10, 0), times
    ) == datetime(2026, 11, 30, 1, 0)
    assert RoundSchedulePolicy.next_slot(datetime(2026, 11, 26, 1, 5), ()) is None


# ── 분석 대상은 주식류만 (실화면 확인: 순위에 ETF·ETN·스팩이 섞였다) ─────────────


def test_equity_policy_uses_kis_group_first():
    from src.domain.market_analysis.round import EquityPolicy

    assert EquityPolicy.is_equity("005930", "삼성전자", "ST")
    assert EquityPolicy.is_equity("088980", "맥쿼리인프라", "RT")
    assert not EquityPolicy.is_equity("252670", "KODEX 200선물인버스2X", "EF")
    assert not EquityPolicy.is_equity(
        "Q530107", "삼성 인버스 2X 코스닥150 선물 ETN", "EN"
    )
    # 스팩은 한투 그룹이 ST 라 이름으로 뺀다
    assert not EquityPolicy.is_equity("0099X0", "IBKS제25호스팩", "ST")


def test_equity_policy_without_group_drops_only_what_is_certain():
    from src.domain.market_analysis.round import EquityPolicy

    assert not EquityPolicy.is_equity(
        "Q700032", "하나 인버스 2X 천연가스 선물 ETN(H)", None
    )
    assert not EquityPolicy.is_equity("123456", "미래에셋스팩3호", None)
    # 그룹을 모르면 ETF 는 확실히 알 수 없어 남긴다 (이름 목록으로 추측하지 않는다)
    assert EquityPolicy.is_equity("252670", "KODEX 200선물인버스2X", None)
    assert EquityPolicy.is_equity("005930", "삼성전자", None)
