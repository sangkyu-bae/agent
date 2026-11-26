"""매수 판단 — 리포트 뒤 (회차 ⑥의 after_report 자리).

Design Ref: stock-analysis-agents §2.2 ⑥, §6 EntryGatePolicy, §7 buy_judge, §10.
에이전트는 점수와 가격 근거만 낸다. 진입 여부는 판단 시점 `get_quote` 현재가로
결정론 게이트가 다시 계산한다(Plan SC-1 의 마지막 단계, §1.1-2).
- 전략·요약이 없는 리포트 → skip(REPORT_INCOMPLETE), 에이전트를 부르지 않는다
- 파싱 실패(보조 LLM 도 실패) → skip(PARSE_FAILED) (U9)
- 게이트 미통과·보류 → 관심종목(ma_decision skip, 사유 = 판단 사유 + 게이트 사유)
- 슬롯 경쟁: 시세 조회 → 게이트 → 진입 기록은
잠금 안에서 한다 (동시 2종목이 마지막 슬롯을
  같이 쓰지 않게). 에이전트 실행은 잠금 밖이다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace as _replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from src.application.market_analysis.ports import (
    AgentRunner,
    DecisionStore,
    MarketTools,
    PositionStore,
    PrincipleReader,
    RoleAgentStore,
    StructuredExtractor,
)
from src.application.market_analysis.quotes import quote_price
from src.application.market_analysis.verdict_parser import parse_buy
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.account import (
    ActivePrinciple,
    BuyVerdict,
    DecisionDraft,
    EntryGatePolicy,
    Position,
)
from src.domain.market_analysis.report import AnalysisTarget
from src.domain.market_analysis.runtime import ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole, Regime

STRATEGY_MAX = 12_000
SUMMARY_MAX = 4_000
RATIONALE_MAX = 4_000
JudgeCost = tuple[int, Decimal]
_NO_COST: JudgeCost = (0, Decimal("0"))


async def active_principles(
    reader: PrincipleReader | None,
    *,
    scope: str,
    setting: MarketAnalysisSetting,
    logger: LoggerInterface,
    request_id: str,
) -> list[ActivePrinciple]:
    """활성 원칙 (module-7). 읽기 실패는 원칙 없이 판단한다."""
    if reader is None or setting.max_principles <= 0:
        return []
    try:
        return await reader.active(
            scope=scope, limit=setting.max_principles, request_id=request_id
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "market_analysis principles unavailable", exception=e, request_id=request_id
        )
        return []


def render_principles(principles: list[ActivePrinciple]) -> str:
    if not principles:
        return "[활성 매매 원칙]\n없음"
    return "[활성 매매 원칙]\n" + "\n".join(f"- {p.text}" for p in principles)


def render_account(positions: list[Position], setting: MarketAnalysisSetting) -> str:
    used = sum((p.slot_weight for p in positions), Decimal("0"))
    lines = [
        f"[계좌 상태]\n보유 {len(positions)}종목 · "
        f"사용 슬롯 {used}/{setting.slot_count}"
    ]
    lines += [
        f"- {p.name or p.symbol}({p.symbol}) 진입가 {p.entry_price} · "
        f"목표가 {p.target_price} · 손절가 {p.stop_loss}"
        for p in positions
    ]
    return "\n".join(lines)


def render_rules(setting: MarketAnalysisSetting, regime: Regime) -> str:
    minimum = setting.min_score_by_regime.get(regime.value, 10)
    return (
        "[진입 규칙 — 서버가 다시 계산한다]\n"
        f"현재 체제 최소 점수 {minimum} · 손익비 ≥ {setting.min_rr} · "
        f"손절폭 {setting.min_stop_pct}~{setting.max_stop_pct}% · "
        "손절가 < 현재가 < 목표가"
    )


class BuyJudgement:
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
        self._entry_lock = asyncio.Lock()

    async def __call__(
        self,
        target: AnalysisTarget,
        result: Any,
        setting: MarketAnalysisSetting,
        request_id: str,
    ) -> JudgeCost:
        regime = Regime(target.regime) if target.regime else Regime.NEUTRAL
        base = DecisionDraft(
            kind="buy",
            symbol=target.symbol,
            name=target.name,
            decision="skip",
            created_at=self._now_utc(),
            report_id=result.report_id,
            regime=regime.value,
            provisional=target.provisional,
        )
        if not result.strategy or not result.summary:
            await self._record(
                base, skip_reason="REPORT_INCOMPLETE", request_id=request_id
            )
            return _NO_COST
        agent_id = (await self._roles.get_all(request_id)).get(AgentRole.BUY_JUDGE)
        if not agent_id:
            await self._record(base, skip_reason="ROLE_UNMAPPED", request_id=request_id)
            return _NO_COST

        principles = await active_principles(
            self._principles,
            scope="buy",
            setting=setting,
            logger=self._logger,
            request_id=request_id,
        )
        held = await self._positions.open_positions(request_id)
        outcome = await self._runner.run(
            agent_id=agent_id,
            query=(
                f"{target.name}({target.symbol}) 매수 판단 — "
                "지침의 JSON 코드블록 하나로만 답하라."
            ),
            reference_context=self._context(
                target, result, setting, regime, held, principles
            ),
            run_as_user_id=setting.run_as_user_id or "",
            request_id=request_id,
        )
        cost: JudgeCost = (outcome.tokens, outcome.cost_usd)
        base = _replace(
            base,
            run_id=outcome.run_id,
            principles_used=tuple(p.id for p in principles),
        )
        if outcome.failed:
            await self._record(
                base,
                skip_reason=f"JUDGE_FAILED: {outcome.error}",
                request_id=request_id,
            )
            return cost
        verdict, _mode = await parse_buy(
            outcome.answer, self._extractor, request_id=request_id
        )
        if verdict is None:
            await self._record(
                _replace(base, rationale=outcome.answer[:RATIONALE_MAX] or None),
                skip_reason="PARSE_FAILED",
                request_id=request_id,
            )
            return cost
        await self._gate_and_enter(target, verdict, base, setting, regime, request_id)
        return cost

    async def _gate_and_enter(
        self,
        target: AnalysisTarget,
        verdict: BuyVerdict,
        base: DecisionDraft,
        setting: MarketAnalysisSetting,
        regime: Regime,
        request_id: str,
    ) -> None:
        draft = _replace(
            base,
            score=verdict.score,
            target_price=verdict.target_price,
            stop_loss=verdict.stop_loss,
            investment_period=verdict.investment_period,
            sector=verdict.sector,
            rationale=verdict.rationale[:RATIONALE_MAX] or None,
        )
        async with self._entry_lock:
            quote = await self._tools.call(
                source=ToolSource.KIS,
                server_id=setting.kis_server_id or "",
                tool="get_quote",
                args={"symbol": target.symbol},
                run_as_user_id=setting.run_as_user_id or "",
                request_id=request_id,
            )
            price = None if quote.is_error else quote_price(quote.payload)
            if price is None:
                await self._record(
                    draft,
                    skip_reason=_join(verdict.skip_reason, "QUOTE_UNAVAILABLE"),
                    request_id=request_id,
                )
                return
            held = await self._positions.open_positions(request_id)
            gate = EntryGatePolicy.check(
                verdict,
                price=price,
                regime=regime,
                setting=setting,
                open_positions=len(held),
                already_held=any(p.symbol == target.symbol for p in held),
                provisional=target.provisional,
            )
            draft = _replace(draft, gate=gate.to_dict(), price_at_decision=price)
            if not gate.passed:
                await self._record(
                    draft,
                    skip_reason=_join(
                        verdict.skip_reason, "GATE: " + ", ".join(gate.reasons)
                    ),
                    request_id=request_id,
                )
                return
            decision_id = await self._decisions.add(
                _replace(draft, decision="enter"), request_id
            )
            # Plan SC-4 재료: 진입가 = 판단 시점 현재가, 목표·손절 = 게이트를 통과한 값
            try:
                position_id = await self._positions.open_position(
                    symbol=target.symbol,
                    name=target.name,
                    sector=verdict.sector,
                    entry_price=price,
                    entry_at=self._now_utc(),
                    target_price=verdict.target_price or price,
                    stop_loss=verdict.stop_loss or price,
                    buy_decision_id=decision_id,
                    request_id=request_id,
                )
            except Exception as e:
                # 중간 점검 M3: 포지션 없는 enter 판단을 남기지 않는다
                await self._decisions.mark_entry_failed(
                    decision_id=decision_id,
                    reason=f"ENTRY_FAILED: {str(e)[:300]}",
                    request_id=request_id,
                )
                raise
            await self._decisions.link_position(
                decision_id=decision_id, position_id=position_id, request_id=request_id
            )
        self._logger.info(
            "market_analysis position opened",
            request_id=request_id,
            symbol=target.symbol,
            position_id=position_id,
        )

    def _context(
        self,
        target: AnalysisTarget,
        result: Any,
        setting: MarketAnalysisSetting,
        regime: Regime,
        held: list[Position],
        principles: list[ActivePrinciple],
    ) -> str:
        header = result.header.render() if result.header is not None else ""
        parts = [
            f"[리포트 요약]\n{result.summary[:SUMMARY_MAX]}",
            f"[투자 시나리오]\n{result.strategy[:STRATEGY_MAX]}",
            header,
            target.market_context,
            render_account(held, setting),
            render_rules(setting, regime),
            render_principles(principles),
        ]
        return "\n\n".join(p for p in parts if p)

    async def _record(
        self, draft: DecisionDraft, *, skip_reason: str, request_id: str
    ) -> None:
        await self._decisions.add(
            _replace(draft, decision="skip", skip_reason=skip_reason[:1000]), request_id
        )


def _join(first: str | None, second: str) -> str:
    return f"{first} · {second}" if first else second
