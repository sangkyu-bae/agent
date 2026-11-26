"""도구 허용목록 — stock-analysis-agents design
§4 "주문 도구는 허용 목록 밖", §11 보안, U13."""

import pytest
from src.domain.market_analysis.runtime import ToolSource
from src.domain.market_analysis.tool_policy import (
    ToolNotAllowedError,
    ToolPolicy,
    parse_error_code,
)


@pytest.mark.parametrize(
    ("source", "tool"),
    [
        (ToolSource.KIS, "get_quote"),
        (ToolSource.KIS, "get_quotes"),
        (ToolSource.KIS, "get_price_history"),
        (ToolSource.KIS, "compute_indicators"),
        (ToolSource.KIS, "scan_signals"),
        (ToolSource.KIS, "get_rankings"),
        (ToolSource.KIS, "get_investor_flow"),
        (ToolSource.KIS, "get_index_history"),
        (ToolSource.KIS, "list_condition_searches"),
        (ToolSource.KIS, "run_condition_search"),
        (ToolSource.DART, "find_corp"),
        (ToolSource.DART, "get_financials"),
        (ToolSource.DART, "list_disclosures"),
        (ToolSource.PERPLEXITY, "research"),
    ],
)
def test_allowed(source, tool):
    ToolPolicy.check(source, tool)


@pytest.mark.parametrize(
    "tool",
    [
        "place_order",
        "cancel_order",
        "get_balance",
        "list_orders",
        "collect_price_history",
        "collect_daily_snapshot",
    ],
)
def test_kis_trading_and_bulk_tools_are_refused(tool):
    with pytest.raises(ToolNotAllowedError):
        ToolPolicy.check(ToolSource.KIS, tool)


def test_unknown_tool_on_other_server_is_refused():
    with pytest.raises(ToolNotAllowedError):
        ToolPolicy.check(ToolSource.DART, "get_quote")


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("RATE_LIMITED: 한도 초과", "RATE_LIMITED"),
        (
            "DART_AUTH_FAILED: OPENDART_API_KEY 가 설정되지 않았습니다",
            "DART_AUTH_FAILED",
        ),
        ("Error executing tool get_quote: KIS_TIMEOUT: 시간 초과", "KIS_TIMEOUT"),
        ("그냥 실패", None),
        ("", None),
    ],
)
def test_parse_error_code(text, code):
    assert parse_error_code(text) == code
