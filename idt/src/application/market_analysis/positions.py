"""보유 관리 — 회차 ② (후보 수집보다 먼저).

Design Ref: stock-analysis-agents §2.2 ②, §6 ExitPolicy, §7 sell_judge, Plan SC-4.
1. 보유 종목 시세를 get_quotes 로 한 번에(30개씩) 읽는다
2. 현재가 ≤ 손절 → STOP, ≥ 목표 → TARGET — 에이전트 없이 결정론으로 청산한다
3. 그 밖에는 매도 판단 에이전트(hold · sell · adjust).
   adjust 는 새 손절 < 현재가 < 새 목표일 때만 반영하고, 아니면 사유만 남긴다
   파싱 실패·실행 실패는 hold (보유를 바꾸지 않는다)
4. 청산되면 on_closed(position_id) — module-7 저널이 끼는 자리. 실패해도 결과는 그대로
시세가 없는 종목은 이번 회차에 손대지 않는다(0원으로 보지 않는다).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from dataclasses import replace as _replace
from datetime import datetime
from decimal import Decimal

from src.application.market_analysis.evidence import INDICATORS
from src.application.market_analysis.judgement import (
    active_principles,
    render_principles,
)
from src.application.market_analysis.ports import (
    AgentRunner,
    DecisionStore,
    MarketTools,
    PositionStore,
    PrincipleReader,
    RoleAgentStore,
    StructuredExtractor,
)
from src.application.market_analysis.quotes import fetch_quotes
from src.application.market_analysis.verdict_parser import parse_sell
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.account import (
    DecisionDraft,
    ExitPolicy,
    ExitReason,
    PerformancePolicy,
    Position,
    SellVerdict,
)
from src.domain.market_analysis.runtime import ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole

INDICATORS_MAX = 6_000
OnClosed = Callable[[int, str], Awaitable[None]]
_EXIT_TEXT = {ExitReason.TARGET: "목표가 도달", ExitReason.STOP: "손절가 도달"}


@dataclass(frozen=True)
class ManageResult:
    closed: tuple[int, ...] = ()
    adjusted: tuple[int, ...] = ()
    errors: tuple[int, ...] = ()
    judged: int = 0
    unpriced: tuple[str, ...] = ()
    tokens: int = 0
    cost_usd: Decimal = Decimal("0")


class PositionManager:
    def __init__(
        self,
        *,
        tools: MarketTools,
        runner: AgentRunner,
        roles: RoleAgentStore,
        positions: PositionStore,
        decisions: DecisionStore,
        extractor: StructuredExtractor | None,
        principles: PrincipleReader | None,
        logger: LoggerInterface,
        now_utc: Callable[[], datetime],
        on_closed: OnClosed | None = None,
    ) -> None:
        self._tools = tools
        self._runner = runner
        self._roles = roles
        self._positions = positions
        self._decisions = decisions
        self._extractor = extractor
        self._principles = principles
        self._logger = logger
        self._now_utc = now_utc
        self._on_closed = on_closed

    async def manage(
        self,
        setting: MarketAnalysisSetting,
        *,
        regime: str | None,
        provisional: bool,
        run_slots: asyncio.Semaphore,
        request_id: str,
    ) -> ManageResult:
        held = await self._positions.open_positions(request_id)
        if not held:
            return ManageResult()
        prices = await self._prices(setting, [p.symbol for p in held], request_id)
        agent_id = (await self._roles.get_all(request_id)).get(AgentRole.SELL_JUDGE)
        principles = await active_principles(
            self._principles,
            scope="sell",
            setting=setting,
            logger=self._logger,
            request_id=request_id,
        )
        ctx = _Ctx(
            setting,
            regime,
            provisional,
            agent_id,
            render_principles(principles),
            tuple(p.id for p in principles),
            run_slots,
        )

        unpriced = tuple(p.symbol for p in held if p.symbol not in prices)
        outcomes = await asyncio.gather(
            *(
                self._safe_one(p, prices[p.symbol], ctx, request_id)
                for p in held
                if p.symbol in prices
            )
        )
        closed = tuple(pid for kind, pid, _, _ in outcomes if kind == "closed")
        for pid in closed:
            await self._notify_closed(pid, request_id)
        return ManageResult(
            closed=closed,
            adjusted=tuple(pid for kind, pid, _, _ in outcomes if kind == "adjusted"),
            errors=tuple(pid for kind, pid, _, _ in outcomes if kind == "error"),
            judged=sum(1 for _, _, tokens, _ in outcomes if tokens is not None),
            unpriced=unpriced,
            tokens=sum(t or 0 for _, _, t, _ in outcomes),
            cost_usd=sum((c for _, _, _, c in outcomes), Decimal("0")),
        )

    async def _safe_one(
        self, position: Position, price: Decimal, ctx: _Ctx, request_id: str
    ) -> tuple[str, int, int | None, Decimal]:
        """중간 점검 M4: 한 포지션의 예외가 다른 포지션 결과·저널을 지우지 않게."""
        try:
            return await self._one(position, price, ctx, request_id)
        except Exception as e:  # noqa: BLE001
            self._logger.warning(
                "market_analysis position step failed",
                exception=e,
                request_id=request_id,
                position_id=position.id,
            )
            return "error", position.id, None, Decimal("0")

    async def _one(
        self, position: Position, price: Decimal, ctx: _Ctx, request_id: str
    ) -> tuple[str, int, int | None, Decimal]:
        """(결과 kind, position_id, 판단 토큰 또는 None, 비용)."""
        base = DecisionDraft(
            kind="sell",
            symbol=position.symbol,
            name=position.name,
            decision="hold",
            created_at=self._now_utc(),
            position_id=position.id,
            price_at_decision=price,
            regime=ctx.regime,
            provisional=ctx.provisional,
        )
        exit_reason = ExitPolicy.check(
            price=price, stop=position.stop_loss, target=position.target_price
        )
        if exit_reason is not None:
            # Plan SC-4: 목표가·손절가 도달 → 결정론 청산 + 거래 내역
            await self._close(position, price, exit_reason, request_id)
            await self._decisions.add(
                _replace(
                    base,
                    decision="sell",
                    rationale=f"{_EXIT_TEXT[exit_reason]} (결정론 청산)",
                    gate={"exit": exit_reason.value, "price": str(price)},
                ),
                request_id,
            )
            return "closed", position.id, None, Decimal("0")
        if not ctx.agent_id:
            await self._decisions.add(
                _replace(base, skip_reason="ROLE_UNMAPPED"), request_id
            )
            return "held", position.id, None, Decimal("0")

        indicators = await self._indicators(position.symbol, ctx.setting, request_id)
        async with ctx.run_slots:
            outcome = await self._runner.run(
                agent_id=ctx.agent_id,
                query=(
                    f"{position.name or position.symbol}({position.symbol}) 보유 종목 "
                    "매도 판단 — 지침의 JSON 코드블록 하나로만 답하라."
                ),
                reference_context=self._context(position, price, indicators, ctx),
                run_as_user_id=ctx.setting.run_as_user_id or "",
                request_id=request_id,
            )
        base = _replace(base, run_id=outcome.run_id, principles_used=ctx.principle_ids)
        if outcome.failed:
            await self._decisions.add(
                _replace(base, skip_reason=f"JUDGE_FAILED: {outcome.error}"), request_id
            )
            return "held", position.id, outcome.tokens, outcome.cost_usd
        verdict, _mode = await parse_sell(
            outcome.answer, self._extractor, request_id=request_id
        )
        kind = await self._apply(
            position, price, verdict, base, outcome.answer, request_id
        )
        return kind, position.id, outcome.tokens, outcome.cost_usd

    async def _apply(
        self,
        position: Position,
        price: Decimal,
        verdict: SellVerdict | None,
        base: DecisionDraft,
        answer: str,
        request_id: str,
    ) -> str:
        if verdict is None:
            await self._decisions.add(
                _replace(
                    base, skip_reason="PARSE_FAILED", rationale=answer[:4000] or None
                ),
                request_id,
            )
            return "held"
        draft = _replace(
            base,
            decision=verdict.action,
            confidence=verdict.confidence,
            rationale=verdict.reason[:4000] or None,
            target_price=verdict.new_target_price,
            stop_loss=verdict.new_stop_loss,
        )
        if verdict.action == "sell":
            await self._close(position, price, ExitReason.JUDGE, request_id)
            await self._decisions.add(draft, request_id)
            return "closed"
        if verdict.action == "adjust":
            if not ExitPolicy.valid_adjustment(verdict, price=price):
                await self._decisions.add(
                    _replace(
                        draft,
                        skip_reason=(
                            f"ADJUST_REJECTED(stop {verdict.new_stop_loss} < "
                            f"price {price} < target {verdict.new_target_price} 아님)"
                        ),
                    ),
                    request_id,
                )
                return "held"
            await self._positions.adjust_levels(
                position_id=position.id,
                target_price=verdict.new_target_price or position.target_price,
                stop_loss=verdict.new_stop_loss or position.stop_loss,
                request_id=request_id,
            )
            await self._decisions.add(draft, request_id)
            return "adjusted"
        await self._decisions.add(draft, request_id)
        return "held"

    async def _close(
        self, position: Position, price: Decimal, reason: ExitReason, request_id: str
    ) -> None:
        now = self._now_utc()
        await self._positions.close_position(
            position_id=position.id,
            exit_price=price,
            exit_at=now,
            reason=reason,
            profit_rate=PerformancePolicy.profit_rate(position.entry_price, price),
            holding_days=PerformancePolicy.holding_days(position.entry_at, now),
            request_id=request_id,
        )
        self._logger.info(
            "market_analysis position closed",
            request_id=request_id,
            position_id=position.id,
            reason=reason.value,
        )

    async def _notify_closed(self, position_id: int, request_id: str) -> None:
        if self._on_closed is None:
            return
        try:
            await self._on_closed(position_id, request_id)
        except Exception as e:  # noqa: BLE001 — 저널 실패가 청산을 되돌리지 않는다
            self._logger.warning(
                "market_analysis on_closed failed",
                exception=e,
                request_id=request_id,
                position_id=position_id,
            )

    async def _prices(
        self, setting: MarketAnalysisSetting, symbols: list[str], request_id: str
    ) -> dict[str, Decimal]:
        return await fetch_quotes(
            self._tools, setting, symbols, logger=self._logger, request_id=request_id
        )

    async def _indicators(
        self, symbol: str, setting: MarketAnalysisSetting, request_id: str
    ) -> str:
        outcome = await self._tools.call(
            source=ToolSource.KIS,
            server_id=setting.kis_server_id or "",
            tool="compute_indicators",
            args={"symbol": symbol, "indicators": INDICATORS},
            run_as_user_id=setting.run_as_user_id or "",
            request_id=request_id,
        )
        if outcome.is_error or outcome.payload is None:
            return "데이터 없음"
        return json.dumps(outcome.payload, ensure_ascii=False, separators=(",", ":"))[
            :INDICATORS_MAX
        ]

    def _context(
        self, position: Position, price: Decimal, indicators: str, ctx: _Ctx
    ) -> str:
        now = self._now_utc()
        return "\n\n".join(
            [
                (
                    "[포지션]\n"
                    f"{position.name or position.symbol}({position.symbol}) · "
                    f"진입가 {position.entry_price} · 목표가 {position.target_price} · "
                    f"손절가 {position.stop_loss} · "
                    f"보유 {PerformancePolicy.holding_days(position.entry_at, now)}일"
                ),
                (
                    f"[현재가]\n{price} (진입 대비 "
                    f"{PerformancePolicy.profit_rate(position.entry_price, price)}%)"
                    + (" · 장중 미확정" if ctx.provisional else "")
                ),
                f"[최근 지표 — 도구 결과 그대로]\n{indicators}",
                f"[매수 당시 근거]\n{position.buy_rationale or '데이터 없음'}",
                f"[시장 체제]\n{ctx.regime or '데이터 없음'}",
                ctx.principles_text,
            ]
        )


@dataclass(frozen=True)
class _Ctx:
    setting: MarketAnalysisSetting
    regime: str | None
    provisional: bool
    agent_id: str | None
    principles_text: str
    principle_ids: tuple[int, ...]
    run_slots: asyncio.Semaphore
