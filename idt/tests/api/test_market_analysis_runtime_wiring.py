"""시장 분석 런타임 조립·시작·정지 — design §2.1, DD6 (module-5).

플랫폼 의존성은 가짜로 넘긴다. 조립 단계에서 네트워크·DB 를 건드리지 않는지,
플래그에 따라 회차 실행기가 켜지는지, 꺼진 모듈은
platform_factory 를 부르지 않는지 본다.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from src.api import market_analysis_di as di


def _platform(calls: list[str]) -> di.MarketAnalysisPlatform:
    def boom(*_a, **_k):
        raise AssertionError("assembly must not touch the platform")

    calls.append("platform")
    return di.MarketAnalysisPlatform(
        session_factory=boom,
        run_agent_uc_builder=boom,
        create_agent_uc_builder=boom,
        auth_ctx_assembler=boom,
        mcp_server_finder=boom,
        mcp_client_factory=boom,
        news_search=boom,
        utility_llm_provider=SimpleNamespace(),
    )


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(di, "_runtime", None)
    monkeypatch.setattr(di, "_ticker_wanted", False)


def _parts(ticker: bool):
    return di.MarketAnalysisParts(ticker_enabled=ticker, logger=MagicMock())


def test_disabled_module_never_builds_the_platform(monkeypatch):
    monkeypatch.setattr(di, "get_market_analysis", lambda: None)
    calls: list[str] = []
    assert di.wire_market_analysis(FastAPI(), lambda: _platform(calls)) is False
    assert calls == [] and di.get_runtime() is None
    assert di.start_market_analysis() is False


async def test_enabled_module_builds_runtime_and_ticker_runs(monkeypatch):
    monkeypatch.setattr(di, "get_market_analysis", lambda: _parts(ticker=True))
    calls: list[str] = []
    assert di.wire_market_analysis(FastAPI(), lambda: _platform(calls)) is True
    runtime = di.get_runtime()
    assert calls == ["platform"] and runtime is not None
    started: list[bool] = []
    runtime.ticker.start = lambda: started.append(True)  # type: ignore[method-assign]
    assert di.start_market_analysis() is True and started == [True]
    stopped: list[bool] = []

    async def stop():
        stopped.append(True)

    runtime.ticker.stop = stop  # type: ignore[method-assign]
    await di.close_market_analysis()
    assert stopped == [True]


def test_ticker_flag_off_keeps_api_but_not_rounds(monkeypatch):
    monkeypatch.setattr(di, "get_market_analysis", lambda: _parts(ticker=False))
    assert di.wire_market_analysis(FastAPI(), lambda: _platform([])) is True
    assert di.get_runtime() is not None
    assert di.start_market_analysis() is False


def test_runtime_assembly_failure_keeps_the_api(monkeypatch):
    monkeypatch.setattr(di, "get_market_analysis", lambda: _parts(ticker=True))

    def broken():
        raise RuntimeError("mcp registry down")

    app = FastAPI()
    assert di.wire_market_analysis(app, broken) is True
    assert di.get_runtime() is None and di.start_market_analysis() is False
    assert "/api/v1/market-analysis/access" in set(app.openapi()["paths"])


async def test_close_without_runtime_is_noop():
    await di.close_market_analysis()
    await asyncio.sleep(0)


def test_api_dependency_points_at_runtime_or_none(monkeypatch):
    """module-8: 라우터의 서비스 의존성은 런타임을 가리키고, 조립 실패면 None(503)."""
    from src.api.routes import market_analysis_router as ma_router

    monkeypatch.setattr(di, "get_market_analysis", lambda: _parts(ticker=False))
    app = FastAPI()
    assert di.wire_market_analysis(app, lambda: _platform([])) is True
    provide = app.dependency_overrides[ma_router.get_market_analysis_api]
    runtime = provide()
    assert runtime is di.get_runtime()
    assert runtime.queries is not None and runtime.run_now is not None
    assert runtime.index_chart is not None

    def broken():
        raise RuntimeError("platform down")

    monkeypatch.setattr(di, "_runtime", None)
    app = FastAPI()
    assert di.wire_market_analysis(app, broken) is True
    assert app.dependency_overrides[ma_router.get_market_analysis_api]() is None
