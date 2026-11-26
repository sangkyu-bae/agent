"""리포트·근거·섹션·역할 매핑 저장소 (SQLite 실제 세션) — design §3.3."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.market_analysis.report import (
    AnalysisTarget,
    ReportStatus,
    SectionResult,
    SectionStatus,
    header_facts_from_quote,
)
from src.domain.market_analysis.runtime import ToolOutcome, ToolSource
from src.domain.market_analysis.value_objects import AgentRole
from src.infrastructure.market_analysis.models import (
    MaEvidenceModel,
    MaReportModel,
    MaReportSectionModel,
    MaRoleAgentModel,
)
from src.infrastructure.market_analysis.report_repository import (
    ReportRepository,
    RoleAgentRepository,
)
from src.infrastructure.persistence.models.base import Base

TARGET = AnalysisTarget(
    symbol="005930",
    name="삼성전자",
    trade_date=date(2026, 11, 26),
    signals=({"rule": "gap", "values": {"change_pct": 3.2}},),
    provisional=True,
    round_id=41,
    regime="bear",
)
HEADER = header_facts_from_quote(
    symbol="005930",
    name="삼성전자",
    quote={"price": "70000", "change": "-500", "change_rate": "-0.71", "volume": 10},
    signals=TARGET.signals,
    provisional=True,
    trade_date=TARGET.trade_date,
)


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c,
                tables=[
                    MaReportModel.__table__,
                    MaReportSectionModel.__table__,
                    MaEvidenceModel.__table__,
                    MaRoleAgentModel.__table__,
                ],
            )
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        os.unlink(tmp.name)


async def test_report_lifecycle(factory):
    repo = ReportRepository(factory, MagicMock())
    rid = await repo.create_report(target=TARGET, header=HEADER, request_id="r")
    await repo.add_evidence(
        report_id=rid,
        request_id="r",
        outcomes=[
            ToolOutcome(
                source=ToolSource.KIS,
                tool="get_quote",
                args={"symbol": "005930"},
                payload={"price": "70000"},
                text='{"price":"70000"}',
            ),
            ToolOutcome(
                source=ToolSource.DART,
                tool="find_corp",
                args={"symbol": "005930"},
                is_error=True,
                error_code="DART_AUTH_FAILED",
                text="DART_AUTH_FAILED: x",
            ),
        ],
    )
    await repo.save_section(
        report_id=rid,
        request_id="r",
        section=SectionResult(
            role=AgentRole.SECTION_TECHNICAL,
            status=SectionStatus.DONE,
            content="## 기술",
            run_id="run-1",
            tokens=120,
            cost_usd=Decimal("0.0123"),
        ),
    )
    await repo.finish_report(
        report_id=rid,
        status=ReportStatus.PARTIAL,
        strategy="전략",
        summary=None,
        tokens=999,
        cost_usd=Decimal("0.5"),
        request_id="r",
    )

    async with factory() as s:
        report = (await s.execute(select(MaReportModel))).scalar_one()
        evidence = (
            (await s.execute(select(MaEvidenceModel).order_by(MaEvidenceModel.id)))
            .scalars()
            .all()
        )
        section = (await s.execute(select(MaReportSectionModel))).scalar_one()
    assert (report.symbol, report.round_id, report.regime) == ("005930", 41, "bear")
    assert report.provisional is True and report.signals[0]["rule"] == "gap"
    assert report.header_facts["price"] == "70000"
    assert (report.status, report.strategy, report.summary) == ("partial", "전략", None)
    assert (report.tokens, Decimal(str(report.cost_usd))) == (999, Decimal("0.5"))
    assert [(e.source, e.tool, e.is_error) for e in evidence] == [
        ("kis", "get_quote", False),
        ("dart", "find_corp", True),
    ]
    assert json.loads(evidence[0].payload) == {"price": "70000"}
    assert evidence[1].payload.startswith("DART_AUTH_FAILED")
    assert (section.role, section.status, section.run_id, section.tokens) == (
        "section_technical",
        "done",
        "run-1",
        120,
    )


async def test_report_without_header_starts_running(factory):
    repo = ReportRepository(factory, MagicMock())
    rid = await repo.create_report(target=TARGET, header=None, request_id="r")
    async with factory() as s:
        report = await s.get(MaReportModel, rid)
    assert report.status == "running" and report.header_facts is None


async def test_role_agent_store_upserts(factory):
    repo = RoleAgentRepository(factory, MagicMock())
    assert await repo.get_all("r") == {}
    await repo.set(
        role=AgentRole.BUY_JUDGE, agent_id="a1", updated_by="7", request_id="r"
    )
    await repo.set(
        role=AgentRole.BUY_JUDGE, agent_id="a2", updated_by="7", request_id="r"
    )
    await repo.set(
        role=AgentRole.SUMMARY, agent_id="s1", updated_by="7", request_id="r"
    )
    assert await repo.get_all("r") == {
        AgentRole.BUY_JUDGE: "a2",
        AgentRole.SUMMARY: "s1",
    }


async def test_unknown_role_rows_are_ignored(factory):
    async with factory() as s, s.begin():
        from datetime import datetime

        s.add(
            MaRoleAgentModel(
                role="legacy_role", agent_id="x", updated_at=datetime(2026, 1, 1)
            )
        )
    assert await RoleAgentRepository(factory, MagicMock()).get_all("r") == {}
