"""ToolIdFormatPolicy 단위 테스트 — mock 금지."""
import pytest

from src.domain.tool_catalog.policies import ToolIdFormatPolicy


class TestToolIdFormatPolicy:
    def test_internal_valid(self):
        ToolIdFormatPolicy.validate("internal:excel_export", "internal")

    def test_internal_valid_underscore(self):
        ToolIdFormatPolicy.validate("internal:tavily_search", "internal")

    def test_internal_invalid_uppercase_raises(self):
        with pytest.raises(ValueError, match="internal"):
            ToolIdFormatPolicy.validate("internal:ExcelExport", "internal")

    def test_internal_invalid_no_prefix_raises(self):
        with pytest.raises(ValueError, match="internal"):
            ToolIdFormatPolicy.validate("excel_export", "internal")

    def test_mcp_valid(self):
        ToolIdFormatPolicy.validate(
            "mcp:a1b2c3d4-e5f6-7890-abcd-ef1234567890:my_tool", "mcp"
        )

    def test_mcp_invalid_no_uuid_raises(self):
        with pytest.raises(ValueError, match="mcp"):
            ToolIdFormatPolicy.validate("mcp:not-a-uuid:tool", "mcp")

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown source"):
            ToolIdFormatPolicy.validate("foo:bar", "external")
