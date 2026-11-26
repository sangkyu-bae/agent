"""시장 분석 값 객체.

Design Ref: stock-analysis-agents §3.1 — DB 에는 문자열로 저장하므로 전부 str Enum 이다.
"""

from __future__ import annotations

from enum import StrEnum


class AgentRole(StrEnum):
    """빌더 에이전트를 매핑하는 역할 단위 (ma_role_agent.role)."""

    SECTION_TECHNICAL = "section_technical"
    SECTION_FLOW = "section_flow"
    SECTION_FINANCIAL = "section_financial"
    SECTION_COMPANY = "section_company"
    SECTION_NEWS = "section_news"
    SECTION_MARKET = "section_market"
    STRATEGY = "strategy"
    SUMMARY = "summary"
    BUY_JUDGE = "buy_judge"
    SELL_JUDGE = "sell_judge"
    JOURNAL = "journal"

    @classmethod
    def section_roles(cls) -> tuple[AgentRole, ...]:
        """리포트 본문 6섹션 — 서로 독립이라 병렬로 돌릴 수 있다 (design §2.3)."""
        return (
            cls.SECTION_TECHNICAL,
            cls.SECTION_FLOW,
            cls.SECTION_FINANCIAL,
            cls.SECTION_COMPANY,
            cls.SECTION_NEWS,
            cls.SECTION_MARKET,
        )


class Regime(StrEnum):
    """시장 체제 — RegimePolicy 가 지수로 결정론 계산한다 (design §6)."""

    STRONG_BULL = "strong_bull"
    BULL = "bull"
    NEUTRAL = "neutral"
    BEAR = "bear"
    STRONG_BEAR = "strong_bear"


class RoundKind(StrEnum):
    INTRADAY = "intraday"
    CLOSE = "close"


class RoundTrigger(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class RoundStatus(StrEnum):
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"
    ABANDONED = "abandoned"


class ItemStatus(StrEnum):
    """회차 안 종목 1개의 상태 (ma_round_item.status)."""

    QUEUED = "queued"
    ANALYZING = "analyzing"
    DONE = "done"
    FAILED = "failed"
    OVER_CAP = "over_cap"
    DUPLICATE = "duplicate"
    HELD = "held"
