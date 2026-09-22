"""mcp_server_registry.default_requires_approval — 모델·매핑·DDL.

Design Ref: approval-gate-phase2-mcp-executor §3.3 (D-07).
매핑에서 빠지면 값이 조용히 False 로 돌아가 게이트 초기값이 무력해진다.
"""
from datetime import datetime
from pathlib import Path

from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.infrastructure.mcp_registry.mcp_server_repository import (
    _to_entity,
    _to_model,
)
from src.infrastructure.mcp_registry.models import MCPServerModel

_NOW = datetime(2026, 9, 21)
_MIGRATION = Path(
    "db/migration/V075__add_default_requires_approval_to_mcp_server_registry.sql"
)


def _entity(flag: bool) -> MCPServerRegistration:
    return MCPServerRegistration(
        id="uuid-1", user_id="u1", name="n", description="d",
        endpoint="https://x/sse", transport=MCPTransportType.SSE,
        input_schema=None, is_active=True, created_at=_NOW, updated_at=_NOW,
        default_requires_approval=flag,
    )


class TestMapping:
    def test_엔티티에서_모델로(self):
        assert _to_model(_entity(True)).default_requires_approval is True
        assert _to_model(_entity(False)).default_requires_approval is False

    def test_모델에서_엔티티로(self):
        model = _to_model(_entity(True))
        assert _to_entity(model).default_requires_approval is True

    def test_컬럼이_NULL인_행은_False로_읽는다(self):
        """마이그레이션 전 생성된 객체·부분 mock 에 대한 방어."""
        model = _to_model(_entity(False))
        model.default_requires_approval = None
        assert _to_entity(model).default_requires_approval is False


class TestModelColumn:
    def test_NOT_NULL이고_코멘트가_있다(self):
        column = MCPServerModel.__table__.c.default_requires_approval
        assert column.nullable is False
        assert column.comment

    def test_모델_코멘트가_DDL과_같다(self):
        """CLAUDE.md §3 — DDL COMMENT 와 SQLAlchemy comment= 동일 반영."""
        column = MCPServerModel.__table__.c.default_requires_approval
        assert column.comment in _MIGRATION.read_text(encoding="utf-8")


class TestMigration:
    def test_기본값_0으로_추가한다(self):
        sql = _MIGRATION.read_text(encoding="utf-8")
        assert "ALTER TABLE mcp_server_registry" in sql
        assert "default_requires_approval TINYINT(1) NOT NULL DEFAULT 0" in sql
        assert "COMMENT" in sql
