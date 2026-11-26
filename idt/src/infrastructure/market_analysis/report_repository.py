"""리포트·근거·섹션 · 역할 매핑 저장소
(application.ports.ReportStore · RoleAgentStore 구현).

Design Ref: stock-analysis-agents §3.3.
회차가 요청 밖(ticker)에서 돌기 때문에 세션 팩토리를 받아
동작마다 짧은 트랜잭션을 연다 — 섹션 하나가 실패해도 앞서 저장한 행은 남는다.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.report import (
    AnalysisTarget,
    HeaderFacts,
    ReportStatus,
    SectionResult,
)
from src.domain.market_analysis.runtime import ToolOutcome
from src.domain.market_analysis.value_objects import AgentRole
from src.infrastructure.market_analysis.models import (
    MaEvidenceModel,
    MaReportModel,
    MaReportSectionModel,
    MaRoleAgentModel,
)

_PAYLOAD_MAX = 200_000  # MEDIUMTEXT 안쪽으로 자른다


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _payload(outcome: ToolOutcome) -> str:
    if outcome.payload is not None and not outcome.is_error:
        text = json.dumps(outcome.payload, ensure_ascii=False)
    else:
        text = outcome.text
    return text[:_PAYLOAD_MAX]


class ReportRepository:
    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def create_report(
        self, *, target: AnalysisTarget, header: HeaderFacts | None, request_id: str
    ) -> int:
        row = MaReportModel(
            symbol=target.symbol,
            name=target.name,
            trade_date=target.trade_date,
            round_id=target.round_id,
            provisional=target.provisional,
            signals=list(target.signals),
            header_facts=header.to_dict() if header else None,
            regime=target.regime,
            status=ReportStatus.RUNNING.value,
            tokens=0,
            cost_usd=Decimal("0"),
            created_at=_now(),
        )
        async with self._sf() as session, session.begin():
            session.add(row)
            await session.flush()
            return int(row.id)

    async def add_evidence(
        self, *, report_id: int, outcomes: list[ToolOutcome], request_id: str
    ) -> None:
        now = _now()
        async with self._sf() as session, session.begin():
            for outcome in outcomes:
                session.add(
                    MaEvidenceModel(
                        report_id=report_id,
                        source=outcome.source.value,
                        tool=outcome.tool,
                        args=dict(outcome.args),
                        payload=_payload(outcome),
                        is_error=outcome.is_error,
                        fetched_at=now,
                    )
                )

    async def save_section(
        self, *, report_id: int, section: SectionResult, request_id: str
    ) -> None:
        async with self._sf() as session, session.begin():
            session.add(
                MaReportSectionModel(
                    report_id=report_id,
                    role=section.role.value,
                    status=section.status.value,
                    content=section.content or None,
                    run_id=section.run_id,
                    tokens=section.tokens,
                    cost_usd=section.cost_usd,
                    created_at=_now(),
                )
            )

    async def finish_report(
        self,
        *,
        report_id: int,
        status: ReportStatus,
        strategy: str | None,
        summary: str | None,
        tokens: int,
        cost_usd: Decimal,
        request_id: str,
    ) -> None:
        async with self._sf() as session, session.begin():
            await session.execute(
                update(MaReportModel)
                .where(MaReportModel.id == report_id)
                .values(
                    status=status.value,
                    strategy=strategy,
                    summary=summary,
                    tokens=tokens,
                    cost_usd=cost_usd,
                )
            )


class RoleAgentRepository:
    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def get_all(self, request_id: str) -> dict[AgentRole, str]:
        async with self._sf() as session:
            rows = (await session.execute(select(MaRoleAgentModel))).scalars().all()
        mapping: dict[AgentRole, str] = {}
        for row in rows:
            try:
                mapping[AgentRole(row.role)] = row.agent_id
            except ValueError:
                self._logger.warning(
                    "market_analysis unknown role row ignored",
                    request_id=request_id,
                    role=row.role,
                )
        return mapping

    async def set(
        self, *, role: AgentRole, agent_id: str, updated_by: str, request_id: str
    ) -> None:
        async with self._sf() as session, session.begin():
            row = await session.get(MaRoleAgentModel, role.value)
            if row is None:
                session.add(
                    MaRoleAgentModel(
                        role=role.value,
                        agent_id=agent_id,
                        updated_by=updated_by,
                        updated_at=_now(),
                    )
                )
            else:
                row.agent_id = agent_id
                row.updated_by = updated_by
                row.updated_at = _now()
