"""회차 1회 실행 — 체제 → 보유 관리 → 후보 → 스캔 → 상한 → 분석·매수 판단 → 성과 → 집계.

Design Ref: stock-analysis-agents §2.2, §10, Plan FR-02~FR-04 · FR-17 · SC-4.
- ① 체제: KOSPI·KOSDAQ 조회. 평일 09:10 이후인데
오늘 KOSPI 봉이 없으면 skipped(HOLIDAY) (U8)
- ② 보유 관리: 후보 수집보다 먼저 — 목표·손절 도달 청산, 그 밖에는 매도 판단
- 상한: RoundCapPolicy — 넘친 종목은 over_cap, 오늘 이미 분석한 종목은 duplicate,
  보유 종목은 held
- 종목 단위 실패(리포트 failed·예외)는 그 종목만 failed, 회차는 done 으로 끝난다
- 동시성: 종목은 max_concurrent_stocks, 에이전트 실행은 max_concurrent_runs 를
  모든 단계가 같이 쓴다
- after_report: 매수 판단(judgement.BuyJudgement).
실패해도 회차·종목 결과를 바꾸지 않는다.
  (토큰, 비용)을 돌려주면 종목·회차 집계에 더한다
- ⑧ close 회차 끝에 성과 스냅샷
- 판단 역할(buy_judge·sell_judge) 매핑이 없으면 회차 시작 전 failed (§10)
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.application.market_analysis.candidates import (
    ScanUnavailableError,
    collect_candidates,
    scan_candidates,
)
from src.application.market_analysis.performance import PerformanceRecorder
from src.application.market_analysis.ports import (
    HeldReader,
    MarketTools,
    RoleAgentStore,
    RoundStore,
)
from src.application.market_analysis.positions import ManageResult, PositionManager
from src.application.market_analysis.regime import MarketRegimeService, MarketSnapshot
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.report import AnalysisTarget, ReportStatus
from src.domain.market_analysis.round import (
    RoundCapPolicy,
    RoundCounts,
    RoundItemDraft,
    RoundSchedulePolicy,
    SignaledCandidate,
    SkipReason,
)
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import (
    AgentRole,
    ItemStatus,
    RoundKind,
    RoundStatus,
)

AfterReport = Callable[
    [AnalysisTarget, Any, MarketAnalysisSetting, str], Awaitable[Any]
]
JUDGE_ROLES = (AgentRole.BUY_JUDGE, AgentRole.SELL_JUDGE)
_ZERO = Decimal("0")


class RoundRunner:
    def __init__(
        self,
        *,
        tools: MarketTools,
        pipeline: Any,
        rounds: RoundStore,
        held: HeldReader,
        logger: LoggerInterface,
        now_utc: Callable[[], datetime],
        after_report: AfterReport | None = None,
        market: MarketRegimeService | None = None,
        positions: PositionManager | None = None,
        performance: PerformanceRecorder | None = None,
        roles: RoleAgentStore | None = None,
    ) -> None:
        self._tools = tools
        self._pipeline = pipeline
        self._rounds = rounds
        self._held = held
        self._logger = logger
        self._now_utc = now_utc
        self._after_report = after_report
        self._market = market or MarketRegimeService(
            tools=tools, regimes=None, logger=logger
        )
        self._positions = positions
        self._performance = performance
        self._roles = roles

    async def run(
        self,
        *,
        round_id: int,
        trade_date: date,
        kind: RoundKind,
        setting: MarketAnalysisSetting,
        request_id: str,
    ) -> None:
        try:
            await self._run(round_id, trade_date, kind, setting, request_id)
        except Exception as e:  # noqa: BLE001 — 회차 행이 running 으로 남지 않게
            self._logger.error(
                "market_analysis round failed",
                exception=e,
                request_id=request_id,
                round_id=round_id,
            )
            await self._rounds.finish_round(
                round_id=round_id,
                status=RoundStatus.FAILED,
                counts=RoundCounts(),
                error=f"ROUND_ERROR: {str(e)[:300]}",
                request_id=request_id,
            )

    async def _run(
        self,
        round_id: int,
        trade_date: date,
        kind: RoundKind,
        setting: MarketAnalysisSetting,
        request_id: str,
    ) -> None:
        if not setting.kis_server_id:
            await self._fail(round_id, "KIS_NOT_CONFIGURED", request_id)
            return
        if not setting.run_as_user_id:
            await self._fail(round_id, "RUN_AS_USER_MISSING", request_id)
            return
        missing = await self._missing_judge_roles(request_id)
        if missing:
            await self._fail(
                round_id, f"ROLE_UNMAPPED({','.join(missing)})", request_id
            )
            return

        # ① 체제
        snapshot = await self._market.snapshot(setting, request_id)
        if snapshot.kis_error:
            # Design §10: KIS 서버 비활성·인증 실패 → 회차 failed ('신호 없음'과 구분)
            await self._fail(
                round_id, f"KIS_UNAVAILABLE({snapshot.kis_error})", request_id
            )
            return
        now_kst = RoundSchedulePolicy.to_kst(self._now_utc())
        if RoundSchedulePolicy.is_holiday(now_kst, snapshot.kospi_day):
            await self._rounds.skip(
                round_id=round_id, reason=SkipReason.HOLIDAY, request_id=request_id
            )
            return
        await self._market.save(
            trade_date=trade_date, snapshot=snapshot, request_id=request_id
        )
        run_slots = asyncio.Semaphore(max(1, setting.max_concurrent_runs))

        # ② 보유 관리 — 후보보다 먼저 (청산된 종목은 오늘 다시 후보가 될 수 있다)
        managed = await self._manage(setting, snapshot, kind, run_slots, request_id)

        # ③④⑤ 후보 · 스캔 · 상한
        candidates = await collect_candidates(
            self._tools, setting, request_id=request_id
        )
        try:
            signaled = await scan_candidates(
                self._tools, setting, candidates, request_id=request_id
            )
        except ScanUnavailableError as e:
            # '신호 0건'과 '스캔 못 함'을 구분한다 (실화면 확인 결함)
            await self._fail(round_id, f"SCAN_FAILED({e.code})", request_id)
            return
        decision = RoundCapPolicy.decide(
            signaled,
            analyzed_today=await self._rounds.analyzed_symbols(
                trade_date=trade_date, request_id=request_id
            ),
            held=await self._held.held_symbols(request_id),
            max_per_round=setting.max_per_round,
            max_per_day=setting.max_per_day,
            attempts_today=await self._rounds.analysis_attempts(
                trade_date=trade_date, request_id=request_id
            ),
        )
        drafts = [
            *(self._draft(c, ItemStatus.QUEUED) for c in decision.selected),
            *(self._draft(c, ItemStatus.OVER_CAP) for c in decision.over_cap),
            *(self._draft(c, ItemStatus.HELD) for c in decision.held),
            *(self._draft(c, ItemStatus.DUPLICATE) for c in decision.duplicate),
        ]
        ids = (
            await self._rounds.add_items(
                round_id=round_id, items=drafts, request_id=request_id
            )
            if drafts
            else {}
        )

        # ⑥ 종목 분석 + 매수 판단
        stock_slots = asyncio.Semaphore(max(1, setting.max_concurrent_stocks))

        async def analyze(candidate: SignaledCandidate) -> tuple[bool, int, Decimal]:
            async with stock_slots:
                return await self._analyze(
                    candidate,
                    ids[candidate.symbol],
                    round_id,
                    trade_date,
                    kind,
                    setting,
                    snapshot,
                    run_slots,
                    request_id,
                )

        results = await asyncio.gather(*(analyze(c) for c in decision.selected))

        # ⑧ 성과 스냅샷 (close 회차)
        if kind is RoundKind.CLOSE:
            await self._record_performance(trade_date, snapshot, setting, request_id)

        analyzed = sum(1 for ok, _, _ in results if ok)
        await self._rounds.finish_round(
            round_id=round_id,
            status=RoundStatus.DONE,
            counts=RoundCounts(
                candidates=len(candidates),
                signaled=len(signaled),
                analyzed=analyzed,
                over_cap=len(decision.over_cap),
                failed=len(results) - analyzed,
                tokens=managed.tokens + sum(t for _, t, _ in results),
                cost_usd=managed.cost_usd + sum((c for _, _, c in results), _ZERO),
            ),
            error=None,
            request_id=request_id,
        )

    async def _missing_judge_roles(self, request_id: str) -> list[str]:
        if self._roles is None:
            return []
        mapping = await self._roles.get_all(request_id)
        return [role.value for role in JUDGE_ROLES if not mapping.get(role)]

    async def _manage(
        self,
        setting: MarketAnalysisSetting,
        snapshot: MarketSnapshot,
        kind: RoundKind,
        run_slots: asyncio.Semaphore,
        request_id: str,
    ) -> ManageResult:
        if self._positions is None:
            return ManageResult()
        try:
            return await self._positions.manage(
                setting,
                regime=snapshot.regime.regime.value,
                provisional=kind is RoundKind.INTRADAY,
                run_slots=run_slots,
                request_id=request_id,
            )
        except Exception as e:  # noqa: BLE001 — 보유 관리 실패가 신규 분석을 막지 않는다
            self._logger.warning(
                "market_analysis position management failed",
                exception=e,
                request_id=request_id,
            )
            return ManageResult()

    async def _record_performance(
        self,
        trade_date: date,
        snapshot: MarketSnapshot,
        setting: MarketAnalysisSetting,
        request_id: str,
    ) -> None:
        if self._performance is None:
            return
        try:
            await self._performance.record(
                trade_date=trade_date,
                snapshot=snapshot,
                setting=setting,
                request_id=request_id,
            )
        except Exception as e:  # noqa: BLE001
            self._logger.warning(
                "market_analysis performance snapshot failed",
                exception=e,
                request_id=request_id,
            )

    async def _analyze(
        self,
        candidate: SignaledCandidate,
        item_id: int,
        round_id: int,
        trade_date: date,
        kind: RoundKind,
        setting: MarketAnalysisSetting,
        snapshot: MarketSnapshot,
        run_slots: asyncio.Semaphore,
        request_id: str,
    ) -> tuple[bool, int, Decimal]:
        await self._rounds.update_item(
            item_id=item_id, status=ItemStatus.ANALYZING, request_id=request_id
        )
        target = AnalysisTarget(
            symbol=candidate.symbol,
            name=candidate.name,
            trade_date=trade_date,
            signals=candidate.signals,
            provisional=kind is RoundKind.INTRADAY
            or any(s.get("provisional") for s in candidate.signals),
            market_context=snapshot.context,
            round_id=round_id,
            regime=snapshot.regime.regime.value,
        )
        try:
            result = await self._pipeline.run(
                target, setting, run_slots=run_slots, request_id=request_id
            )
        except Exception as e:  # noqa: BLE001 — 한 종목 실패가 회차를 멈추지 않는다
            self._logger.warning(
                "market_analysis stock analysis failed",
                exception=e,
                request_id=request_id,
                symbol=candidate.symbol,
            )
            await self._rounds.update_item(
                item_id=item_id,
                status=ItemStatus.FAILED,
                error=f"PIPELINE_ERROR: {str(e)[:300]}",
                request_id=request_id,
            )
            return False, 0, _ZERO

        ok = result.status is not ReportStatus.FAILED
        tokens, cost = result.tokens, result.cost_usd
        if ok:
            extra_tokens, extra_cost = await self._judge(
                target, result, setting, request_id
            )
            tokens, cost = tokens + extra_tokens, cost + extra_cost
        await self._rounds.update_item(
            item_id=item_id,
            status=ItemStatus.DONE if ok else ItemStatus.FAILED,
            report_id=result.report_id,
            tokens=tokens,
            cost_usd=cost,
            error=None if ok else "REPORT_FAILED",
            request_id=request_id,
        )
        return ok, tokens, cost

    async def _judge(
        self,
        target: AnalysisTarget,
        result: Any,
        setting: MarketAnalysisSetting,
        request_id: str,
    ) -> tuple[int, Decimal]:
        if self._after_report is None:
            return 0, _ZERO
        try:
            extra = await self._after_report(target, result, setting, request_id)
        except Exception as e:  # noqa: BLE001
            self._logger.warning(
                "market_analysis after_report failed",
                exception=e,
                request_id=request_id,
                symbol=target.symbol,
            )
            return 0, _ZERO
        if isinstance(extra, tuple) and len(extra) == 2:
            return int(extra[0]), Decimal(extra[1])
        return 0, _ZERO

    @staticmethod
    def _draft(candidate: SignaledCandidate, status: ItemStatus) -> RoundItemDraft:
        return RoundItemDraft(
            symbol=candidate.symbol,
            name=candidate.name,
            signals=candidate.signals,
            status=status.value,
        )

    async def _fail(self, round_id: int, error: str, request_id: str) -> None:
        await self._rounds.finish_round(
            round_id=round_id,
            status=RoundStatus.FAILED,
            counts=RoundCounts(),
            error=error,
            request_id=request_id,
        )
