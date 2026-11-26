"""청산 저널 · 원칙 후보 — 회차 ⑦ (PositionManager.on_closed 자리).

Design Ref: stock-analysis-agents §2.2 ⑦, §7 journal, DD8 · DD9, Plan FR-12 · SC-4.
1. 포지션당 저널 1개 — 이미 있으면 에이전트를 부르지 않는다 (UNIQUE 로 한 번 더 막는다)
2. 재료: 청산 포지션 · 그 포지션의 매수·매도 판단
이력 · 보유 기간 일봉(get_price_history)
3. 저널 에이전트 → JSON 파싱(보조 LLM 1회) → 실패하면 원문만 저장 (DD8)
4. 원칙 후보 최대 5개 — 설정 principle_auto_activate
가 false(기본)면 비활성으로 (U12 · DD9).
   같은 원칙은 새로 만들지 않고 근거 거래 수를 올린다(저장소)
실패는 회차를 멈추지 않는다 — 호출자(PositionManager)가 예외를 가두지만, 여기서도
실행 실패·파싱 실패는 값으로 처리한다.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from src.application.market_analysis.ports import (
    AgentRunner,
    JournalStore,
    MarketTools,
    PrincipleStore,
    RoleAgentStore,
    SettingReader,
    StructuredExtractor,
)
from src.application.market_analysis.verdict_parser import parse_model
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.principle import (
    MAX_CANDIDATES_PER_JOURNAL,
    ClosedPosition,
    DecisionSummary,
    JournalDraft,
    PrincipleCandidate,
)
from src.domain.market_analysis.runtime import ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole

PRICE_PATH_MAX = 8_000
RAW_ANSWER_MAX = 60_000
_EXIT_TEXT = {"target": "목표가 도달", "stop": "손절가 도달", "judge": "매도 판단"}


class PrincipleCandidateModel(BaseModel):
    condition: str = Field(min_length=1, max_length=500)
    action: str = Field(min_length=1, max_length=500)
    reason: str | None = Field(default=None, max_length=2000)
    scope: Literal["buy", "sell", "all"] = "all"
    priority: Literal["high", "medium", "low"] = "medium"
    confidence: int = Field(default=1, ge=1, le=10)

    @field_validator("scope", "priority", mode="before")
    @classmethod
    def _lower(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v


class JournalOutModel(BaseModel):
    one_line: str | None = Field(default=None, max_length=300)
    situation: str | None = Field(default=None, max_length=8000)
    evaluation: str | None = Field(default=None, max_length=8000)
    lessons: list[str] = Field(default_factory=list, max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=20)
    principle_candidates: list[PrincipleCandidateModel] = Field(default_factory=list)


class JournalWriter:
    def __init__(
        self,
        *,
        tools: MarketTools,
        runner: AgentRunner,
        roles: RoleAgentStore,
        journals: JournalStore,
        principles: PrincipleStore,
        settings: SettingReader,
        extractor: StructuredExtractor | None,
        logger: LoggerInterface,
        now_utc: Callable[[], datetime],
    ) -> None:
        self._tools = tools
        self._runner = runner
        self._roles = roles
        self._journals = journals
        self._principles = principles
        self._settings = settings
        self._extractor = extractor
        self._logger = logger
        self._now_utc = now_utc

    async def __call__(self, position_id: int, request_id: str) -> int | None:
        """저널 ID (만들지 않았으면 None)."""
        if await self._journals.has_journal(position_id, request_id):
            return None
        position = await self._journals.closed_position(position_id, request_id)
        if position is None:
            self._logger.warning(
                "market_analysis journal skipped — position not closed",
                request_id=request_id,
                position_id=position_id,
            )
            return None
        agent_id = (await self._roles.get_all(request_id)).get(AgentRole.JOURNAL)
        if not agent_id:
            self._logger.warning(
                "market_analysis journal skipped — role unmapped",
                request_id=request_id,
                position_id=position_id,
            )
            return None
        setting = await self._settings.get(request_id)
        decisions = await self._journals.decisions_for(position_id, request_id)
        path = await self._price_path(position, setting, request_id)
        outcome = await self._runner.run(
            agent_id=agent_id,
            query=(
                f"{position.name or position.symbol}({position.symbol}) "
                "청산 거래 복기 — "
                "지침의 JSON 코드블록 하나로만 답하라."
            ),
            reference_context=_context(position, decisions, path),
            run_as_user_id=setting.run_as_user_id or "",
            request_id=request_id,
        )
        if outcome.failed:
            self._logger.warning(
                "market_analysis journal agent failed",
                request_id=request_id,
                position_id=position_id,
                error=outcome.error,
            )
            return None
        parsed, _mode = await parse_model(
            outcome.answer, JournalOutModel, self._extractor, request_id
        )
        journal_id = await self._journals.save_journal(
            self._draft(position_id, parsed, outcome.answer, outcome.run_id), request_id
        )
        if journal_id is None or parsed is None:
            return journal_id
        candidates = [
            PrincipleCandidate(
                condition=c.condition.strip(),
                action=c.action.strip(),
                reason=c.reason,
                scope=c.scope,
                priority=c.priority,
                confidence=c.confidence,
            )
            for c in parsed.principle_candidates[:MAX_CANDIDATES_PER_JOURNAL]
        ]
        if candidates:
            # DD9: 기본은 비활성 — 운영자가 켠다
            await self._principles.add_candidates(
                journal_id=journal_id,
                candidates=candidates,
                auto_activate=setting.principle_auto_activate,
                request_id=request_id,
            )
        return journal_id

    def _draft(
        self,
        position_id: int,
        parsed: JournalOutModel | None,
        answer: str,
        run_id: str | None,
    ) -> JournalDraft:
        if parsed is None:
            # DD8: 구조화 실패 → 원문만 저장
            return JournalDraft(
                position_id=position_id,
                one_line=None,
                situation=None,
                evaluation=None,
                lessons=(),
                tags=(),
                raw_answer=answer[:RAW_ANSWER_MAX] or None,
                run_id=run_id,
                created_at=self._now_utc(),
            )
        return JournalDraft(
            position_id=position_id,
            one_line=parsed.one_line,
            situation=parsed.situation,
            evaluation=parsed.evaluation,
            lessons=tuple(str(x)[:500] for x in parsed.lessons),
            tags=tuple(str(x)[:50] for x in parsed.tags),
            raw_answer=None,
            run_id=run_id,
            created_at=self._now_utc(),
        )

    async def _price_path(
        self, position: ClosedPosition, setting: MarketAnalysisSetting, request_id: str
    ) -> str:
        outcome = await self._tools.call(
            source=ToolSource.KIS,
            server_id=setting.kis_server_id or "",
            tool="get_price_history",
            args={
                "symbol": position.symbol,
                "interval": "D",
                "start": position.entry_at.date().isoformat(),
                "end": position.exit_at.date().isoformat(),
                "limit": max(2, position.holding_days + 2),
            },
            run_as_user_id=setting.run_as_user_id or "",
            request_id=request_id,
        )
        if outcome.is_error or outcome.payload is None:
            return "데이터 없음"
        return json.dumps(outcome.payload, ensure_ascii=False, separators=(",", ":"))[
            :PRICE_PATH_MAX
        ]


def _context(
    position: ClosedPosition, decisions: list[DecisionSummary], path: str
) -> str:
    result = (
        "[거래 결과]\n"
        f"{position.name or position.symbol}({position.symbol}) · 섹터 "
        f"{position.sector or '데이터 없음'}\n"
        f"진입 {position.entry_price} ({position.entry_at.date()}) → 청산 "
        f"{position.exit_price} ({position.exit_at.date()}) · "
        f"{_EXIT_TEXT.get(position.exit_reason, position.exit_reason)}\n"
        f"실현 수익률 {position.profit_rate}% · 보유 {position.holding_days}일 · "
        f"마지막 목표가 {position.target_price} · 마지막 손절가 {position.stop_loss}"
    )
    lines = ["[판단 이력 — 오래된 순]"]
    for d in decisions:
        head = f"- {d.created_at:%Y-%m-%d %H:%M} {d.kind}:{d.decision}"
        facts = [
            f"점수 {d.score}" if d.score is not None else "",
            f"확신도 {d.confidence}" if d.confidence is not None else "",
            f"판단가 {d.price_at_decision}" if d.price_at_decision is not None else "",
            f"목표 {d.target_price}" if d.target_price is not None else "",
            f"손절 {d.stop_loss}" if d.stop_loss is not None else "",
        ]
        body = " · ".join(f for f in facts if f)
        reason = (d.rationale or d.skip_reason or "").strip()[:1500]
        lines.append(f"{head} {body}\n  근거: {reason or '데이터 없음'}")
    if len(lines) == 1:
        lines.append("데이터 없음")
    return "\n\n".join(
        [result, "\n".join(lines), f"[보유 기간 일봉 — 도구 결과 그대로]\n{path}"]
    )
