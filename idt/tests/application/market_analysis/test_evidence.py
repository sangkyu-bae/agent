"""prefetch 계획·실행 · 근거 블록 렌더 (design §2.3, §1.1-5)."""

from __future__ import annotations

import dataclasses
import json
from datetime import date

from src.application.market_analysis.evidence import (
    plan_prefetch,
    render_evidence,
    run_prefetch,
)
from src.domain.market_analysis.report import EvidenceKey
from src.domain.market_analysis.runtime import ToolOutcome, ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting

from .fakes import FakeTools

SETTING = dataclasses.replace(
    MarketAnalysisSetting.defaults(),
    kis_server_id="kis-1",
    dart_server_id="dart-1",
    perplexity_server_id="pplx-1",
)
TODAY = date(2026, 11, 26)


def _keys(calls):
    return [c.key for c in calls]


def test_plan_covers_all_sources_when_servers_configured():
    calls = plan_prefetch(
        symbol="005930", name="삼성전자", setting=SETTING, today=TODAY
    )
    by_key = {c.key: c for c in calls}
    assert set(by_key) == set(EvidenceKey)
    assert by_key[EvidenceKey.QUOTE].tool == "get_quote"
    assert by_key[EvidenceKey.DAILY].args == {
        "symbol": "005930",
        "interval": "D",
        "limit": 120,
    }
    assert by_key[EvidenceKey.INVESTOR].args == {"symbol": "005930", "days": 20}
    assert by_key[EvidenceKey.DART_FINANCIALS].args == {
        "symbol": "005930",
        "year": 2025,
        "report": "annual",
    }
    assert by_key[EvidenceKey.RESEARCH].source is ToolSource.PERPLEXITY
    assert "삼성전자" in by_key[EvidenceKey.RESEARCH].args["query"]
    assert by_key[EvidenceKey.NEWS].source is ToolSource.TAVILY


def test_plan_skips_unconfigured_servers():
    setting = dataclasses.replace(
        SETTING, dart_server_id=None, perplexity_server_id=None
    )
    keys = _keys(
        plan_prefetch(symbol="005930", name="삼성전자", setting=setting, today=TODAY)
    )
    assert EvidenceKey.DART_FINANCIALS not in keys and EvidenceKey.RESEARCH not in keys
    assert EvidenceKey.QUOTE in keys and EvidenceKey.NEWS in keys


async def test_run_prefetch_returns_outcome_per_key():
    tools = FakeTools()
    calls = plan_prefetch(
        symbol="005930", name="삼성전자", setting=SETTING, today=TODAY
    )
    outcomes = await run_prefetch(
        tools, calls, setting=SETTING, run_as_user_id="7", request_id="r"
    )
    assert set(outcomes) == set(EvidenceKey)
    assert tools.news_calls[0]["days"] == 7
    kis = [c for c in tools.calls if c[0] is ToolSource.KIS]
    assert {c[1] for c in kis} == {
        "get_quote",
        "get_price_history",
        "compute_indicators",
        "get_investor_flow",
    }


def _ok(tool, payload, source=ToolSource.KIS):
    return ToolOutcome(
        source=source,
        tool=tool,
        args={"symbol": "005930"},
        payload=payload,
        text=json.dumps(payload, ensure_ascii=False),
    )


def test_render_labels_sources_and_marks_missing():
    outcomes = {
        EvidenceKey.QUOTE: _ok("get_quote", {"price": "70000"}),
        EvidenceKey.DAILY: ToolOutcome(
            source=ToolSource.KIS,
            tool="get_price_history",
            is_error=True,
            error_code="KIS_TIMEOUT",
        ),
    }
    text = render_evidence(
        (EvidenceKey.QUOTE, EvidenceKey.DAILY, EvidenceKey.INDICATORS), outcomes
    )
    # 근거 JSON 은 토큰을 아끼려 공백 없이 압축한다
    assert "[근거 quote · kis:get_quote]" in text and '"price":"70000"' in text
    assert "[근거 daily · kis:get_price_history] 데이터 없음 (KIS_TIMEOUT)" in text
    assert "[근거 indicators] 데이터 없음 (조회 안 함)" in text


def test_render_bounds_each_item_and_total():
    big = _ok("get_price_history", {"bars": ["x" * 50 for _ in range(1000)]})
    text = render_evidence(
        (EvidenceKey.DAILY,), {EvidenceKey.DAILY: big}, per_item=1000, total=1500
    )
    assert len(text) <= 1500 + 200
    assert "(잘림)" in text


# ── module-10 실측 G1: 재무 증감 4/44 소오차 → 코드가 미리 계산 ──


def _fin_item(account, current, previous, statement="IS"):
    return {
        "statement": statement,
        "account": account,
        "current_amount": current,
        "previous_amount": previous,
        "currency": "KRW",
    }


def test_financial_changes_compute_amount_and_rate_deterministically():
    from src.application.market_analysis.evidence import financial_changes

    rows = financial_changes(
        {
            "items": [
                # 실측(HC홈센타) 오차 사례: 에이전트는 -19.02%·-12.53% 로 썼다
                _fin_item("매출액", 298_824_352_914, 369_039_055_143),
                _fin_item("유동자산", 135_639_915_524, 155_082_911_584, "BS"),
                # 흑자 → 적자: 에이전트는 -250.34% 를 썼지만 비율 자체가 뜻이 없다
                _fin_item("영업이익", -18_513_534_433, 12_312_167_768),
            ]
        }
    )
    by = {r["account"]: r for r in rows}
    assert by["매출액"]["change"] == -70_214_702_229
    assert by["매출액"]["change_rate"] == "-19.03"
    assert by["유동자산"]["change"] == -19_442_996_060
    assert by["유동자산"]["change_rate"] == "-12.54"
    assert by["영업이익"]["change"] == -30_825_702_201
    assert by["영업이익"]["change_rate"] is None


def test_financial_changes_skip_rate_when_base_zero_or_sign_flips():
    from src.application.market_analysis.evidence import financial_changes

    rows = financial_changes(
        {
            "items": [
                _fin_item("당기순이익", -5_000, 10_000),  # 흑자 → 적자: 비율 의미 없음
                _fin_item("기타", 100, 0),
                _fin_item("값없음", None, 100),
            ]
        }
    )
    by = {r["account"]: r for r in rows}
    assert by["당기순이익"]["change"] == -15_000
    assert by["당기순이익"]["change_rate"] is None
    assert by["기타"]["change_rate"] is None
    assert "값없음" not in by  # 금액이 없으면 행을 만들지 않는다
    assert financial_changes({"no_items": 1}) == []
    assert financial_changes(None) == []


def test_render_puts_computed_changes_before_raw_financials():
    payload = {"items": [_fin_item("매출액", 1_200, 1_000)]}
    text = render_evidence(
        (EvidenceKey.DART_FINANCIALS,),
        {EvidenceKey.DART_FINANCIALS: _ok("get_financials", payload, ToolSource.DART)},
    )
    calc_at = text.index("[계산 dart_financials")
    raw_at = text.index("[근거 dart_financials · dart:get_financials]")
    assert calc_at < raw_at  # 원문이 잘려도 계산값은 남는다
    assert "매출액" in text and "증감액 200" in text and "증감률 20.00%" in text
    assert "직접 계산하지" in text


# ── 리포트 표현 보강: 수급 거래대금 단위 (에이전트가 단위를 추측했다) ──


def test_render_states_investor_amount_unit():
    """KIS *_net_amount 는 백만 원 — 실측 amount/(qty×close) 중앙값 0.9986e-6."""
    payload = {
        "symbol": "005930",
        "days": [
            {
                "date": "2026-11-26",
                "close": "9000",
                "individual_net_qty": -15670,
                "individual_net_amount": "-143",
            }
        ],
    }
    text = render_evidence(
        (EvidenceKey.INVESTOR,),
        {EvidenceKey.INVESTOR: _ok("get_investor_flow", payload)},
    )
    unit_at = text.index("[단위 investor]")
    raw_at = text.index("[근거 investor · kis:get_investor_flow]")
    assert unit_at < raw_at
    assert "백만 원" in text and "추정하지 않는다" in text


def test_unit_note_is_absent_when_investor_failed():
    failed = ToolOutcome(
        source=ToolSource.KIS,
        tool="get_investor_flow",
        is_error=True,
        error_code="KIS_TIMEOUT",
    )
    text = render_evidence((EvidenceKey.INVESTOR,), {EvidenceKey.INVESTOR: failed})
    assert "[단위 investor]" not in text and "데이터 없음 (KIS_TIMEOUT)" in text
