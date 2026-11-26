"""회차 시작 ① — 지수 조회 · 체제 계산 · 휴장 판정 재료 · 시장 맥락 문자열.

Design Ref: stock-analysis-agents §2.2 ①, §6 RegimePolicy.
KOSPI 80봉으로 체제를 판정하고(60봉 미만이면 neutral + insufficient),
KOSDAQ 은 종가만 쓴다. 지수 조회가 실패해도 예외 없이 neutral 로 계속한다 —
휴장 판정은 마지막 KOSPI 봉 날짜가 없으면 휴장으로 단정하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from src.application.market_analysis.ports import MarketTools, RegimeStore
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.account import RegimePolicy, RegimeResult
from src.domain.market_analysis.runtime import ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting

KOSPI_BARS = 80
KOSDAQ_BARS = 5
# 회차를 계속해도 소용없는 KIS 오류 — 일시 오류(RATE_LIMITED·KIS_TIMEOUT)는 계속한다
KIS_FATAL = frozenset({"SERVER_UNAVAILABLE", "KIS_AUTH_FAILED"})
REGIME_LABELS = {
    "strong_bull": "강한 상승",
    "bull": "상승",
    "neutral": "중립",
    "bear": "하락",
    "strong_bear": "강한 하락",
}


@dataclass(frozen=True)
class MarketSnapshot:
    regime: RegimeResult
    kospi_day: date | None
    kospi_close: Decimal | None
    kosdaq_close: Decimal | None
    kospi_bars: int
    context: str
    kis_error: str | None = None
    """KIS 를 쓸 수 없는 오류 코드 (서버 비활성·인증 실패). 있으면 회차는 failed."""


def _day(text: Any) -> date | None:
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        return None


def _num(text: Any) -> Decimal | None:
    try:
        return Decimal(str(text))
    except (InvalidOperation, ValueError):
        return None


class MarketRegimeService:
    def __init__(
        self,
        *,
        tools: MarketTools,
        regimes: RegimeStore | None,
        logger: LoggerInterface,
    ) -> None:
        self._tools = tools
        self._regimes = regimes
        self._logger = logger

    async def snapshot(
        self, setting: MarketAnalysisSetting, request_id: str
    ) -> MarketSnapshot:
        kospi, kospi_error = await self._bars(setting, "KOSPI", KOSPI_BARS, request_id)
        if kospi_error in KIS_FATAL:
            # 중간 점검 I1 · Design §10: KIS 장애를 '신호 없음'과 구분한다
            return MarketSnapshot(
                regime=RegimePolicy.decide([]),
                kospi_day=None,
                kospi_close=None,
                kosdaq_close=None,
                kospi_bars=0,
                context="",
                kis_error=kospi_error,
            )
        kosdaq, _ = await self._bars(setting, "KOSDAQ", KOSDAQ_BARS, request_id)
        closes = [c for c in (_num(b.get("close")) for b in kospi) if c is not None]
        result = RegimePolicy.decide(closes)
        lines = [self._regime_line(result), "", "[지수]"]
        for index, bars in (("KOSPI", kospi), ("KOSDAQ", kosdaq)):
            if not bars:
                lines.append(f"{index}: 데이터 없음")
                continue
            last = bars[-1]
            state = " (미확정)" if last.get("provisional") else ""
            lines.append(f"{index}: {last.get('close')} ({last.get('date')}{state})")
        return MarketSnapshot(
            regime=result,
            kospi_day=_day(kospi[-1].get("date")) if kospi else None,
            kospi_close=closes[-1] if closes else None,
            kosdaq_close=_num(kosdaq[-1].get("close")) if kosdaq else None,
            kospi_bars=len(closes),
            context="\n".join(lines),
        )

    async def save(
        self, *, trade_date: date, snapshot: MarketSnapshot, request_id: str
    ) -> None:
        if self._regimes is None or snapshot.kospi_close is None:
            return
        try:
            await self._regimes.save_regime(
                trade_date=trade_date,
                result=snapshot.regime,
                kosdaq_close=snapshot.kosdaq_close,
                bars=snapshot.kospi_bars,
                request_id=request_id,
            )
        except Exception as e:  # noqa: BLE001 — 기록 실패가 회차를 멈추지 않는다
            self._logger.warning(
                "market_analysis regime save failed",
                exception=e,
                request_id=request_id,
            )

    @staticmethod
    def _regime_line(result: RegimeResult) -> str:
        label = f"{REGIME_LABELS[result.regime.value]}({result.regime.value})"
        if result.insufficient:
            return f"[시장 체제] {label} — KOSPI 봉이 60개 미만이라 중립으로 둔다"
        return (
            f"[시장 체제] {label} — KOSPI 종가 {result.close}, MA20 {result.ma20}, "
            f"MA60 {result.ma60}, 20일 수익률 {result.r20}%"
        )

    async def _bars(
        self, setting: MarketAnalysisSetting, index: str, limit: int, request_id: str
    ) -> tuple[list[dict[str, Any]], str | None]:
        """(봉 목록, 오류 코드). 오류여도 예외 없이 빈 목록."""
        outcome = await self._tools.call(
            source=ToolSource.KIS,
            server_id=setting.kis_server_id or "",
            tool="get_index_history",
            args={"index": index, "interval": "D", "limit": limit},
            run_as_user_id=setting.run_as_user_id or "",
            request_id=request_id,
        )
        if outcome.is_error or not isinstance(outcome.payload, dict):
            self._logger.warning(
                "market_analysis index history unavailable",
                request_id=request_id,
                index=index,
                error_code=outcome.error_code,
            )
            return [], outcome.error_code or "TOOL_CALL_FAILED"
        bars = outcome.payload.get("bars")
        if not isinstance(bars, list):
            return [], None
        return [b for b in bars if isinstance(b, dict)], None
