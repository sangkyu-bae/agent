"""리포트 도메인 — 섹션별 근거 표 · 머리 사실 · 상태 규칙.

Design Ref: stock-analysis-agents
§2.3(파이프라인), §1.1-5(머리 사실은 도구 결과에서 결정론 렌더),
§10(실패 모델). 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from src.domain.market_analysis.value_objects import AgentRole


class ReportStatus(StrEnum):
    RUNNING = "running"
    DONE = "done"
    PARTIAL = "partial"
    FAILED = "failed"


class SectionStatus(StrEnum):
    DONE = "done"
    FAILED = "failed"
    EMPTY = "empty"


class EvidenceKey(StrEnum):
    """prefetch 근거 1건의 이름 — 섹션별로 어떤 근거를 넘길지 고르는 단위."""

    QUOTE = "quote"
    DAILY = "daily"
    INDICATORS = "indicators"
    INVESTOR = "investor"
    DART_CORP = "dart_corp"
    DART_FINANCIALS = "dart_financials"
    DART_DISCLOSURES = "dart_disclosures"
    NEWS = "news"
    RESEARCH = "research"


SECTION_EVIDENCE: dict[AgentRole, tuple[EvidenceKey, ...]] = {
    AgentRole.SECTION_TECHNICAL: (
        EvidenceKey.QUOTE,
        EvidenceKey.DAILY,
        EvidenceKey.INDICATORS,
    ),
    AgentRole.SECTION_FLOW: (EvidenceKey.QUOTE, EvidenceKey.INVESTOR),
    AgentRole.SECTION_FINANCIAL: (
        EvidenceKey.DART_FINANCIALS,
        EvidenceKey.DART_DISCLOSURES,
    ),
    AgentRole.SECTION_COMPANY: (EvidenceKey.DART_CORP, EvidenceKey.RESEARCH),
    AgentRole.SECTION_NEWS: (
        EvidenceKey.NEWS,
        EvidenceKey.RESEARCH,
        EvidenceKey.DART_DISCLOSURES,
    ),
    # 시장 섹션은 회차가 넘기는 시장 맥락(지수·체제)을 함께 받는다
    AgentRole.SECTION_MARKET: (EvidenceKey.QUOTE,),
}

SECTION_TITLES: dict[AgentRole, str] = {
    AgentRole.SECTION_TECHNICAL: "기술적 분석",
    AgentRole.SECTION_FLOW: "수급",
    AgentRole.SECTION_FINANCIAL: "재무",
    AgentRole.SECTION_COMPANY: "기업·산업",
    AgentRole.SECTION_NEWS: "뉴스·촉매",
    AgentRole.SECTION_MARKET: "시장·섹터",
    AgentRole.STRATEGY: "투자 시나리오",
    AgentRole.SUMMARY: "핵심 요약",
}


@dataclass(frozen=True)
class AnalysisTarget:
    """분석 대상 종목 1개 — 회차(module-5)가 만든다."""

    symbol: str
    name: str
    trade_date: date
    signals: tuple[dict[str, Any], ...]
    provisional: bool
    market_context: str = ""
    round_id: int | None = None
    regime: str | None = None


@dataclass(frozen=True)
class HeaderFacts:
    """리포트 머리 사실 — 도구 결과에서 그대로 옮긴다(LLM 이 쓰지 않는다)."""

    symbol: str
    name: str
    trade_date: date
    price: str
    change: str
    change_rate: str
    volume: int | None
    as_of: str
    signals: tuple[dict[str, Any], ...]
    provisional: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "trade_date": self.trade_date.isoformat(),
            "price": self.price,
            "change": self.change,
            "change_rate": self.change_rate,
            "volume": self.volume,
            "as_of": self.as_of,
            "signals": list(self.signals),
            "provisional": self.provisional,
        }

    def render(self) -> str:
        rules = ", ".join(str(s.get("rule", "")) for s in self.signals) or "없음"
        state = "장중 미확정 봉" if self.provisional else "확정 봉"
        return (
            f"[머리 사실 — 도구 결과 그대로]\n"
            f"종목: {self.name}({self.symbol}) · "
            f"기준일 {self.trade_date.isoformat()} ({state})\n"
            f"현재가 {self.price} · 전일 대비 {self.change} ({self.change_rate}%) · "
            f"거래량 {self.volume if self.volume is not None else '데이터 없음'} · "
            f"조회 {self.as_of}\n"
            f"발생 신호: {rules}"
        )


def header_facts_from_quote(
    *,
    symbol: str,
    name: str,
    quote: Any,
    signals: tuple[dict[str, Any], ...],
    provisional: bool,
    trade_date: date,
) -> HeaderFacts | None:
    """KIS `get_quote` 결과 → 머리 사실.
    현재가가 없으면 None (리포트를 만들 수 없다)."""
    if not isinstance(quote, dict) or not str(quote.get("price") or "").strip():
        return None
    volume = quote.get("volume")
    return HeaderFacts(
        symbol=symbol,
        name=name,
        trade_date=trade_date,
        price=str(quote["price"]),
        change=str(quote.get("change") or ""),
        change_rate=str(quote.get("change_rate") or ""),
        volume=int(volume) if isinstance(volume, int | float) else None,
        as_of=str(quote.get("as_of") or ""),
        signals=signals,
        provisional=provisional,
    )


@dataclass(frozen=True)
class SectionResult:
    role: AgentRole
    status: SectionStatus
    content: str
    run_id: str | None
    tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    error: str | None = None


class ReportStatusPolicy:
    @staticmethod
    def decide(
        *,
        quote_ok: bool,
        sections: dict[AgentRole, SectionStatus],
        strategy_ok: bool,
        summary_ok: bool,
    ) -> ReportStatus:
        if not quote_ok:
            return ReportStatus.FAILED
        all_sections = all(
            sections.get(role) is SectionStatus.DONE
            for role in AgentRole.section_roles()
        )
        if all_sections and strategy_ok and summary_ok:
            return ReportStatus.DONE
        return ReportStatus.PARTIAL

    @staticmethod
    def ready_for_judgement(status: ReportStatus, *, strategy_ok: bool) -> bool:
        """매수 판단으로 넘길 수 있는가 — 전략이
        없으면 skip(REPORT_INCOMPLETE) (§10)."""
        return status in (ReportStatus.DONE, ReportStatus.PARTIAL) and strategy_ok
