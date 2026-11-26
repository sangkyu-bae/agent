"""SQLAlchemy ORM 모델: ma_* 13개 (V100).

Design Ref: stock-analysis-agents §3.3. 컬럼·COMMENT 는 마이그레이션과 같게 둔다
(tests/infrastructure/market_analysis/test_models_match_migration.py 가 대조한다).
플랫폼 테이블에는 FK 를 걸지 않는다 — 모듈을 떼어낼 때 테이블만 옮긴다.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base

_ID = BigInteger().with_variant(Integer, "sqlite")
_MEDIUM = Text().with_variant(MEDIUMTEXT(), "mysql")
_PRICE = Numeric(14, 2)
_COST = Numeric(12, 6)


def _pk(comment: str) -> Any:
    return mapped_column(_ID, primary_key=True, autoincrement=True, comment=comment)


class MaSettingModel(Base):
    __tablename__ = "ma_setting"
    __table_args__ = {"comment": "시장 분석 모듈 설정 (단일 행)"}

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, comment="설정 행 ID (항상 1)"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="자동 분석 스위치"
    )
    round_times: Mapped[list] = mapped_column(
        JSON, nullable=False, comment="회차 시각 목록 (KST HH:MM)"
    )
    max_per_round: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, comment="회차당 최대 분석 종목 수"
    )
    max_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50, comment="하루 최대 분석 종목 수"
    )
    max_concurrent_stocks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, comment="동시 분석 종목 수"
    )
    max_concurrent_runs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4, comment="동시 에이전트 실행 수"
    )
    signal_rules: Mapped[list] = mapped_column(
        JSON, nullable=False, comment="분석 대상으로 삼을 신호 규칙 목록"
    )
    rule_params: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="신호 규칙 파라미터 (scan_signals rule_params)"
    )
    ranking_kinds: Mapped[list] = mapped_column(
        JSON, nullable=False, comment="후보 수집에 쓰는 순위 종류"
    )
    ranking_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, comment="순위 종류별 후보 수"
    )
    condition_seqs: Mapped[list] = mapped_column(
        JSON, nullable=False, comment="HTS 조건검색 seq 목록"
    )
    intraday_entry_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="장중 회차 진입 허용"
    )
    slot_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, comment="가상 계좌 슬롯 수"
    )
    min_score_by_regime: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="시장 체제별 최소 매수 점수"
    )
    min_rr: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, comment="최소 손익비"
    )
    max_stop_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, comment="최대 손절폭 (%)"
    )
    min_stop_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, comment="최소 손절폭 (%)"
    )
    max_principles: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, comment="판단에 넣을 활성 원칙 최대 수"
    )
    principle_auto_activate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="원칙 후보 자동 활성 여부"
    )
    run_as_user_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="에이전트 실행 신원 (사용자 ID)"
    )
    kis_server_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="KIS MCP 서버 ID"
    )
    dart_server_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="DART MCP 서버 ID"
    )
    perplexity_server_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="Perplexity MCP 서버 ID"
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="마지막 수정자 (사용자 ID)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수정 시각 (UTC)"
    )


class MaRoleAgentModel(Base):
    __tablename__ = "ma_role_agent"
    __table_args__ = {"comment": "시장 분석 역할별 담당 에이전트"}

    role: Mapped[str] = mapped_column(
        String(32), primary_key=True, comment="역할 (section_technical 등 11종)"
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="매핑한 빌더 에이전트 ID"
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="마지막 수정자 (사용자 ID)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수정 시각 (UTC)"
    )


class MaRoundModel(Base):
    __tablename__ = "ma_round"
    __table_args__ = (
        UniqueConstraint("trade_date", "slot", "run_trigger", name="uq_ma_round_slot"),
        Index("ix_ma_round_status", "status"),
        {"comment": "시장 분석 회차 (UNIQUE 로 다중 인스턴스 1회 실행 보장)"},
    )

    id: Mapped[int] = _pk("회차 ID")
    trade_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="거래일 (KST)"
    )
    slot: Mapped[str] = mapped_column(
        String(5), nullable=False, comment="회차 시각 (KST HH:MM)"
    )
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="intraday|close"
    )
    run_trigger: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="auto|manual"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="running|done|skipped|failed|abandoned"
    )
    skip_reason: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="건너뜀 사유 (DISABLED·WEEKEND·HOLIDAY·BUSY)"
    )
    candidates: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="수집한 후보 종목 수"
    )
    signaled: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="신호가 난 종목 수"
    )
    analyzed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="분석 완료 종목 수"
    )
    over_cap: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="상한 초과로 분석하지 않은 종목 수"
    )
    failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="분석 실패 종목 수"
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="회차 토큰 합계"
    )
    total_cost_usd: Mapped[Decimal] = mapped_column(
        _COST, nullable=False, default=Decimal("0"), comment="회차 비용 합계 (USD)"
    )
    error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="회차 실패 사유"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="시작 시각 (UTC)"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="종료 시각 (UTC)"
    )


class MaRoundItemModel(Base):
    __tablename__ = "ma_round_item"
    __table_args__ = (
        Index("ix_ma_round_item_round", "round_id"),
        Index("ix_ma_round_item_symbol", "symbol", "created_at"),
        {"comment": "시장 분석 회차별 종목 처리 결과"},
    )

    id: Mapped[int] = _pk("회차 종목 ID")
    round_id: Mapped[int] = mapped_column(
        _ID,
        ForeignKey("ma_round.id", ondelete="CASCADE"),
        nullable=False,
        comment="회차 ID",
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, comment="종목 코드")
    name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="종목명"
    )
    signals: Mapped[list] = mapped_column(
        JSON, nullable=False, comment="발생한 신호 (규칙명과 값)"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="queued|analyzing|done|failed|over_cap|duplicate|held",
    )
    error: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="실패 사유"
    )
    report_id: Mapped[int | None] = mapped_column(
        _ID, nullable=True, comment="생성된 리포트 ID"
    )
    tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="종목 토큰 합계"
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        _COST, nullable=False, default=Decimal("0"), comment="종목 비용 합계 (USD)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각 (UTC)"
    )


class MaReportModel(Base):
    __tablename__ = "ma_report"
    __table_args__ = (
        Index("ix_ma_report_date", "trade_date"),
        Index("ix_ma_report_symbol", "symbol"),
        {"comment": "시장 분석 종목 리포트"},
    )

    id: Mapped[int] = _pk("리포트 ID")
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, comment="종목 코드")
    name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="종목명"
    )
    trade_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="거래일 (KST)"
    )
    round_id: Mapped[int | None] = mapped_column(
        _ID, nullable=True, comment="만든 회차 ID"
    )
    provisional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="미확정 봉 기반 여부"
    )
    signals: Mapped[list] = mapped_column(
        JSON, nullable=False, comment="분석 계기가 된 신호"
    )
    header_facts: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="머리 사실 (도구 결과에서 결정론 렌더)"
    )
    strategy: Mapped[str | None] = mapped_column(
        _MEDIUM, nullable=True, comment="투자 시나리오·리스크 본문"
    )
    summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="핵심 요약"
    )
    regime: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="분석 시점 시장 체제"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="running|done|partial|failed"
    )
    tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="리포트 토큰 합계"
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        _COST, nullable=False, default=Decimal("0"), comment="리포트 비용 합계 (USD)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각 (UTC)"
    )


class MaReportSectionModel(Base):
    __tablename__ = "ma_report_section"
    __table_args__ = (
        UniqueConstraint("report_id", "role", name="uq_ma_report_section"),
        {"comment": "시장 분석 리포트 섹션"},
    )

    id: Mapped[int] = _pk("섹션 ID")
    report_id: Mapped[int] = mapped_column(
        _ID,
        ForeignKey("ma_report.id", ondelete="CASCADE"),
        nullable=False,
        comment="리포트 ID",
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, comment="섹션 역할")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="done|failed|empty"
    )
    content: Mapped[str | None] = mapped_column(
        _MEDIUM, nullable=True, comment="섹션 본문 (Markdown)"
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="에이전트 실행 ID (ai_run)"
    )
    tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="섹션 토큰"
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        _COST, nullable=False, default=Decimal("0"), comment="섹션 비용 (USD)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각 (UTC)"
    )


class MaEvidenceModel(Base):
    __tablename__ = "ma_evidence"
    __table_args__ = (
        Index("ix_ma_evidence_report", "report_id"),
        {"comment": "시장 분석 리포트 근거 (prefetch 도구 결과)"},
    )

    id: Mapped[int] = _pk("근거 ID")
    report_id: Mapped[int] = mapped_column(
        _ID,
        ForeignKey("ma_report.id", ondelete="CASCADE"),
        nullable=False,
        comment="리포트 ID",
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="kis|dart|tavily|perplexity"
    )
    tool: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="호출한 도구 이름"
    )
    args: Mapped[dict] = mapped_column(JSON, nullable=False, comment="도구 인자")
    payload: Mapped[str | None] = mapped_column(
        _MEDIUM, nullable=True, comment="도구 결과 원문"
    )
    is_error: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="도구 오류 여부"
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="조회 시각 (UTC)"
    )


class MaDecisionModel(Base):
    __tablename__ = "ma_decision"
    __table_args__ = (
        Index("ix_ma_decision_kind", "kind", "decision", "created_at"),
        Index("ix_ma_decision_symbol", "symbol"),
        {"comment": "시장 분석 매수·매도 판단 (매수 보류는 관심종목)"},
    )

    id: Mapped[int] = _pk("판단 ID")
    kind: Mapped[str] = mapped_column(String(8), nullable=False, comment="buy|sell")
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, comment="종목 코드")
    name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="종목명"
    )
    report_id: Mapped[int | None] = mapped_column(
        _ID, nullable=True, comment="근거 리포트 ID (매수 판단)"
    )
    position_id: Mapped[int | None] = mapped_column(
        _ID, nullable=True, comment="대상 포지션 ID (매도 판단·진입 결과)"
    )
    score: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="매수 점수 (1~10)"
    )
    decision: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="enter|skip|hold|sell|adjust"
    )
    target_price: Mapped[Decimal | None] = mapped_column(
        _PRICE, nullable=True, comment="목표가"
    )
    stop_loss: Mapped[Decimal | None] = mapped_column(
        _PRICE, nullable=True, comment="손절가"
    )
    investment_period: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="투자 기간 (단기·중기·장기)"
    )
    sector: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="섹터"
    )
    confidence: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="확신도 (1~10, 매도 판단)"
    )
    rationale: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="판단 근거"
    )
    skip_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="보류 사유 (게이트 사유 포함)"
    )
    gate: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="결정론 게이트 결과"
    )
    principles_used: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="판단에 넣은 원칙 ID 목록"
    )
    price_at_decision: Mapped[Decimal | None] = mapped_column(
        _PRICE, nullable=True, comment="판단 시점 현재가"
    )
    regime: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="판단 시점 시장 체제"
    )
    provisional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="미확정 봉 기반 여부"
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="에이전트 실행 ID (ai_run)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="판단 시각 (UTC)"
    )


class MaPositionModel(Base):
    __tablename__ = "ma_position"
    __table_args__ = (
        Index("ix_ma_position_status", "status"),
        Index("ix_ma_position_symbol", "symbol"),
        {"comment": "시장 분석 가상 계좌 포지션"},
    )

    id: Mapped[int] = _pk("포지션 ID")
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, comment="종목 코드")
    name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="종목명"
    )
    sector: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="섹터"
    )
    status: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="open|closed"
    )
    slot_weight: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        nullable=False,
        default=Decimal("1.000"),
        comment="사용 슬롯 비중",
    )
    entry_price: Mapped[Decimal] = mapped_column(
        _PRICE, nullable=False, comment="진입가"
    )
    entry_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="진입 시각 (UTC)"
    )
    target_price: Mapped[Decimal] = mapped_column(
        _PRICE, nullable=False, comment="현재 목표가"
    )
    stop_loss: Mapped[Decimal] = mapped_column(
        _PRICE, nullable=False, comment="현재 손절가"
    )
    exit_price: Mapped[Decimal | None] = mapped_column(
        _PRICE, nullable=True, comment="청산가"
    )
    exit_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="청산 시각 (UTC)"
    )
    exit_reason: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="target|stop|judge"
    )
    profit_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), nullable=True, comment="실현 수익률 (%)"
    )
    holding_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="보유 일수"
    )
    buy_decision_id: Mapped[int | None] = mapped_column(
        _ID, nullable=True, comment="진입 근거 매수 판단 ID"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각 (UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수정 시각 (UTC)"
    )


class MaMarketRegimeModel(Base):
    __tablename__ = "ma_market_regime"
    __table_args__ = {"comment": "시장 분석 일자별 시장 체제"}

    trade_date: Mapped[date] = mapped_column(
        Date, primary_key=True, comment="거래일 (KST)"
    )
    kospi_close: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True, comment="KOSPI 종가"
    )
    kosdaq_close: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True, comment="KOSDAQ 종가"
    )
    kospi_ma20: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True, comment="KOSPI 20일 이평"
    )
    kospi_ma60: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True, comment="KOSPI 60일 이평"
    )
    regime: Mapped[str] = mapped_column(String(16), nullable=False, comment="시장 체제")
    basis: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="판정 근거 (20일 수익률·봉 수 등)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="계산 시각 (UTC)"
    )


class MaEquitySnapshotModel(Base):
    __tablename__ = "ma_equity_snapshot"
    __table_args__ = {"comment": "시장 분석 일자별 성과 스냅샷"}

    trade_date: Mapped[date] = mapped_column(
        Date, primary_key=True, comment="거래일 (KST)"
    )
    realized_cum_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, comment="누적 실현 수익률 (%)"
    )
    open_positions: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="보유 종목 수"
    )
    used_slots: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, comment="사용 슬롯"
    )
    kospi_cum_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4), nullable=True, comment="KOSPI 누적 수익률 (%)"
    )
    kosdaq_cum_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4), nullable=True, comment="KOSDAQ 누적 수익률 (%)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="기록 시각 (UTC)"
    )


class MaJournalModel(Base):
    __tablename__ = "ma_journal"
    __table_args__ = (
        UniqueConstraint("position_id", name="uq_ma_journal_position"),
        {"comment": "시장 분석 청산 저널"},
    )

    id: Mapped[int] = _pk("저널 ID")
    position_id: Mapped[int] = mapped_column(
        _ID,
        ForeignKey("ma_position.id", ondelete="CASCADE"),
        nullable=False,
        comment="청산된 포지션 ID",
    )
    one_line: Mapped[str | None] = mapped_column(
        String(300), nullable=True, comment="한 줄 요약"
    )
    situation: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="상황 분석"
    )
    evaluation: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="판단 평가"
    )
    lessons: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="교훈 목록"
    )
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="패턴 태그")
    raw_answer: Mapped[str | None] = mapped_column(
        _MEDIUM, nullable=True, comment="구조화 실패 시 에이전트 원문"
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="에이전트 실행 ID (ai_run)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="작성 시각 (UTC)"
    )


class MaPrincipleModel(Base):
    __tablename__ = "ma_principle"
    __table_args__ = (
        Index("ix_ma_principle_active", "is_active", "priority"),
        {"comment": "시장 분석 매매 원칙 (저널에서 생성)"},
    )

    id: Mapped[int] = _pk("원칙 ID")
    condition_text: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="적용 조건"
    )
    action_text: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="취할 행동"
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="근거")
    scope: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="buy|sell|all"
    )
    priority: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="high|medium|low"
    )
    confidence: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="확신도 (1~10)"
    )
    supporting_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="근거 거래 수"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="판단에 넣는지 여부"
    )
    source_journal_id: Mapped[int | None] = mapped_column(
        _ID, nullable=True, comment="출처 저널 ID"
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="마지막 수정자 (사용자 ID)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각 (UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수정 시각 (UTC)"
    )
