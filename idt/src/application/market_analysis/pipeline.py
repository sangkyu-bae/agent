"""종목 분석 파이프라인 — 순서는 코드가, 글은 빌더 에이전트가 쓴다.

Design Ref: stock-analysis-agents §2.3, DD3·DD4(asyncio + 단계 기록), §10(실패 모델).

prefetch(동시) → 리포트 행·근거 저장 → 6섹션(동시,
run_slots 로 상한) → 전략 → 요약 → 확정.
- 머리 사실(현재가 등)은 도구 결과에서 그대로 옮긴다.
KIS 시세가 없으면 FAILED — 에이전트를 부르지 않는다
- 섹션 1개 실패·역할 미매핑은 그 단계만 실패, 리포트는
PARTIAL 로 계속 (Plan SC-1 · Design U10)
- 비용 = 에이전트 실행 비용(ai_run) + 외부 과금 도구 추정 비용(Perplexity)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.application.market_analysis.evidence import (
    plan_prefetch,
    render_evidence,
    run_prefetch,
)
from src.application.market_analysis.ports import (
    AgentRunner,
    MarketTools,
    ReportStore,
    RoleAgentStore,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.report import (
    SECTION_EVIDENCE,
    SECTION_TITLES,
    AnalysisTarget,
    EvidenceKey,
    HeaderFacts,
    ReportStatus,
    ReportStatusPolicy,
    SectionResult,
    SectionStatus,
    header_facts_from_quote,
)
from src.domain.market_analysis.runtime import AgentRunOutcome
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole

STRATEGY_CONTEXT_MAX = 38_000
SUMMARY_SECTION_HEAD = 600
SUMMARY_STRATEGY_MAX = 20_000  # 요약 참고 자료에서 섹션 요지가 잘리지 않게


@dataclass(frozen=True)
class PipelineResult:
    report_id: int
    status: ReportStatus
    header: HeaderFacts | None
    strategy: str | None
    summary: str | None
    tokens: int
    cost_usd: Decimal
    failed_sections: tuple[AgentRole, ...] = ()


def _when(target: AnalysisTarget) -> str:
    state = "장중 미확정 봉 기준" if target.provisional else "확정 봉 기준"
    return f"{target.trade_date.isoformat()} ({state})"


def _section_text(section: SectionResult) -> str:
    return section.content if section.status is SectionStatus.DONE else "데이터 없음"


def _query(role: AgentRole, target: AnalysisTarget) -> str:
    title = SECTION_TITLES.get(role, role.value)
    return (
        f"{target.name}({target.symbol}) — '{title}'을(를) 작성하라. "
        f"기준: {_when(target)}. "
        "참고 자료의 수치만 쓰고, "
        "자료에 없으면 '데이터 없음'이라고 적는다."
    )


class StockAnalysisPipeline:
    def __init__(
        self,
        *,
        tools: MarketTools,
        runner: AgentRunner,
        reports: ReportStore,
        roles: RoleAgentStore,
        logger: LoggerInterface,
    ) -> None:
        self._tools = tools
        self._runner = runner
        self._reports = reports
        self._roles = roles
        self._logger = logger

    async def run(
        self,
        target: AnalysisTarget,
        setting: MarketAnalysisSetting,
        *,
        run_slots: asyncio.Semaphore,
        request_id: str,
        today: date | None = None,
    ) -> PipelineResult:
        run_as = setting.run_as_user_id or ""
        calls = plan_prefetch(
            symbol=target.symbol,
            name=target.name,
            setting=setting,
            today=today or target.trade_date,
        )
        outcomes = await run_prefetch(
            self._tools,
            calls,
            setting=setting,
            run_as_user_id=run_as,
            request_id=request_id,
        )
        quote = outcomes.get(EvidenceKey.QUOTE)
        header = header_facts_from_quote(
            symbol=target.symbol,
            name=target.name,
            quote=None if quote is None or quote.is_error else quote.payload,
            signals=target.signals,
            provisional=target.provisional,
            trade_date=target.trade_date,
        )
        report_id = await self._reports.create_report(
            target=target, header=header, request_id=request_id
        )
        # 중간 점검 I2: 리포트 행을 만든 뒤 예외가 나면 failed 로 닫고 다시 던진다
        # (회차는 그 종목을 PIPELINE_ERROR 로 기록한다). running 으로 남기지 않는다.
        try:
            await self._reports.add_evidence(
                report_id=report_id,
                outcomes=list(outcomes.values()),
                request_id=request_id,
            )
            tool_cost = sum((o.cost_usd for o in outcomes.values()), Decimal("0"))

            if header is None:
                # Plan §10: KIS 시세가 없으면 분석 불가 — 에이전트를 부르지 않는다
                await self._reports.finish_report(
                    report_id=report_id,
                    status=ReportStatus.FAILED,
                    strategy=None,
                    summary=None,
                    tokens=0,
                    cost_usd=tool_cost,
                    request_id=request_id,
                )
                return PipelineResult(
                    report_id, ReportStatus.FAILED, None, None, None, 0, tool_cost
                )

            roles = await self._roles.get_all(request_id)
            head = header.render()

            async def section(role: AgentRole) -> SectionResult:
                evidence = render_evidence(SECTION_EVIDENCE[role], outcomes)
                context = f"{head}\n\n{evidence}"
                if role is AgentRole.SECTION_MARKET and target.market_context:
                    context += f"\n\n[시장 맥락 — 회차 계산]\n{target.market_context}"
                result = await self._run_role(
                    role,
                    roles,
                    _query(role, target),
                    context,
                    run_as,
                    run_slots,
                    request_id,
                )
                await self._reports.save_section(
                    report_id=report_id, section=result, request_id=request_id
                )
                return result

            sections = await asyncio.gather(
                *(section(r) for r in AgentRole.section_roles())
            )

            body = "\n\n".join(
                f"## {SECTION_TITLES[s.role]}\n{_section_text(s)}" for s in sections
            )
            strategy = await self._run_role(
                AgentRole.STRATEGY,
                roles,
                _query(AgentRole.STRATEGY, target),
                f"{head}\n\n{body}"[:STRATEGY_CONTEXT_MAX],
                run_as,
                run_slots,
                request_id,
            )
            heads = "\n\n".join(
                f"## {SECTION_TITLES[s.role]}\n{s.content[:SUMMARY_SECTION_HEAD]}"
                for s in sections
                if s.status is SectionStatus.DONE
            )
            strategy_text = (
                strategy.content if strategy.status is SectionStatus.DONE else ""
            )
            summary = await self._run_role(
                AgentRole.SUMMARY,
                roles,
                _query(AgentRole.SUMMARY, target),
                # 중간 점검 I2: 전략 본문이 길어도 참고 자료 상한(40k)을 넘지 않게
                (
                    f"{head}\n\n## 투자 시나리오\n"
                    f"{strategy_text[:SUMMARY_STRATEGY_MAX] or '데이터 없음'}"
                    f"\n\n{heads}"
                )[:STRATEGY_CONTEXT_MAX],
                run_as,
                run_slots,
                request_id,
            )

            strategy_ok = strategy.status is SectionStatus.DONE
            summary_ok = summary.status is SectionStatus.DONE
            status = ReportStatusPolicy.decide(
                quote_ok=True,
                sections={s.role: s.status for s in sections},
                strategy_ok=strategy_ok,
                summary_ok=summary_ok,
            )
            runs = [*sections, strategy, summary]
            tokens = sum(r.tokens for r in runs)
            cost = sum((r.cost_usd for r in runs), Decimal("0")) + tool_cost
            await self._reports.finish_report(
                report_id=report_id,
                status=status,
                strategy=strategy.content if strategy_ok else None,
                summary=summary.content if summary_ok else None,
                tokens=tokens,
                cost_usd=cost,
                request_id=request_id,
            )
            return PipelineResult(
                report_id=report_id,
                status=status,
                header=header,
                strategy=strategy.content if strategy_ok else None,
                summary=summary.content if summary_ok else None,
                tokens=tokens,
                cost_usd=cost,
                failed_sections=tuple(
                    s.role for s in sections if s.status is not SectionStatus.DONE
                ),
            )
        except Exception:
            await self._close_failed(report_id, request_id)
            raise

    async def _close_failed(self, report_id: int, request_id: str) -> None:
        try:
            await self._reports.finish_report(
                report_id=report_id,
                status=ReportStatus.FAILED,
                strategy=None,
                summary=None,
                tokens=0,
                cost_usd=Decimal("0"),
                request_id=request_id,
            )
        except Exception as e:  # noqa: BLE001 — 원래 예외를 가리지 않는다
            self._logger.warning(
                "market_analysis report close failed",
                exception=e,
                request_id=request_id,
                report_id=report_id,
            )

    async def _run_role(
        self,
        role: AgentRole,
        roles: dict[AgentRole, str],
        query: str,
        context: str,
        run_as: str,
        run_slots: asyncio.Semaphore,
        request_id: str,
    ) -> SectionResult:
        agent_id = roles.get(role)
        if not agent_id:
            return SectionResult(
                role=role,
                status=SectionStatus.FAILED,
                content="",
                run_id=None,
                error="ROLE_UNMAPPED",
            )
        async with run_slots:
            outcome: AgentRunOutcome = await self._runner.run(
                agent_id=agent_id,
                query=query,
                reference_context=context,
                run_as_user_id=run_as,
                request_id=request_id,
            )
        if outcome.failed:
            status = SectionStatus.FAILED
        elif not outcome.answer.strip():
            status = SectionStatus.EMPTY
        else:
            status = SectionStatus.DONE
        return SectionResult(
            role=role,
            status=status,
            content=outcome.answer,
            run_id=outcome.run_id,
            tokens=outcome.tokens,
            cost_usd=outcome.cost_usd,
            error=outcome.error,
        )
