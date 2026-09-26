"""mcp_server_registry.identity_config_enc — 모델·매핑·DDL.

Design Ref: mcp-identity-header §3.3. 서명 비밀은 auth_config 와 다른 컬럼에
암호화 저장한다 (PUT 의 auth_config 통째 교체가 비밀을 지우지 않도록).
"""
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from src.domain.mcp_registry.identity import IdentityHeaderConfig
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.infrastructure.mcp_registry.mcp_server_repository import (
    _to_entity,
    _to_model,
)
from src.infrastructure.mcp_registry.models import MCPServerModel
from src.infrastructure.security.secret_cipher import SecretCipher

_NOW = datetime(2026, 9, 26)
_SECRET = "s" * 32
_MIGRATION = Path(
    "db/migration/V077__add_identity_config_to_mcp_server_registry.sql"
)


def _cipher() -> SecretCipher:
    return SecretCipher(SecretCipher.generate_key())


def _identity() -> IdentityHeaderConfig:
    return IdentityHeaderConfig.from_dict(
        {"audience": "mcp-outlook-server", "secret": _SECRET, "ttl_seconds": 120}
    )


def _entity(identity: IdentityHeaderConfig | None) -> MCPServerRegistration:
    return MCPServerRegistration(
        id="uuid-1", user_id="7", name="Outlook", description="d",
        endpoint="http://localhost:8006/sse", transport=MCPTransportType.SSE,
        input_schema=None, is_active=True, created_at=_NOW, updated_at=_NOW,
        auth_config={"headers": {"X-Static": "v"}},
        identity_config=identity,
    )


class TestMapping:
    def test_암호화해_저장하고_평문이_컬럼에_없다(self):
        model = _to_model(_entity(_identity()), _cipher())
        assert model.identity_config_enc
        assert _SECRET not in model.identity_config_enc
        assert "mcp-outlook-server" not in model.identity_config_enc

    def test_왕복하면_같은_설정(self):
        cipher = _cipher()
        entity = _to_entity(_to_model(_entity(_identity()), cipher), cipher)
        assert entity.identity_config == _identity()

    def test_auth_config와_독립된_컬럼(self):
        cipher = _cipher()
        model = _to_model(_entity(_identity()), cipher)
        assert cipher.decrypt_dict(model.auth_config_enc) == {
            "headers": {"X-Static": "v"}
        }
        assert "secret" not in cipher.decrypt_dict(model.auth_config_enc)

    def test_미설정이면_NULL(self):
        assert _to_model(_entity(None), _cipher()).identity_config_enc is None

    def test_NULL이면_None으로_읽는다(self):
        cipher = _cipher()
        model = _to_model(_entity(None), cipher)
        assert _to_entity(model, cipher).identity_config is None

    def test_cipher가_없으면_저장하지_않는다(self):
        """auth_config 와 같은 규칙 — 평문 저장 금지. 등록 검증이 선차단한다."""
        model = _to_model(_entity(_identity()), None)
        assert model.identity_config_enc is None

    def test_암호문이_있는데_cipher가_없으면_읽을_수_없음으로_표시(self):
        """Check G-3 — 키 누락을 '신원 미설정'으로 오인하면 헤더 없이 나간다."""
        model = _to_model(_entity(_identity()), _cipher())
        entity = _to_entity(model, None)
        assert entity.identity_config is None
        assert entity.identity_config_unreadable is True
        assert entity.requires_identity is True

    def test_컬럼_속성이_없는_구형_객체는_None(self):
        model = _to_model(_entity(None), None)
        del model.identity_config_enc
        entity = _to_entity(model, _cipher())
        assert entity.identity_config is None
        assert entity.identity_config_unreadable is False

    def test_손상된_설정은_로그를_남기고_None으로_읽는다(self):
        """목록 조회 전체가 깨지지 않게 격리한다. identity 모드 서버는
        헤더 없는 요청을 거부하므로 타인 자원 노출로 이어지지 않는다."""
        cipher = _cipher()
        model = _to_model(_entity(None), cipher)
        model.identity_config_enc = cipher.encrypt_dict({"audience": "x"})
        logger = MagicMock()
        entity = _to_entity(model, cipher, logger)
        assert entity.identity_config is None
        assert entity.identity_config_unreadable is True
        logger.error.assert_called_once()
        assert _SECRET not in str(logger.error.call_args)


class TestModelColumn:
    def test_nullable이고_코멘트가_있다(self):
        column = MCPServerModel.__table__.c.identity_config_enc
        assert column.nullable is True
        assert column.comment

    def test_모델_코멘트가_DDL과_같다(self):
        column = MCPServerModel.__table__.c.identity_config_enc
        assert column.comment in _MIGRATION.read_text(encoding="utf-8")


class TestMigration:
    def test_nullable_TEXT_컬럼을_추가한다(self):
        sql = _MIGRATION.read_text(encoding="utf-8")
        assert "ALTER TABLE mcp_server_registry" in sql
        assert "ADD COLUMN identity_config_enc TEXT NULL" in sql
