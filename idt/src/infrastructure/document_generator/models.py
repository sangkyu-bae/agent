"""SQLAlchemy ORM 모델: document_generation_type (doc-generator Design §3, V059 매핑)."""
from datetime import datetime

from sqlalchemy import DateTime, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class DocumentGenerationTypeModel(Base):
    __tablename__ = "document_generation_type"
    __table_args__ = (
        # 유니크 아님 — soft-delete 재등록 허용, active 1개는 UseCase가 보장 (V037 선례).
        Index(
            "idx_document_generation_type_agent_worker",
            "agent_id", "worker_id", "status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="문서 유형 ID (UUID)"
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="소유 에이전트 ID (agent_definition FK)"
    )
    worker_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="대상 워커 ID (document_generator 도구 워커)"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="문서 유형명 (산출 파일명·프롬프트에 사용)"
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=False, default="",
        comment="문서 용도 설명 (작성 프롬프트에 주입)",
    )
    sections: Mapped[list] = mapped_column(
        JSON, nullable=False, comment="섹션 아웃라인 (title·guidance 객체 배열 — 순서 보존)"
    )
    output_format: Mapped[str] = mapped_column(
        String(8), nullable=False, default="docx",
        comment="출력 포맷 (pdf|docx, 기본 docx — D4)",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active",
        comment="상태 (active|deleted, soft-delete)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각 (UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수정 시각 (UTC)"
    )
