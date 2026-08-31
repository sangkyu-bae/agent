"""SQLAlchemy ORM: multimodal_setting (V065).

Design Ref: multimodal-extractor §3.3
— 전역 단일 행, vision_model_id 는 llm_model.id 소프트 참조(FK 없음).
CLAUDE.md §3: 테이블·전 컬럼 comment= 는 마이그레이션 COMMENT 와 동일 문구.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base

# V065 시드 행 id — 단일 행 테이블의 고정 키
MULTIMODAL_SETTING_ID = "b0000000-0000-4000-8000-000000000001"


class MultimodalSettingModel(Base):
    __tablename__ = "multimodal_setting"
    __table_args__ = {"comment": "멀티모달 추출 전역 설정 — 단일 행"}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="고정 단일 행 식별자"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="멀티모달 추출 활성 여부"
    )
    vision_model_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="llm_model.id 소프트 참조 — NULL이면 미설정"
    )
    max_images_per_doc: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=50,
        comment="문서당 비전 호출 상한 — 초과분은 skipped",
    )
    min_image_px: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        comment="가로·세로 최소 픽셀 — 미만은 필터 제외",
    )
    min_area_ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        default=Decimal("0.0200"),
        comment="페이지 면적 대비 최소 비율 — 미만은 필터 제외",
    )
    concurrency: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4, comment="동시 비전 호출 수"
    )
    timeout_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, comment="건당 비전 호출 타임아웃(초)"
    )
    output_language: Mapped[str] = mapped_column(
        String(8), nullable=False, default="ko", comment="설명 출력 언어 ko 또는 en"
    )
    detail_level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="detailed",
        comment="설명 상세도 brief 또는 detailed",
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
