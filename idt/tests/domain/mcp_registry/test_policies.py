"""Domain 테스트: MCPRegistrationPolicy."""
import pytest

from src.domain.mcp_registry.policies import MCPRegistrationPolicy


class TestValidateEndpoint:

    def test_accepts_https_url(self):
        assert MCPRegistrationPolicy.validate_endpoint("https://mcp.example.com/sse") is True

    def test_accepts_http_url(self):
        assert MCPRegistrationPolicy.validate_endpoint("http://localhost:8080/sse") is True

    def test_rejects_empty_string(self):
        assert MCPRegistrationPolicy.validate_endpoint("") is False

    def test_rejects_ftp_scheme(self):
        assert MCPRegistrationPolicy.validate_endpoint("ftp://mcp.example.com/sse") is False

    def test_rejects_no_netloc(self):
        assert MCPRegistrationPolicy.validate_endpoint("https:///sse") is False

    def test_rejects_too_long(self):
        long_url = "https://" + "a" * 600 + ".com/sse"
        assert MCPRegistrationPolicy.validate_endpoint(long_url) is False


class TestValidateName:

    def test_accepts_valid_name(self):
        assert MCPRegistrationPolicy.validate_name("My MCP Tool") is True

    def test_rejects_empty_string(self):
        assert MCPRegistrationPolicy.validate_name("") is False

    def test_rejects_whitespace_only(self):
        assert MCPRegistrationPolicy.validate_name("   ") is False

    def test_rejects_too_long(self):
        assert MCPRegistrationPolicy.validate_name("a" * 256) is False

    def test_accepts_max_length(self):
        assert MCPRegistrationPolicy.validate_name("a" * 255) is True


class TestValidateDescription:

    def test_accepts_valid_description(self):
        assert MCPRegistrationPolicy.validate_description("Does something useful") is True

    def test_rejects_empty_string(self):
        assert MCPRegistrationPolicy.validate_description("") is False

    def test_rejects_whitespace_only(self):
        assert MCPRegistrationPolicy.validate_description("  ") is False

    def test_rejects_too_long(self):
        assert MCPRegistrationPolicy.validate_description("a" * 2001) is False
