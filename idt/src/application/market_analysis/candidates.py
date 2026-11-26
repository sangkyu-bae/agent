"""후보 수집과 신호 스캔 — 회차 ③④.

Design Ref: stock-analysis-agents §2.2,
DD11(설정한 규칙이 하나라도 난 종목 전부), DD12(마감 후 전 종목
스캔은 1차 제외 — 후보는 순위 ∪ 조건검색). KIS 응답
형식은 mcp-kis-server schemas 그대로다.
- 소스 하나가 실패해도 나머지 후보로 진행한다
- scan_signals 는 호출당 30종목(KIS_SCAN_MAX_SYMBOLS)
— 나눠 부르고, 묶음 하나가 실패하면 그 묶음만 빠진다
"""

from __future__ import annotations

from typing import Any

from src.application.market_analysis.ports import MarketTools
from src.domain.market_analysis.round import (
    Candidate,
    EquityPolicy,
    SignaledCandidate,
)
from src.domain.market_analysis.runtime import ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting

SCAN_CHUNK = 30


class ScanUnavailableError(RuntimeError):
    """신호 스캔이 한 묶음도 되지 않았다 — 회차는 failed(SCAN_FAILED(code))."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def _kis(
    tools: MarketTools,
    setting: MarketAnalysisSetting,
    tool: str,
    args: dict,
    request_id: str,
) -> Any:
    outcome = await tools.call(
        source=ToolSource.KIS,
        server_id=setting.kis_server_id or "",
        tool=tool,
        args=args,
        run_as_user_id=setting.run_as_user_id or "",
        request_id=request_id,
    )
    return None if outcome.is_error else outcome.payload


def _volume(row: dict) -> int | None:
    value = row.get("volume")
    return int(value) if isinstance(value, int | float) else None


async def collect_candidates(
    tools: MarketTools, setting: MarketAnalysisSetting, *, request_id: str
) -> dict[str, Candidate]:
    """순위(설정한 종류별) ∪ 조건검색. 처음 본 순서를 지킨다."""
    found: dict[str, Candidate] = {}

    def add(rows: Any) -> None:
        for row in rows or []:
            symbol = str(row.get("symbol") or "").strip()
            if not symbol or symbol in found:
                continue
            name = str(row.get("name") or symbol)
            group = row.get("group") or None
            # 주식류만 — ETF·ETN·스팩은 후보에서 뺀다 (EquityPolicy)
            if not EquityPolicy.is_equity(symbol, name, group):
                continue
            found[symbol] = Candidate(
                symbol=symbol, name=name, volume=_volume(row), group=group
            )

    for kind in setting.ranking_kinds:
        payload = await _kis(
            tools,
            setting,
            "get_rankings",
            {"kind": kind, "limit": setting.ranking_limit},
            request_id,
        )
        add((payload or {}).get("entries") if isinstance(payload, dict) else None)
    for seq in setting.condition_seqs:
        payload = await _kis(
            tools, setting, "run_condition_search", {"seq": seq}, request_id
        )
        add((payload or {}).get("hits") if isinstance(payload, dict) else None)
    return found


async def scan_candidates(
    tools: MarketTools,
    setting: MarketAnalysisSetting,
    candidates: dict[str, Candidate],
    *,
    request_id: str,
) -> list[SignaledCandidate]:
    """설정 규칙으로 스캔해 신호가 하나라도
    난 종목만 돌려준다 (종목별로 신호를 묶는다).

    묶음 하나의 실패는 그 묶음만 빠진다. **모든 묶음이 실패하면** ScanUnavailableError —
    '신호 0건'과 '스캔 못 함'을 구분한다(실화면 확인: 오래된 KIS 컨테이너가 규칙을
    전부 거부했는데 회차가 신호 0건으로 끝났다)."""
    symbols = list(candidates)
    hits: dict[str, list[dict[str, Any]]] = {}
    chunks = failed = 0
    last_error: str | None = None
    for start in range(0, len(symbols), SCAN_CHUNK):
        chunk = symbols[start : start + SCAN_CHUNK]
        args: dict[str, Any] = {"symbols": chunk, "rules": list(setting.signal_rules)}
        if setting.rule_params:
            args["rule_params"] = setting.rule_params
        chunks += 1
        outcome = await tools.call(
            source=ToolSource.KIS,
            server_id=setting.kis_server_id or "",
            tool="scan_signals",
            args=args,
            run_as_user_id=setting.run_as_user_id or "",
            request_id=request_id,
        )
        if outcome.is_error:
            failed += 1
            last_error = outcome.error_code or "TOOL_CALL_FAILED"
            continue
        payload = outcome.payload
        signals = payload.get("signals") if isinstance(payload, dict) else None
        for rule, rows in (signals or {}).items():
            for row in rows or []:
                symbol = str(row.get("symbol") or "")
                if symbol not in candidates:
                    continue
                hits.setdefault(symbol, []).append(
                    {
                        "rule": rule,
                        "direction": row.get("direction"),
                        "provisional": bool(row.get("provisional")),
                        "values": row.get("values") or {},
                    }
                )
    if chunks and failed == chunks:
        raise ScanUnavailableError(last_error or "TOOL_CALL_FAILED")
    return [
        SignaledCandidate(
            symbol=symbol,
            name=candidates[symbol].name,
            volume=candidates[symbol].volume,
            signals=tuple(hits[symbol]),
        )
        for symbol in symbols
        if symbol in hits
    ]
