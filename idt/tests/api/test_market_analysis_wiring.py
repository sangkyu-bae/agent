"""시장 분석 모듈 조립·킬스위치 — stock-analysis-agents
design §15 env, §5 (플래그 off → 404)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from src.api import market_analysis_di as di


def _settings(enabled: bool = True, ticker: bool = True):
    return SimpleNamespace(
        market_analysis_enabled=enabled, market_analysis_ticker_enabled=ticker
    )


def test_disabled_builds_nothing():
    logger = MagicMock()
    assert di.build_market_analysis(_settings(enabled=False), logger) is None
    logger.info.assert_not_called()


def test_enabled_builds_parts_and_logs_once():
    logger = MagicMock()
    parts = di.build_market_analysis(_settings(ticker=False), logger)
    assert parts is not None
    assert parts.ticker_enabled is False
    assert logger.info.call_args.args[0] == "market_analysis enabled"


def test_assembly_failure_returns_none_and_warns():
    logger = MagicMock()
    broken = SimpleNamespace(market_analysis_enabled=True)  # ticker 필드 없음
    assert di.build_market_analysis(broken, logger) is None
    assert "assembly failed" in logger.warning.call_args.args[0]


def _paths(app: FastAPI) -> set[str]:
    return set(app.openapi()["paths"])


def test_wire_registers_routes_only_when_enabled(monkeypatch):
    monkeypatch.setattr(di, "get_market_analysis", lambda: None)
    off = FastAPI()
    assert di.wire_market_analysis(off) is False
    assert not any(p.startswith("/api/v1/market-analysis") for p in _paths(off))

    parts = di.build_market_analysis(_settings(), MagicMock())
    monkeypatch.setattr(di, "get_market_analysis", lambda: parts)
    on = FastAPI()
    assert di.wire_market_analysis(on) is True
    assert "/api/v1/market-analysis/access" in _paths(on)
