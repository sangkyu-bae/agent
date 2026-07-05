"""SQLAlchemy ORM 모델: skill_definition."""
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class SkillDefinitionModel(Base):
    __tablename__ = "skill_definition"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # 'trigger'는 MySQL 예약어 → DB 컬럼명은 trigger_text, 파이썬 속성은 trigger
    trigger: Mapped[str | None] = mapped_column("trigger_text", Text, nullable=True)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    script_type: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    script_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    visibility: Mapped[str] = mapped_column(
        SAEnum("private", "department", "public", name="skill_visibility"),
        nullable=False,
        default="private",
        index=True,
    )
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    forked_from: Mapped[str | None] = mapped_column(String(36), nullable=True)
    forked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
