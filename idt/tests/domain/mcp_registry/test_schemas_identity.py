"""MCPServerRegistration.identity_config — 엔티티 필드.

Design Ref: mcp-identity-header §3.1. 미설정 서버는 기존과 동일해야 한다 (FR-08).
"""
from datetime import datetime

from src.domain.mcp_registry.identity import IdentityHeaderConfig
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType

_NOW = datetime(2026, 9, 26)
_SECRET = "s" * 32


def _reg(identity: IdentityHeaderConfig | None = None) -> MCPServerRegistration:
    return MCPServerRegistration(
        id="uuid-1", user_id="7", name="Outlook", description="d",
        endpoint="http://localhost:8006/sse", transport=MCPTransportType.SSE,
        input_schema=None, is_active=True, created_at=_NOW, updated_at=_NOW,
        identity_config=identity,
    )


def _identity() -> IdentityHeaderConfig:
    return IdentityHeaderConfig.from_dict(
        {"audience": "mcp-outlook-server", "secret": _SECRET}
    )


class TestIdentityField:
    def test_기본값은_None이고_신원_불필요(self):
        reg = MCPServerRegistration(
            id="uuid-1", user_id="7", name="n", description="d",
            endpoint="http://x/sse", transport=MCPTransportType.SSE,
            input_schema=None, is_active=True, created_at=_NOW, updated_at=_NOW,
        )
        assert reg.identity_config is None
        assert reg.requires_identity is False

    def test_설정이_있으면_신원_필요(self):
        assert _reg(_identity()).requires_identity is True

    def test_masked_identity는_secret을_가린다(self):
        masked = _reg(_identity()).masked_identity()
        assert masked is not None
        assert masked["secret"] == "****"
        assert masked["audience"] == "mcp-outlook-server"

    def test_masked_identity는_미설정이면_None(self):
        assert _reg().masked_identity() is None
