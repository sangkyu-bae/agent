"""종목 분석 파이프라인 — prefetch → 6섹션 → 전략 → 요약 → 저장 (design §2.3, §10, U10).

가짜 포트로 순서·근거 배분·실패 처리·비용 합산만 본다. 실제 LLM·MCP 는 부르지 않는다.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.market_analysis.pipeline import StockAnalysisPipeline
from src.domain.market_analysis.report import (
    AnalysisTarget,
    ReportStatus,
    SectionStatus,
)
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole

from .fakes import FakeReports, FakeRoles, FakeRunner, FakeTools

SETTING = dataclasses.replace(
    MarketAnalysisSetting.defaults(),
    kis_server_id="kis-1",
    dart_server_id="dart-1",
    perplexity_server_id="pplx-1",
    run_as_user_id="7",
)
TARGET = AnalysisTarget(
    symbol="005930",
    name="삼성전자",
    trade_date=date(2026, 11, 26),
    signals=({"rule": "volume_spike", "values": {"ratio": 3.1}},),
    provisional=False,
    market_context="[시장] KOSPI 4697.51 · 체제 bear",
    round_id=41,
    regime="bear",
)


def _pipeline(tools=None, runner=None, reports=None, roles=None):
    tools = tools or FakeTools()
    runner = runner or FakeRunner()
    reports = reports or FakeReports()
    roles = roles or FakeRoles()
    p = StockAnalysisPipeline(
        tools=tools, runner=runner, reports=reports, roles=roles, logger=MagicMock()
    )
    return p, tools, runner, reports


async def _run(p, setting=SETTING, slots=4):
    return await p.run(
        TARGET, setting, run_slots=asyncio.Semaphore(slots), request_id="r"
    )


async def test_happy_path_order_and_persistence():
    p, tools, runner, reports = _pipeline()
    result = await _run(p)

    assert result.status is ReportStatus.DONE
    assert result.report_id == 1
    agents = [r["agent_id"] for r in runner.runs]
    sections = [r.value for r in AgentRole.section_roles()]
    assert set(agents[:6]) == set(sections)
    assert agents[6:] == ["strategy", "summary"]  # 섹션이 끝난 뒤 전략 → 요약
    assert len(reports.sections) == 6
    assert reports.created[0]["header"].price == "70000"
    finished = reports.finished[0]
    assert finished["status"] is ReportStatus.DONE
    assert (
        finished["strategy"] == "strategy 본문"
        and finished["summary"] == "summary 본문"
    )
    # 에이전트 8회 × (100 토큰, $0.01) + Perplexity 추정 $0.004
    assert finished["tokens"] == 800
    assert finished["cost_usd"] == Decimal("0.084")
    assert (result.tokens, result.cost_usd) == (800, Decimal("0.084"))
    assert result.strategy == "strategy 본문"


async def test_each_section_gets_only_its_evidence_and_header():
    p, _, runner, _ = _pipeline()
    await _run(p)
    by_agent = {r["agent_id"]: r for r in runner.runs}

    tech = by_agent["section_technical"]["reference_context"]
    assert "[머리 사실" in tech and "[근거 daily" in tech and "[근거 indicators" in tech
    assert "[근거 investor" not in tech
    flow = by_agent["section_flow"]["reference_context"]
    assert "[근거 investor" in flow and "[근거 daily" not in flow
    market = by_agent["section_market"]["reference_context"]
    assert "KOSPI 4697.51" in market
    news = by_agent["section_news"]["reference_context"]
    assert "[근거 news" in news and "[근거 research" in news
    # 섹션 질의는 짧고(2000자 이하) 실행자는 설정의 run_as_user_id
    for r in runner.runs:
        assert len(r["query"]) <= 2000 and r["user"] == "7"
    assert "삼성전자(005930)" in by_agent["section_technical"]["query"]


async def test_strategy_sees_all_sections_and_summary_sees_strategy():
    p, _, runner, _ = _pipeline()
    await _run(p)
    by_agent = {r["agent_id"]: r for r in runner.runs}
    strategy_ctx = by_agent["strategy"]["reference_context"]
    for role in AgentRole.section_roles():
        assert f"{role.value} 본문" in strategy_ctx
    assert "strategy 본문" in by_agent["summary"]["reference_context"]


async def test_one_failed_section_makes_partial_but_continues():
    p, _, runner, reports = _pipeline(runner=FakeRunner(fail_agents={"section_news"}))
    result = await _run(p)
    assert result.status is ReportStatus.PARTIAL
    news = next(s for _, s in reports.sections if s.role is AgentRole.SECTION_NEWS)
    assert news.status is SectionStatus.FAILED and news.error.startswith("RUN_FAILED")
    assert (
        "데이터 없음"
        in {r["agent_id"]: r for r in runner.runs}["strategy"]["reference_context"]
    )
    assert result.strategy  # 전략은 계속 나온다


async def test_empty_answer_is_empty_section():
    p, _, _, reports = _pipeline(runner=FakeRunner(empty_agents={"section_flow"}))
    await _run(p)
    flow = next(s for _, s in reports.sections if s.role is AgentRole.SECTION_FLOW)
    assert flow.status is SectionStatus.EMPTY


async def test_missing_quote_fails_without_running_agents():
    tools = FakeTools()
    tools.fail.add("get_quote")
    p, _, runner, reports = _pipeline(tools=tools)
    result = await _run(p)
    assert result.status is ReportStatus.FAILED
    assert runner.runs == []
    assert reports.finished[0]["status"] is ReportStatus.FAILED
    assert reports.evidence  # 실패한 근거도 남긴다


async def test_unmapped_role_fails_that_stage_only():
    roles = FakeRoles()
    del roles.mapping[AgentRole.SECTION_COMPANY]
    del roles.mapping[AgentRole.SUMMARY]
    p, _, runner, reports = _pipeline(roles=roles)
    result = await _run(p)
    company = next(
        s for _, s in reports.sections if s.role is AgentRole.SECTION_COMPANY
    )
    assert company.status is SectionStatus.FAILED and company.error == "ROLE_UNMAPPED"
    assert result.status is ReportStatus.PARTIAL and result.summary is None
    assert "section_company" not in {r["agent_id"] for r in runner.runs}


async def test_run_slots_bound_concurrency():
    runner = FakeRunner()
    p, _, _, _ = _pipeline(runner=runner)
    await _run(p, slots=2)
    assert runner.max_active <= 2


async def test_provisional_target_is_marked_in_queries():
    p, _, runner, _ = _pipeline()
    await p.run(
        dataclasses.replace(TARGET, provisional=True),
        SETTING,
        run_slots=asyncio.Semaphore(4),
        request_id="r",
    )
    assert all("미확정" in r["query"] for r in runner.runs)


async def test_exception_after_report_created_marks_it_failed_and_reraises():
    """중간 점검 I2: 리포트 행을 만든 뒤 예외가 나도 running 으로 남지 않는다."""
    import pytest

    class BoomReports(FakeReports):
        async def save_section(self, *, report_id, section, request_id):
            raise RuntimeError("db down")

    reports = BoomReports()
    p, _, _, _ = _pipeline(reports=reports)
    with pytest.raises(RuntimeError, match="db down"):
        await _run(p)
    assert reports.created and reports.finished[-1]["status"] is ReportStatus.FAILED


async def test_summary_context_is_bounded_even_for_huge_strategy():
    huge = "가" * 60_000
    runner = FakeRunner(answers={"strategy": huge})
    p, _, runner, _ = _pipeline(runner=runner)
    await _run(p)
    summary_ctx = {r["agent_id"]: r for r in runner.runs}["summary"][
        "reference_context"
    ]
    assert len(summary_ctx) <= 40_000
