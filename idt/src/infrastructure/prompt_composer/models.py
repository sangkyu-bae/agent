"""SQLAlchemy ORM 모델: prompt_session / prompt_version (V061·V062).

Design Ref: §3.3.
DDL COMMENT 규칙 (V054+): 테이블·전 컬럼 comment= 동반 필수 — 마이그레이션 SQL 과
동일 문구를 유지한다.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.prompt_composer.schemas import PROMPT_SOURCE_LLM
from src.infrastructure.persistence.models.base import Base


class PromptSessionModel(Base):
    __tablename__ = "prompt_session"
    __table_args__ = (
        Index("ix_prompt_session_user", "user_id", "created_at"),
        Index("ix_prompt_session_agent", "agent_id"),
        {
            "comment": (
                "시스템 프롬프트 생성 세션 — 하나의 요청에서 파생된 버전들의 묶음"
            )
        },
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="세션 ID (uuid4)"
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="생성 요청 사용자 ID (조회 인가 기준)",
    )
    # Design §3.3 — FK 미설정. 에이전트 삭제가 이력 삭제로 전이되면 안 된다.
    agent_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment=(
            "바인딩된 에이전트 ID. 생성 시점엔 미저장 상태라 NULL 허용(Design D5). "
            "FK 미설정 — 에이전트 삭제가 이력 삭제로 전이되면 안 됨"
        ),
    )
    user_request: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="최초 자연어 요청 원문 (최대 1000자, 서버 검증)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="세션 생성 시각 (UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        comment="수정 시각 (UTC). agent_id 백필 시 갱신",
    )


class PromptVersionModel(Base):
    __tablename__ = "prompt_version"
    __table_args__ = (
        UniqueConstraint("session_id", "version_no", name="uq_session_version"),
        {
            "comment": (
                "시스템 프롬프트 버전 이력 — 생성 1회당 1행, 근거(의도·도구) 동봉"
            )
        },
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="버전 ID (uuid4)"
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prompt_session.id", ondelete="CASCADE"),
        nullable=False,
        comment="소속 prompt_session ID",
    )
    version_no: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="세션 내 버전 번호 (1부터 증가)"
    )
    # Design Q4 — 구조 변경 시 증가시켜 과거 행을 분기 파싱한다 (R6 완화).
    schema_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        comment=(
            "sections JSON 구조 버전. 구조 변경 시 증가시켜 과거 행 파싱 분기 "
            "(Design Q4)"
        ),
    )
    # agent-create-wizard Design Ref: §3.4 — 위저드에서 사용자가 편집한 프롬프트를
    # 새 버전으로 쌓을 때 LLM 생성본과 구분한다 (V063).
    source: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=PROMPT_SOURCE_LLM,
        comment="프롬프트 작성 주체 — llm(생성) 또는 human(사용자 편집본)",
    )
    sections: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="구조화 섹션 — purpose / roles / tool_guides / principles 4키",
    )
    assembled: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="서버가 결정적으로 조립한 최종 시스템 프롬프트 문자열",
    )
    intent_snapshot: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "생성에 사용된 IntentResult 원본 스냅샷. 미주입이거나 degraded 면 NULL"
        ),
    )
    tool_ids: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="생성에 실제 반영된 tool_id 배열 (환각 폐기·미존재 제외 후)",
    )
    degraded: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="LLM 실패로 규칙기반 폴백이 쓰였는지 여부",
    )
    reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="degraded 사유(error|timeout|schema|empty) 또는 관측 메모",
    )
    elapsed_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="LLM 호출 소요 시간(ms). 관측용",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="버전 생성 시각 (UTC)"
    )
