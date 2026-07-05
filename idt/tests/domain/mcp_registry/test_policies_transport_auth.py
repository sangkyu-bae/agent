"""Domain 테스트: transport/auth 정책 + 시크릿 마스킹."""
from datetime import datetime

from src.domain.mcp_registry.policies import MCPRegistrationPolicy
from src.domain.mcp_registry.schemas import (
    MCPServerRegistration,
    MCPTransportType,
    mask_secrets,
)


class TestValidateTransport:

    def test_sse_allowed(self):
        assert MCPRegistrationPolicy.validate_transport("sse") is True

    def test_streamable_http_allowed(self):
        assert MCPRegistrationPolicy.validate_transport("streamable_http") is True

    def test_unknown_rejected(self):
        assert MCPRegistrationPolicy.validate_transport("websocket") is False
        assert MCPRegistrationPolicy.validate_transport("") is False


class TestValidateAuth:

    def test_sse_needs_no_auth(self):
        assert MCPRegistrationPolicy.validate_auth("sse", None) is True

    def test_streamable_http_requires_api_key(self):
        assert MCPRegistrationPolicy.validate_auth("streamable_http", None) is False
        assert MCPRegistrationPolicy.validate_auth("streamable_http", {}) is False
        assert (
            MCPRegistrationPolicy.validate_auth("streamable_http", {"api_key": "  "})
            is False
        )

    def test_streamable_http_with_api_key_ok(self):
        assert (
            MCPRegistrationPolicy.validate_auth("streamable_http", {"api_key": "K"})
            is True
        )


class TestRequiresSecretStorage:

    def test_streamable_http_requires_secret_storage(self):
        assert (
            MCPRegistrationPolicy.requires_secret_storage("streamable_http") is True
        )

    def test_sse_does_not_require_secret_storage(self):
        assert MCPRegistrationPolicy.requires_secret_storage("sse") is False


class TestMaskSecrets:

    def test_mask_values_keep_keys(self):
        assert mask_secrets({"api_key": "secret", "profile": "p"}) == {
            "api_key": "****",
            "profile": "****",
        }

    def test_mask_none(self):
        assert mask_secrets(None) is None

    def test_mask_nested(self):
        masked = mask_secrets({"headers": {"Authorization": "Bearer t"}})
        assert masked == {"headers": {"Authorization": "****"}}


class TestRegistrationMasking:

    def _reg(self, **kw):
        base = dict(
            id="i", user_id="u", name="n", description="d",
            endpoint="https://e/mcp", transport=MCPTransportType.STREAMABLE_HTTP,
            input_schema=None, is_active=True,
            created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
        )
        base.update(kw)
        return MCPServerRegistration(**base)

    def test_masked_auth_and_server_config(self):
        reg = self._reg(
            auth_config={"api_key": "K", "profile": "P"},
            server_config={"NAVER_CLIENT_ID": "id"},
        )
        assert reg.masked_auth() == {"api_key": "****", "profile": "****"}
        assert reg.masked_server_config() == {"NAVER_CLIENT_ID": "****"}

    def test_masked_none_when_absent(self):
        reg = self._reg()
        assert reg.masked_auth() is None
        assert reg.masked_server_config() is None
