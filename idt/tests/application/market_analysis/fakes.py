"""시장 분석 유스케이스 테스트용 가짜 포트 — 네트워크·LLM·DB 없이."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any

from src.domain.market_analysis.report import ReportStatus, SectionResult
from src.domain.market_analysis.runtime import AgentRunOutcome, ToolOutcome, ToolSource
from src.domain.market_analysis.value_objects import AgentRole

QUOTE = {
    "market": "KRX",
    "symbol": "005930",
    "price": "70000",
    "change": "-500",
    "change_rate": "-0.71",
    "volume": 12345678,
    "currency": "KRW",
    "as_of": "2026-11-26T02:00:00",
}


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[ToolSource, str, dict]] = []
        self.news_calls: list[dict] = []
        self.fail: set[str] = set()
        self.payloads: dict[str, Any] = {"get_quote": QUOTE}
        self.cost: dict[str, Decimal] = {"research": Decimal("0.004")}
        self.fail_code = "KIS_TIMEOUT"  # fail 에 든 도구가 돌려줄 오류 코드

    async def call(self, *, source, server_id, tool, args, run_as_user_id, request_id):
        self.calls.append((source, tool, args))
        if tool in self.fail:
            return ToolOutcome(
                source=source,
                tool=tool,
                args=args,
                is_error=True,
                error_code=self.fail_code,
                text=f"{self.fail_code}: 실패",
            )
        payload = self.payloads.get(tool, {"tool": tool, "value": 1})
        if callable(payload):  # 인자에 따라 다른 응답 (scan_signals 묶음 등)
            payload = payload(args)
        return ToolOutcome(
            source=source,
            tool=tool,
            args=args,
            payload=payload,
            text=json.dumps(payload, ensure_ascii=False),
            cost_usd=self.cost.get(tool, Decimal("0")),
        )

    async def news(self, *, query, days, max_results, request_id):
        self.news_calls.append(
            {"query": query, "days": days, "max_results": max_results}
        )
        payload = [{"title": "뉴스", "url": "https://n/1"}]
        return ToolOutcome(
            source=ToolSource.TAVILY,
            tool="search",
            args={"query": query},
            payload=payload,
            text=json.dumps(payload, ensure_ascii=False),
        )


class FakeRunner:
    def __init__(
        self,
        *,
        fail_agents: set[str] | None = None,
        empty_agents: set[str] | None = None,
        answers: dict[str, object] | None = None,
    ):
        self.runs: list[dict] = []
        self.fail_agents = fail_agents or set()
        self.empty_agents = empty_agents or set()
        # agent_id → 답변 문자열 또는 (query → 답변) 함수
        self.answers = answers or {}
        self.active = 0
        self.max_active = 0

    async def run(
        self, *, agent_id, query, reference_context, run_as_user_id, request_id
    ):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        self.runs.append(
            {
                "agent_id": agent_id,
                "query": query,
                "reference_context": reference_context,
                "user": run_as_user_id,
            }
        )
        if agent_id in self.fail_agents:
            return AgentRunOutcome(
                answer="", run_id=None, failed=True, error="RUN_FAILED: x"
            )
        answer = "" if agent_id in self.empty_agents else f"{agent_id} 본문"
        if agent_id in self.answers:
            given = self.answers[agent_id]
            answer = given(query) if callable(given) else str(given)
        return AgentRunOutcome(
            answer=answer,
            run_id=f"run-{agent_id}",
            tokens=100,
            cost_usd=Decimal("0.01"),
        )


class FakeReports:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.evidence: list[tuple[int, list[ToolOutcome]]] = []
        self.sections: list[tuple[int, SectionResult]] = []
        self.finished: list[dict] = []

    async def create_report(self, *, target, header, request_id) -> int:
        self.created.append({"target": target, "header": header})
        return len(self.created)

    async def add_evidence(self, *, report_id, outcomes, request_id) -> None:
        self.evidence.append((report_id, list(outcomes)))

    async def save_section(self, *, report_id, section, request_id) -> None:
        self.sections.append((report_id, section))

    async def finish_report(
        self,
        *,
        report_id,
        status: ReportStatus,
        strategy,
        summary,
        tokens,
        cost_usd,
        request_id,
    ) -> None:
        self.finished.append(
            {
                "report_id": report_id,
                "status": status,
                "strategy": strategy,
                "summary": summary,
                "tokens": tokens,
                "cost_usd": cost_usd,
            }
        )


class FakeRoles:
    def __init__(self, mapping: dict[AgentRole, str] | None = None) -> None:
        self.mapping = (
            dict(mapping)
            if mapping is not None
            else {role: role.value for role in AgentRole}
        )
        self.sets: list[tuple[AgentRole, str]] = []

    async def get_all(self, request_id: str) -> dict[AgentRole, str]:
        return dict(self.mapping)

    async def set(self, *, role, agent_id, updated_by, request_id) -> None:
        self.mapping[role] = agent_id
        self.sets.append((role, agent_id))


class FakeRounds:
    """application.ports.RoundStore — UNIQUE 선점을 dict 로 흉내 낸다."""

    def __init__(self) -> None:
        self.rounds: dict[int, dict] = {}
        self.keys: set[tuple] = set()
        self.items: dict[int, dict] = {}
        self.analyzed: set[str] = set()
        self.abandoned = 0

    async def try_claim(self, *, trade_date, slot, kind, trigger, request_id):
        key = (trade_date, slot, trigger)
        if key in self.keys:
            return None
        self.keys.add(key)
        rid = len(self.rounds) + 1
        self.rounds[rid] = {
            "trade_date": trade_date,
            "slot": slot,
            "kind": kind,
            "trigger": trigger,
            "status": "running",
        }
        return rid

    async def any_running(self, *, exclude_id, request_id):
        return any(
            r["status"] == "running" for i, r in self.rounds.items() if i != exclude_id
        )

    async def skip(self, *, round_id, reason, request_id):
        self.rounds[round_id].update(status="skipped", skip_reason=reason)

    async def add_items(self, *, round_id, items, request_id):
        ids = {}
        for item in items:
            iid = len(self.items) + 1
            self.items[iid] = {
                "round_id": round_id,
                "symbol": item.symbol,
                "status": item.status,
                "signals": item.signals,
            }
            ids[item.symbol] = iid
        return ids

    async def update_item(
        self,
        *,
        item_id,
        status,
        report_id=None,
        tokens=0,
        cost_usd=Decimal("0"),
        error=None,
        request_id,
    ):
        self.items[item_id].update(
            status=str(status),
            report_id=report_id,
            tokens=tokens,
            cost_usd=cost_usd,
            error=error,
        )

    async def finish_round(self, *, round_id, status, counts, error, request_id):
        self.rounds[round_id].update(status=str(status), counts=counts, error=error)

    async def analyzed_symbols(self, *, trade_date, request_id):
        return set(self.analyzed)

    async def abandon_running(self, request_id):
        n = 0
        for r in self.rounds.values():
            if r["status"] == "running":
                r["status"] = "abandoned"
                n += 1
        self.abandoned += n
        return n


class FakeHeld:
    def __init__(self, symbols: set[str] | None = None) -> None:
        self.symbols = symbols or set()

    async def held_symbols(self, request_id):
        return set(self.symbols)


class FakePositions:
    """application.ports.PositionStore — 진입·청산을 dict 로 기록."""

    def __init__(self) -> None:
        self.rows: dict[int, dict] = {}

    def seed(self, **kw) -> int:
        from datetime import datetime

        pid = len(self.rows) + 1
        row = {
            "id": pid,
            "symbol": "005930",
            "name": "삼성전자",
            "sector": None,
            "slot_weight": Decimal("1"),
            "entry_price": Decimal("10000"),
            "entry_at": datetime(2026, 11, 20, 1, 0),
            "target_price": Decimal("12000"),
            "stop_loss": Decimal("9500"),
            "buy_decision_id": None,
            "buy_rationale": "매수 근거",
            "status": "open",
        }
        row.update(kw)
        self.rows[pid] = row
        return pid

    def _position(self, row):
        from src.domain.market_analysis.account import Position

        return Position(
            **{
                k: row[k]
                for k in (
                    "id",
                    "symbol",
                    "name",
                    "sector",
                    "slot_weight",
                    "entry_price",
                    "entry_at",
                    "target_price",
                    "stop_loss",
                    "buy_decision_id",
                    "buy_rationale",
                )
            }
        )

    async def open_positions(self, request_id):
        return [self._position(r) for r in self.rows.values() if r["status"] == "open"]

    async def open_position(
        self,
        *,
        symbol,
        name,
        sector,
        entry_price,
        entry_at,
        target_price,
        stop_loss,
        buy_decision_id,
        request_id,
    ):
        return self.seed(
            symbol=symbol,
            name=name,
            sector=sector,
            entry_price=entry_price,
            entry_at=entry_at,
            target_price=target_price,
            stop_loss=stop_loss,
            buy_decision_id=buy_decision_id,
            buy_rationale=None,
        )

    async def close_position(
        self,
        *,
        position_id,
        exit_price,
        exit_at,
        reason,
        profit_rate,
        holding_days,
        request_id,
    ):
        self.rows[position_id].update(
            status="closed",
            exit_price=exit_price,
            exit_at=exit_at,
            exit_reason=reason,
            profit_rate=profit_rate,
            holding_days=holding_days,
        )

    async def adjust_levels(self, *, position_id, target_price, stop_loss, request_id):
        self.rows[position_id].update(target_price=target_price, stop_loss=stop_loss)

    async def closed_trades(self, request_id):
        from src.domain.market_analysis.account import ClosedTrade

        return [
            ClosedTrade(r["profit_rate"], r["slot_weight"], r["holding_days"])
            for r in self.rows.values()
            if r["status"] == "closed"
        ]

    async def held_symbols(self, request_id):
        return {r["symbol"] for r in self.rows.values() if r["status"] == "open"}


class FakeDecisions:
    def __init__(self) -> None:
        self.rows: list = []
        self.links: dict[int, int] = {}
        self.reverted: dict[int, str] = {}

    async def add(self, draft, request_id) -> int:
        self.rows.append(draft)
        return len(self.rows)

    async def link_position(self, *, decision_id, position_id, request_id) -> None:
        self.links[decision_id] = position_id

    async def mark_entry_failed(self, *, decision_id, reason, request_id) -> None:
        self.reverted[decision_id] = reason


class FakeRegimes:
    def __init__(self, first=None) -> None:
        self.regimes: dict = {}
        self.snapshots: dict = {}
        self.first = first

    async def save_regime(self, *, trade_date, result, kosdaq_close, bars, request_id):
        self.regimes[trade_date] = (result, kosdaq_close, bars)
        if self.first is None:
            self.first = (result.close, kosdaq_close)

    async def first_closes(self, request_id):
        return self.first

    async def save_snapshot(self, *, trade_date, request_id, **values):
        self.snapshots[trade_date] = values


class FakePrinciples:
    def __init__(self, items=None) -> None:
        self.items = items or []
        self.calls: list[str] = []

    async def active(self, *, scope, limit, request_id):
        self.calls.append(scope)
        return list(self.items)[:limit]


class FakeExtractor:
    def __init__(self, result=None) -> None:
        self.result = result
        self.calls = 0

    async def extract(self, *, text, schema, request_id):
        self.calls += 1
        return self.result


class FakeJournals:
    """application.ports.JournalStore."""

    def __init__(self, position=None, decisions=None) -> None:
        self.position = position
        self.decisions = decisions or []
        self.saved: list = []
        self.existing: set[int] = set()

    async def closed_position(self, position_id, request_id):
        return self.position

    async def decisions_for(self, position_id, request_id):
        return list(self.decisions)

    async def has_journal(self, position_id, request_id):
        return position_id in self.existing

    async def save_journal(self, draft, request_id):
        if draft.position_id in self.existing:
            return None
        self.existing.add(draft.position_id)
        self.saved.append(draft)
        return len(self.saved)


class FakePrincipleStore:
    def __init__(self) -> None:
        self.added: list[dict] = []
        self.toggles: list[dict] = []
        self.known: set[int] = {1}

    async def add_candidates(
        self, *, journal_id, candidates, auto_activate, request_id
    ):
        self.added.append(
            {
                "journal_id": journal_id,
                "candidates": list(candidates),
                "auto_activate": auto_activate,
            }
        )
        return list(range(1, len(candidates) + 1))

    async def set_active(
        self, *, principle_id, is_active, priority, updated_by, request_id
    ):
        if principle_id not in self.known:
            return False
        self.toggles.append(
            {
                "id": principle_id,
                "is_active": is_active,
                "priority": priority,
                "by": updated_by,
            }
        )
        return True


class FakeSettings:
    def __init__(self, setting) -> None:
        self.setting = setting

    async def get(self, request_id):
        return self.setting
