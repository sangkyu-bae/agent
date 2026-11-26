"""시장 분석 모듈이 코드로 직접 부를 수 있는 MCP 도구 허용목록.

Design Ref: stock-analysis-agents §4, §11 —
주문(`place_order`·`cancel_order`)·계좌 조회·대량 적재 도구는
목록 밖이다. 목록 밖 도구는 HTTP 호출 전에 거부한다 (Plan NFR 보안, Design U13).
"""

from __future__ import annotations

import re

from src.domain.market_analysis.runtime import ToolSource

ALLOWED_TOOLS: dict[ToolSource, frozenset[str]] = {
    ToolSource.KIS: frozenset(
        {
            "get_quote",
            "get_quotes",
            "get_price_history",
            "compute_indicators",
            "scan_signals",
            "get_rankings",
            "get_investor_flow",
            "get_index_history",
            "list_condition_searches",
            "run_condition_search",
        }
    ),
    ToolSource.DART: frozenset({"find_corp", "get_financials", "list_disclosures"}),
    ToolSource.PERPLEXITY: frozenset({"research"}),
}

_CODE = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+):")


class ToolNotAllowedError(Exception):
    """허용목록 밖 도구."""


class ToolPolicy:
    @staticmethod
    def check(source: ToolSource, tool: str) -> None:
        if tool not in ALLOWED_TOOLS.get(source, frozenset()):
            raise ToolNotAllowedError(f"{source.value}:{tool}")


def parse_error_code(text: str) -> str | None:
    """MCP 서버 오류 메시지 `"{CODE}: 설명"`
    에서 코드를 꺼낸다 (앞에 SDK 머리말이 붙어도)."""
    match = _CODE.search(text or "")
    return match.group(1) if match else None
