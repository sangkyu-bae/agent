"""users.mailbox_upn — 모델·매핑·DDL.

Design Ref: mcp-identity-header §3.3. 매핑에서 빠지면 신원 헤더 발급 시
모든 사용자가 '메일함 미등록'으로 거부된다.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.auth.entities import User
from src.infrastructure.auth.models import UserModel
from src.infrastructure.auth.user_repository import UserRepository, _to_entity

_MIGRATION = Path("db/migration/V076__add_mailbox_upn_to_users.sql")


def _model(mailbox: str | None) -> UserModel:
    return UserModel(
        id=7, email="kim@login.local", password_hash="h",
        role="user", status="approved", mailbox_upn=mailbox,
    )


class TestMapping:
    def test_모델에서_엔티티로_mailbox를_옮긴다(self):
        assert _to_entity(_model("kim@corp.com")).mailbox_upn == "kim@corp.com"

    def test_NULL이면_None(self):
        assert _to_entity(_model(None)).mailbox_upn is None

    @pytest.mark.asyncio
    async def test_save가_mailbox를_모델에_싣는다(self):
        session = AsyncMock()
        session.add = MagicMock()
        repo = UserRepository(session=session, logger=MagicMock())
        await repo.save(
            User(email="kim@login.local", password_hash="h", mailbox_upn="kim@corp.com")
        )
        added = session.add.call_args.args[0]
        assert added.mailbox_upn == "kim@corp.com"


class TestUpdateMailbox:
    @pytest.mark.asyncio
    async def test_UPDATE만_실행하고_commit하지_않는다(self):
        """DB-001 — commit 은 get_session 의존성이 담당한다."""
        session = AsyncMock()
        repo = UserRepository(session=session, logger=MagicMock())
        await repo.update_mailbox(7, "kim@corp.com")
        stmt = session.execute.call_args.args[0]
        compiled = stmt.compile()
        assert "UPDATE users" in str(compiled)
        assert compiled.params["mailbox_upn"] == "kim@corp.com"
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_로그에_주소를_남기지_않는다(self):
        logger = MagicMock()
        repo = UserRepository(session=AsyncMock(), logger=logger)
        await repo.update_mailbox(7, "kim@corp.com")
        assert "kim@corp.com" not in str(logger.info.call_args_list)


class TestModelColumn:
    def test_nullable_255자이고_코멘트가_있다(self):
        column = UserModel.__table__.c.mailbox_upn
        assert column.nullable is True
        assert column.type.length == 255
        assert column.comment

    def test_모델_코멘트가_DDL과_같다(self):
        column = UserModel.__table__.c.mailbox_upn
        assert column.comment in _MIGRATION.read_text(encoding="utf-8")


class TestMigration:
    def test_nullable_컬럼을_추가한다(self):
        sql = _MIGRATION.read_text(encoding="utf-8")
        assert "ALTER TABLE users" in sql
        assert "ADD COLUMN mailbox_upn VARCHAR(255) NULL" in sql
