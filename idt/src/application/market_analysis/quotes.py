"""다중 종목 현재가 — KIS get_quotes 를 30개씩 (보유 관리 · 보유 목록 화면이 같이 쓴다).

Design Ref: stock-analysis-agents §2.2 ②, module-9 결정(보유 표 현재가).
응답 키는 `quotes`. 시세가 없는 종목은 결과에서 빠진다 — 0원으로 보지 않는다.
KIS 가 설정되지 않았거나 호출이 실패해도 예외 없이 빈 dict.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from src.application.market_analysis.ports import MarketTools
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.runtime import ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting

QUOTES_CHUNK = 30


def quote_price(payload: Any) -> Decimal | None:
    if not isinstance(payload, dict):
        return None
    try:
        price = Decimal(str(payload.get("price")))
    except (InvalidOperation, ValueError):
        return None
    return price if price.is_finite() and price > 0 else None


async def fetch_quotes(
    tools: MarketTools,
    setting: MarketAnalysisSetting,
    symbols: list[str],
    *,
    logger: LoggerInterface,
    request_id: str,
) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    unique = list(dict.fromkeys(symbols))
    if not unique or not setting.kis_server_id:
        return prices
    for start in range(0, len(unique), QUOTES_CHUNK):
        outcome = await tools.call(
            source=ToolSource.KIS,
            server_id=setting.kis_server_id,
            tool="get_quotes",
            args={"symbols": unique[start : start + QUOTES_CHUNK]},
            run_as_user_id=setting.run_as_user_id or "",
            request_id=request_id,
        )
        if outcome.is_error or not isinstance(outcome.payload, dict):
            logger.warning(
                "market_analysis quotes unavailable",
                request_id=request_id,
                error_code=outcome.error_code,
            )
            continue
        for row in outcome.payload.get("quotes") or []:
            price = quote_price(row)
            if price is not None and row.get("symbol"):
                prices[str(row["symbol"])] = price
    return prices
