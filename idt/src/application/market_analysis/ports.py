"""시장 분석 포트.

Design Ref: stock-analysis-agents §4 — 플랫폼과 닿는 곳은 이 Protocol 뿐이다.
구현은 infrastructure/market_analysis 가
구조적 타이핑으로 맞춘다(이 패키지를 import 하지 않는다).
포트는 예외를 던지지 않고 실패를 값(`AgentRunOutcome.failed`,
`ToolOutcome.is_error`, None)으로 돌려준다
— 한 종목·한 섹션 실패가 회차를 멈추지 않게 (§10).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from src.domain.market_analysis.account import (
    ActivePrinciple,
    ClosedTrade,
    DecisionDraft,
    ExitReason,
    Position,
    RegimeResult,
)
from src.domain.market_analysis.index_chart import IndexBar
from src.domain.market_analysis.principle import (
    ClosedPosition,
    DecisionSummary,
    JournalDraft,
    PrincipleCandidate,
)
from src.domain.market_analysis.report import (
    AnalysisTarget,
    HeaderFacts,
    ReportStatus,
    SectionResult,
)
from src.domain.market_analysis.round import RoundCounts, RoundItemDraft
from src.domain.market_analysis.runtime import AgentRunOutcome, ToolOutcome, ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import (
    AgentRole,
    ItemStatus,
    RoundKind,
    RoundStatus,
    RoundTrigger,
)

T = TypeVar("T", bound=BaseModel)


class PermissionCodesReader(Protocol):
    """AccessPort 의 재료 — 사용자의 최종 권한 코드(role 기본 + 추가 부여)."""

    async def codes_for(
        self, user_id: int, role: str, request_id: str
    ) -> frozenset[str]: ...


class SettingReader(Protocol):
    async def get(self, request_id: str) -> MarketAnalysisSetting: ...


class AgentRunner(Protocol):
    """빌더 에이전트 1회 실행 (§4 AgentRunnerPort).
    대화 이력은 남기지 않고 실행 기록(ai_run)만 남긴다."""

    async def run(
        self,
        *,
        agent_id: str,
        query: str,
        reference_context: str | None,
        run_as_user_id: str,
        request_id: str,
    ) -> AgentRunOutcome: ...


class MarketTools(Protocol):
    """MCP 시장 도구를 LLM 없이 직접 호출 (§4
    MarketToolPort). 허용목록 밖 도구는 호출 전 거부."""

    async def call(
        self,
        *,
        source: ToolSource,
        server_id: str,
        tool: str,
        args: dict[str, Any],
        run_as_user_id: str,
        request_id: str,
    ) -> ToolOutcome: ...

    async def news(
        self, *, query: str, days: int, max_results: int, request_id: str
    ) -> ToolOutcome: ...


class ReportStore(Protocol):
    """ma_report · ma_evidence · ma_report_section 쓰기 (module-4)."""

    async def create_report(
        self, *, target: AnalysisTarget, header: HeaderFacts | None, request_id: str
    ) -> int: ...

    async def add_evidence(
        self, *, report_id: int, outcomes: list[ToolOutcome], request_id: str
    ) -> None: ...

    async def save_section(
        self, *, report_id: int, section: SectionResult, request_id: str
    ) -> None: ...

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
    ) -> None: ...


class RoleAgentStore(Protocol):
    """ma_role_agent — 역할 ↔ 빌더 에이전트."""

    async def get_all(self, request_id: str) -> dict[AgentRole, str]: ...

    async def set(
        self, *, role: AgentRole, agent_id: str, updated_by: str, request_id: str
    ) -> None: ...


class AgentCreator(Protocol):
    """플랫폼에 빌더 에이전트를 만든다 (bootstrap). 실패는 (None, 사유)."""

    async def create(
        self,
        *,
        name: str,
        system_prompt: str,
        tool_ids: list[str],
        owner_user_id: str,
        token_limit: int,
        request_id: str,
    ) -> tuple[str | None, str | None]: ...


class RoundStore(Protocol):
    """ma_round · ma_round_item (module-5). 선점은
    DB UNIQUE(trade_date, slot, run_trigger)."""

    async def try_claim(
        self,
        *,
        trade_date: date,
        slot: str,
        kind: RoundKind,
        trigger: RoundTrigger,
        request_id: str,
    ) -> int | None:
        """새 회차 행(running)을 만든다. 이미
        있으면 None — 다른 인스턴스·이전 틱이 처리했다."""
        ...

    async def any_running(self, *, exclude_id: int | None, request_id: str) -> bool: ...

    async def skip(self, *, round_id: int, reason: str, request_id: str) -> None: ...

    async def add_items(
        self, *, round_id: int, items: list[RoundItemDraft], request_id: str
    ) -> dict[str, int]:
        """종목 → item id."""
        ...

    async def update_item(
        self,
        *,
        item_id: int,
        status: ItemStatus,
        report_id: int | None = None,
        tokens: int = 0,
        cost_usd: Decimal = Decimal("0"),
        error: str | None = None,
        request_id: str,
    ) -> None: ...

    async def finish_round(
        self,
        *,
        round_id: int,
        status: RoundStatus,
        counts: RoundCounts,
        error: str | None,
        request_id: str,
    ) -> None: ...

    async def analyzed_symbols(self, *, trade_date: date, request_id: str) -> set[str]:
        """그 거래일에 이미 분석을 마친(또는 진행 중인) 종목 — 하루 1회 분석 (FR-04)."""
        ...

    async def analysis_attempts(self, *, trade_date: date, request_id: str) -> int:
        """그 거래일의 분석 시도 행 수(done·analyzing·queued·failed) — 하루 상한
        예산 (FR-02, G8). 같은 종목이 다시 실패하면 다시 센다."""
        ...

    async def abandon_running(self, request_id: str) -> int:
        """기동 시 회수 — running 회차를 abandoned
        로, 그 회차의 queued/analyzing 종목을 failed 로."""
        ...


class HeldReader(Protocol):
    """보유 중인 종목 — 매수 분석 대신 매도 판단으로
    보낸다 (FR-04). module-6 에서 포지션으로 구현."""

    async def held_symbols(self, request_id: str) -> set[str]: ...


class StructuredExtractor(Protocol):
    """에이전트 답변에서 JSON 파싱이 실패했을 때 보조
    LLM 으로 다시 구조화 (DD8). 실패하면 None."""

    async def extract(
        self, *, text: str, schema: type[T], request_id: str
    ) -> T | None: ...


class PositionStore(Protocol):
    """ma_position — 가상 계좌 (module-6). 진입·청산 값은 결정론 정책이 정한다."""

    async def open_positions(self, request_id: str) -> list[Position]: ...

    async def open_position(
        self,
        *,
        symbol: str,
        name: str | None,
        sector: str | None,
        entry_price: Decimal,
        entry_at: datetime,
        target_price: Decimal,
        stop_loss: Decimal,
        buy_decision_id: int | None,
        request_id: str,
    ) -> int: ...

    async def close_position(
        self,
        *,
        position_id: int,
        exit_price: Decimal,
        exit_at: datetime,
        reason: ExitReason,
        profit_rate: Decimal,
        holding_days: int,
        request_id: str,
    ) -> None: ...

    async def adjust_levels(
        self,
        *,
        position_id: int,
        target_price: Decimal,
        stop_loss: Decimal,
        request_id: str,
    ) -> None: ...

    async def closed_trades(self, request_id: str) -> list[ClosedTrade]: ...


class DecisionStore(Protocol):
    """ma_decision — 매수·매도 판단 기록."""

    async def add(self, draft: DecisionDraft, request_id: str) -> int: ...

    async def link_position(
        self, *, decision_id: int, position_id: int, request_id: str
    ) -> None: ...

    async def mark_entry_failed(
        self, *, decision_id: int, reason: str, request_id: str
    ) -> None:
        """enter 판단을 skip 으로 되돌린다 — 포지션 생성 실패 시 (중간 점검 M3)."""
        ...


class RegimeStore(Protocol):
    """ma_market_regime · ma_equity_snapshot — 일자별 1행, 다시 쓰면 덮어쓴다."""

    async def save_regime(
        self,
        *,
        trade_date: date,
        result: RegimeResult,
        kosdaq_close: Decimal | None,
        bars: int,
        request_id: str,
    ) -> None: ...

    async def first_closes(
        self, request_id: str
    ) -> tuple[Decimal | None, Decimal | None] | None:
        """가장 이른 날의 (KOSPI, KOSDAQ) 종가 — 지수 누적 수익률의 기준."""
        ...

    async def save_snapshot(
        self,
        *,
        trade_date: date,
        realized_cum_rate: Decimal,
        open_positions: int,
        used_slots: Decimal,
        kospi_cum_rate: Decimal | None,
        kosdaq_cum_rate: Decimal | None,
        request_id: str,
    ) -> None: ...


class PrincipleReader(Protocol):
    """활성 매매 원칙 (module-7 에서 구현). scope 는 buy·sell."""

    async def active(
        self, *, scope: str, limit: int, request_id: str
    ) -> list[ActivePrinciple]: ...


class JournalStore(Protocol):
    """ma_journal + 저널 재료(청산 포지션 · 그 포지션의 판단 이력) — module-7."""

    async def closed_position(
        self, position_id: int, request_id: str
    ) -> ClosedPosition | None: ...

    async def decisions_for(
        self, position_id: int, request_id: str
    ) -> list[DecisionSummary]:
        """그 포지션의 매수 판단(진입 근거)과 매도 판단 이력, 오래된 순."""
        ...

    async def has_journal(self, position_id: int, request_id: str) -> bool: ...

    async def save_journal(self, draft: JournalDraft, request_id: str) -> int | None:
        """저널 ID. 이미 있으면(UNIQUE) None — 같은 청산을 두 번 복기하지 않는다."""
        ...


class PrincipleStore(Protocol):
    """ma_principle 쓰기 — 후보 저장(같은 원칙이면 근거 거래 수 +1) · 켜고 끄기."""

    async def add_candidates(
        self,
        *,
        journal_id: int,
        candidates: list[PrincipleCandidate],
        auto_activate: bool,
        request_id: str,
    ) -> list[int]: ...

    async def set_active(
        self,
        *,
        principle_id: int,
        is_active: bool,
        priority: str | None,
        updated_by: str,
        request_id: str,
    ) -> bool:
        """원칙이 없으면 False."""
        ...


class SettingWriter(Protocol):
    """ma_setting 단일 행 쓰기 (module-8). 검증은 호출자가 끝낸 값만 들어온다."""

    async def save(
        self, setting: MarketAnalysisSetting, *, updated_by: str, request_id: str
    ) -> None: ...


class ReferenceChecker(Protocol):
    """설정·매핑이 가리키는 플랫폼 대상이 실제로 쓸 수 있는지 (§5.2 검증)."""

    async def mcp_server_active(self, server_id: str, request_id: str) -> bool: ...

    async def user_active(self, user_id: str, request_id: str) -> bool: ...

    async def agent_usable(self, agent_id: str, request_id: str) -> bool:
        """있고 삭제되지 않은 빌더 에이전트."""
        ...


class QueryStore(Protocol):
    """조회 화면용 읽기 (module-8). JSON 으로 바로 내보낼 dict 를 돌려준다 — 시각은
    UTC ISO(+00:00), 거래일은 YYYY-MM-DD, 금액·비율은 float. 없으면 None."""

    async def closed_trades(self, request_id: str) -> list[dict[str, Any]]:
        """청산 건 + 진입 근거 리포트의 신호 규칙 목록(`rules`)."""
        ...

    async def open_summary(self, request_id: str) -> dict[str, Any]: ...

    async def equity_series(
        self, limit: int, request_id: str
    ) -> list[dict[str, Any]]: ...

    async def latest_regime(self, request_id: str) -> dict[str, Any] | None: ...

    async def last_round(self, request_id: str) -> dict[str, Any] | None: ...

    async def list_positions(
        self, *, status: str, page: int, size: int, request_id: str
    ) -> tuple[list[dict[str, Any]], int]: ...

    async def position_detail(
        self, position_id: int, request_id: str
    ) -> dict[str, Any] | None: ...

    async def list_decisions(
        self, *, kind: str, decision: str | None, page: int, size: int, request_id: str
    ) -> tuple[list[dict[str, Any]], int]: ...

    async def list_reports(
        self,
        *,
        symbol: str | None,
        trade_date: date | None,
        page: int,
        size: int,
        request_id: str,
    ) -> tuple[list[dict[str, Any]], int]: ...

    async def report_detail(
        self, report_id: int, request_id: str
    ) -> dict[str, Any] | None: ...

    async def list_rounds(
        self, *, page: int, size: int, request_id: str
    ) -> tuple[list[dict[str, Any]], int]: ...

    async def round_detail(
        self, round_id: int, request_id: str
    ) -> dict[str, Any] | None: ...

    async def principles(self, request_id: str) -> list[dict[str, Any]]: ...

    async def recent_journals(
        self, limit: int, request_id: str
    ) -> list[dict[str, Any]]: ...


class IndexDailyStore(Protocol):
    """market-index-ytd-chart §3.4.

    ma_index_daily 읽기·덮어쓰기, ma_market_regime 읽기.
    """

    async def last_date(self, index: str, since: date, request_id: str) -> date | None:
        """since 이후 저장된 마지막 거래일."""
        ...

    async def upsert(self, bars: list[IndexBar], request_id: str) -> int:
        """확정 봉만 덮어써 저장, 저장한 수."""
        ...

    async def bars(
        self, index: str, start: date, end: date, request_id: str
    ) -> list[IndexBar]: ...

    async def regimes(
        self, start: date, end: date, request_id: str
    ) -> list[tuple[date, str]]: ...
