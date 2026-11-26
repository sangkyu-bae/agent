"""prefetch — LLM 없이 근거를 먼저 모으고, 섹션에 넘길 근거 블록을 만든다.

Design Ref: stock-analysis-agents §2.3, §1.1-5, §8.1(실제 도구 시그니처).
- 소스 서버가 설정돼 있지 않으면 그 근거는 계획에서
빠지고 블록에 "데이터 없음 (조회 안 함)"
- 근거 블록은 도구 결과 원문(JSON)을 그대로
싣는다 — 에이전트 지침은 "근거 블록에 없는 수치 금지"
- 실패는 블록에 오류 코드와 함께 "데이터 없음" 으로 남는다 (섹션은 계속 쓴다)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.application.market_analysis.ports import MarketTools
from src.domain.market_analysis.report import EvidenceKey
from src.domain.market_analysis.runtime import ToolOutcome, ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting

INDICATORS = ["sma", "ema", "rsi", "macd", "bollinger", "volume_ratio"]
NEWS_DAYS = 7
NEWS_MAX = 5
RESEARCH_MAX = 8
DISCLOSURE_DAYS = 30


@dataclass(frozen=True)
class PrefetchCall:
    key: EvidenceKey
    source: ToolSource
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


def plan_prefetch(
    *, symbol: str, name: str, setting: MarketAnalysisSetting, today: date
) -> list[PrefetchCall]:
    calls: list[PrefetchCall] = []
    if setting.kis_server_id:
        kis = ToolSource.KIS
        calls += [
            PrefetchCall(EvidenceKey.QUOTE, kis, "get_quote", {"symbol": symbol}),
            PrefetchCall(
                EvidenceKey.DAILY,
                kis,
                "get_price_history",
                {"symbol": symbol, "interval": "D", "limit": 120},
            ),
            PrefetchCall(
                EvidenceKey.INDICATORS,
                kis,
                "compute_indicators",
                {"symbol": symbol, "indicators": INDICATORS},
            ),
            PrefetchCall(
                EvidenceKey.INVESTOR,
                kis,
                "get_investor_flow",
                {"symbol": symbol, "days": 20},
            ),
        ]
    if setting.dart_server_id:
        dart = ToolSource.DART
        calls += [
            PrefetchCall(EvidenceKey.DART_CORP, dart, "find_corp", {"symbol": symbol}),
            PrefetchCall(
                EvidenceKey.DART_FINANCIALS,
                dart,
                "get_financials",
                {"symbol": symbol, "year": today.year - 1, "report": "annual"},
            ),
            PrefetchCall(
                EvidenceKey.DART_DISCLOSURES,
                dart,
                "list_disclosures",
                {"symbol": symbol, "days": DISCLOSURE_DAYS},
            ),
        ]
    calls.append(
        PrefetchCall(
            EvidenceKey.NEWS,
            ToolSource.TAVILY,
            "search",
            {"query": f"{name} 주가", "days": NEWS_DAYS, "max_results": NEWS_MAX},
        )
    )
    if setting.perplexity_server_id:
        calls.append(
            PrefetchCall(
                EvidenceKey.RESEARCH,
                ToolSource.PERPLEXITY,
                "research",
                {
                    "query": f"{name}({symbol}) 사업 내용·주요 경쟁사·최근 이슈",
                    "recency": "month",
                    "max_results": RESEARCH_MAX,
                },
            )
        )
    return calls


def _server_id(setting: MarketAnalysisSetting, source: ToolSource) -> str:
    return {
        ToolSource.KIS: setting.kis_server_id,
        ToolSource.DART: setting.dart_server_id,
        ToolSource.PERPLEXITY: setting.perplexity_server_id,
    }.get(source) or ""


async def run_prefetch(
    tools: MarketTools,
    calls: list[PrefetchCall],
    *,
    setting: MarketAnalysisSetting,
    run_as_user_id: str,
    request_id: str,
) -> dict[EvidenceKey, ToolOutcome]:
    """계획한 호출을 동시에 보낸다. 실패도 값(ToolOutcome)으로 남는다."""

    async def one(call: PrefetchCall) -> ToolOutcome:
        if call.source is ToolSource.TAVILY:
            return await tools.news(
                query=call.args["query"],
                days=call.args["days"],
                max_results=call.args["max_results"],
                request_id=request_id,
            )
        return await tools.call(
            source=call.source,
            server_id=_server_id(setting, call.source),
            tool=call.tool,
            args=call.args,
            run_as_user_id=run_as_user_id,
            request_id=request_id,
        )

    results = await asyncio.gather(*(one(c) for c in calls))
    return {call.key: outcome for call, outcome in zip(calls, results, strict=True)}


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + " …(잘림)"


def _body(outcome: ToolOutcome) -> str:
    if outcome.payload is not None:
        return json.dumps(outcome.payload, ensure_ascii=False, separators=(",", ":"))
    return outcome.text


def _amount(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.replace(",", ""))
        except ValueError:
            return None
    return None


def financial_changes(payload: Any) -> list[dict[str, Any]]:
    """DART 재무 항목의 전기 대비 증감액·증감률을 코드가 계산한다.

    module-10 실측(E3): 에이전트가 직접 계산한 증감률 44개 중 4개가 틀렸다
    (최대 0.22%p). 근거 블록에 계산값을 싣고 지침으로 "직접 계산 금지".
    - 증감률 = 증감액 / |전기| × 100, 소수 둘째 자리 반올림(ROUND_HALF_UP)
    - 전기가 0 이거나 부호가 바뀌면(흑자↔적자) 증감률은 None — 비율이 뜻이 없다
    - 당기·전기 금액 중 하나라도 없으면 그 항목은 만들지 않는다
    """
    items = payload.get("items") if isinstance(payload, dict) else None
    rows: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        current = _amount(item.get("current_amount"))
        previous = _amount(item.get("previous_amount"))
        if current is None or previous is None:
            continue
        change = current - previous
        flipped = current != 0 and (current < 0) != (previous < 0)
        rate: str | None = None
        if previous != 0 and not flipped:
            rate = str(
                (Decimal(change) / abs(Decimal(previous)) * 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )
        rows.append(
            {
                "statement": item.get("statement"),
                "account": item.get("account"),
                "current": current,
                "previous": previous,
                "change": change,
                "change_rate": rate,
            }
        )
    return rows


def _render_financial_changes(outcome: ToolOutcome) -> str | None:
    rows = financial_changes(outcome.payload)
    if not rows:
        return None
    lines = [
        f"[계산 {EvidenceKey.DART_FINANCIALS.value} · 전기 대비 증감] "
        "증감액·증감률은 아래 값을 그대로 쓰고 직접 계산하지 않는다. "
        "'계산 안 함'은 전기 0 또는 흑자·적자 전환이라 비율이 뜻이 없는 경우다."
    ]
    for r in rows:
        rate = (
            f"증감률 {r['change_rate']}%"
            if r["change_rate"] is not None
            else "증감률 계산 안 함"
        )
        lines.append(
            f"- {r['statement'] or ''} {r['account']}: 당기 {r['current']} · 전기 "
            f"{r['previous']} · 증감액 {r['change']} · {rate}"
        )
    return "\n".join(lines)


def render_evidence(
    keys: tuple[EvidenceKey, ...],
    outcomes: dict[EvidenceKey, ToolOutcome],
    *,
    per_item: int = 6000,
    total: int = 20000,
) -> str:
    parts: list[str] = []
    for key in keys:
        outcome = outcomes.get(key)
        if outcome is None:
            parts.append(f"[근거 {key.value}] 데이터 없음 (조회 안 함)")
            continue
        label = f"[근거 {key.value} · {outcome.source.value}:{outcome.tool}]"
        if outcome.is_error:
            parts.append(f"{label} 데이터 없음 ({outcome.error_code or '오류'})")
            continue
        if key is EvidenceKey.DART_FINANCIALS:
            # 계산값을 원문보다 앞에 — 원문이 per_item 에서 잘려도 남는다
            computed = _render_financial_changes(outcome)
            if computed:
                parts.append(computed)
        parts.append(f"{label}\n{_clip(_body(outcome), per_item)}")
    return _clip("\n\n".join(parts), total)
