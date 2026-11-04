"""SQLAlchemy ORM 모델: tool_access_default / tool_access_department / tool_access_user.

Design Ref: tool-access-control §3.3
FK·CASCADE 의 진실은 DDL(V082)이다. ORM 에는 FK 를 선언하지 않는다 — 프로젝트의
기존 관례(위키 erd-agent-run: "ORM에 FK 없음 ≠ DB에 FK 없음")와 같고, 저장소
테스트가 tool_catalog/users/departments 모델 없이 테이블만 만들 수 있게 한다.
"""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ToolAccessDefaultModel(Base):
    __tablename__ = "tool_access_default"

    tool_id: Mapped[str] = mapped_column(String(150), primary_key=True)
    granted_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)


class ToolAccessDepartmentModel(Base):
    __tablename__ = "tool_access_department"
    __table_args__ = (Index("ix_tadept_dept", "department_id"),)

    tool_id: Mapped[str] = mapped_column(String(150), primary_key=True)
    department_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    granted_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)


class ToolAccessUserModel(Base):
    __tablename__ = "tool_access_user"
    __table_args__ = (Index("ix_tau_user", "user_id"),)

    tool_id: Mapped[str] = mapped_column(String(150), primary_key=True)
    # 복합 PK 의 정수 컬럼이 자동 증가로 해석되지 않도록 명시한다.
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    granted_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
