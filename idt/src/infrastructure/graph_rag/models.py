"""SQLAlchemy ORM: graph_rag_setting (V086), graph_rag_stage_change (V087),
graph_extraction_job (V088).

Design Ref: graph-rag-foundation §3.3 — comment= 는 마이그레이션 COMMENT 와 같은 문구.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base

# V086 시드 행 id — 단일 행 테이블의 고정 키
GRAPH_RAG_SETTING_ID = "c0000000-0000-4000-8000-000000000001"


class GraphRagSettingModel(Base):
    __tablename__ = "graph_rag_setting"
    __table_args__ = {"comment": "그래프 RAG 전역 설정 — 단일 행"}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="고정 단일 행 식별자"
    )
    rollout_stage: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="off",
        comment="노출 단계 off 또는 admin_only 또는 general",
    )
    extraction_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="업로드 후 자동 추출 여부"
    )
    jev_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Jev 판정 사용 여부 — 끄면 LLM 선택으로 판정",
    )
    link_threshold: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        nullable=False,
        default=Decimal("0.800"),
        comment="이 확률 이상이면 기존 엔티티에 연결",
    )
    new_threshold: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        nullable=False,
        default=Decimal("0.400"),
        comment="이 확률 미만이면 새 엔티티 생성",
    )
    extraction_llm_model_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="llm_model.id 소프트 참조 — 추출용"
    )
    rejudge_llm_model_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="llm_model.id 소프트 참조 — 재판정용 NULL이면 추출 모델",
    )
    concurrency: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, comment="추출 동시 LLM 호출 수"
    )
    max_llm_calls_per_doc: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=300,
        comment="문서당 LLM 호출 상한 — 초과 시 partial",
    )
    candidate_top_k: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, comment="판정 후보 수 상한"
    )
    max_hops: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, comment="그래프 검색 최대 탐색 단계"
    )
    graph_rrf_weight: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        nullable=False,
        default=Decimal("0.500"),
        comment="그래프 결과 RRF 가중치",
    )
    retrieval_timeout_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=800, comment="그래프 검색 시간 상한 밀리초"
    )
    entity_types: Mapped[list] = mapped_column(
        JSON, nullable=False, comment="허용 엔티티 타입 목록"
    )
    relation_types: Mapped[list] = mapped_column(
        JSON, nullable=False, comment="허용 관계 타입 목록"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="생성 시각"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="수정 시각",
    )


class GraphRagStageChangeModel(Base):
    __tablename__ = "graph_rag_stage_change"
    __table_args__ = (
        Index("idx_grsc_created", "created_at"),
        {"comment": "그래프 RAG 노출 단계 변경 이력"},
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="변경 이력 식별자"
    )
    from_stage: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="이전 단계"
    )
    to_stage: Mapped[str] = mapped_column(String(16), nullable=False, comment="새 단계")
    changed_by: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="변경한 관리자 id"
    )
    eval_baseline_run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="그래프 off RAGAS 실행 id 소프트 참조"
    )
    eval_graph_run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="그래프 on RAGAS 실행 id 소프트 참조"
    )
    force_reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="평가 기록 없이 강제 전환한 사유"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="변경 시각"
    )


def _count(comment: str) -> Mapped[int]:
    return mapped_column(Integer, nullable=False, default=0, comment=comment)


class GraphExtractionJobModel(Base):
    __tablename__ = "graph_extraction_job"
    __table_args__ = (
        Index("idx_gej_document", "document_id", "created_at"),
        Index("idx_gej_status", "status"),
        {"comment": "그래프 추출 잡 — 문서 단위 실행 이력"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="잡 식별자")
    document_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="document_metadata.document_id 소프트 참조"
    )
    kb_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="knowledge_base.id 소프트 참조"
    )
    collection_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="청크가 저장된 컬렉션"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        comment="pending 또는 processing 또는 completed 또는 partial 또는 failed",
    )
    mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="resume",
        comment="resume 완료 청크 건너뜀 또는 rebuild 문서 그래프 삭제 후 재추출",
    )
    trigger_source: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="upload 자동 또는 admin 수동"
    )
    extractor_version: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="추출기 버전 — 바뀌면 resume도 재추출"
    )
    total_chunks: Mapped[int] = _count("대상 청크 수")
    processed_chunks: Mapped[int] = _count("처리 완료 청크 수")
    failed_chunks: Mapped[int] = _count("처리 실패 청크 수")
    llm_calls: Mapped[int] = _count("추출과 판정 LLM 호출 합계")
    judge_calls: Mapped[int] = _count("Jev 호출 수")
    entities_created: Mapped[int] = _count("새로 만든 엔티티 수")
    entities_linked: Mapped[int] = _count("기존 엔티티에 연결한 언급 수")
    relations_created: Mapped[int] = _count("저장한 관계 엣지 수")
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="실패 사유 요약"
    )
    requested_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="요청 사용자 id 소프트 참조"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="처리 시작 시각"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="처리 종료 시각"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="생성 시각"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="수정 시각",
    )
