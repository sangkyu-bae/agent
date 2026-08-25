"""SQLAlchemy ORM: document_blueprint / document_blueprint_asset (V066).

Design Ref: golden-sample-blueprint §3.3 / D2 (에셋 LONGBLOB 영구 보관)
CLAUDE.md §3: 테이블·전 컬럼 comment= 는 마이그레이션 COMMENT 와 동일 문구.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, LargeBinary, String, func
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base

_BLOB = LargeBinary().with_variant(LONGBLOB(), "mysql")


class DocumentBlueprintModel(Base):
    __tablename__ = "document_blueprint"
    __table_args__ = {"comment": "Golden Sample 에서 추출한 발표자료 양식 blueprint"}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="blueprint 식별자 UUID"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="표시 이름")
    description: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", comment="설명"
    )
    source_kind: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="원본 종류 pdf 또는 pptx"
    )
    page_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="원본 페이지 수"
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="blueprint JSON 스키마 버전"
    )
    blueprint_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="style·patterns·narrative·font_mapping·warnings 직렬화",
    )
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="active",
        comment="상태 active 또는 inactive",
    )
    created_by: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="등록 관리자 사용자 식별자"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="생성 시각"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="수정 시각"
    )


class DocumentBlueprintAssetModel(Base):
    __tablename__ = "document_blueprint_asset"
    __table_args__ = {"comment": "blueprint 로고·장식·표지 이미지 에셋"}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="에셋 식별자 UUID"
    )
    blueprint_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True, comment="소속 document_blueprint.id"
    )
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="에셋 종류 logo 또는 decoration 또는 cover"
    )
    mime: Mapped[str] = mapped_column(String(50), nullable=False, comment="MIME 타입")
    width: Mapped[int] = mapped_column(Integer, nullable=False, comment="픽셀 너비")
    height: Mapped[int] = mapped_column(Integer, nullable=False, comment="픽셀 높이")
    sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="이미지 내용 해시"
    )
    box_json: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="슬라이드 비율 좌표 x y w h"
    )
    adopted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="관리자 채택 여부"
    )
    data: Mapped[bytes] = mapped_column(
        _BLOB, nullable=False, comment="이미지 바이트 — TTL 없는 영구 보관"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="생성 시각"
    )
