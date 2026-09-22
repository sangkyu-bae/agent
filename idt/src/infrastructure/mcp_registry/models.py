"""SQLAlchemy ORM 모델: mcp_server_registry."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class MCPServerModel(Base):
    __tablename__ = "mcp_server_registry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    transport: Mapped[str] = mapped_column(String(20), nullable=False, default="sse")
    input_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # transport별 인증/서버 config를 Fernet 암호화한 토큰 (평문 저장 금지)
    auth_config_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    server_config_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    # approval-gate-phase2 D-07 (V075): 신규 카탈로그 엔트리의 requires_approval
    # 초기값. 런타임 SoT 는 tool_catalog.requires_approval 이다.
    default_requires_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        comment="1이면 이 서버의 도구가 카탈로그에 처음 등록될 때 requires_approval=1 로 시작 (초기값 전용, 기존 엔트리 소급 없음). 기본 0 이라 기존 서버는 무영향",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
