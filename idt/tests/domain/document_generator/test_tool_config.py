"""DocumentGeneratorToolConfig 테스트 (Design §4-2)."""
import pytest

from src.domain.document_generator.tool_config import DocumentGeneratorToolConfig


class TestDocumentGeneratorToolConfig:
    def test_valid_config(self):
        config = DocumentGeneratorToolConfig(
            type_id="t-1",
            mcp_html_to_doc_tool_id="mcp_abc",
            output_format="docx",
        )
        assert config.type_id == "t-1"

    def test_empty_type_id_rejected(self):
        with pytest.raises(ValueError):
            DocumentGeneratorToolConfig(
                type_id="", mcp_html_to_doc_tool_id="mcp_abc", output_format="docx"
            )

    def test_empty_mcp_tool_id_allowed_for_settings_fallback(self):
        """D5: 빈 값 허용 — 런타임에 settings 폴백 체인으로 해석."""
        config = DocumentGeneratorToolConfig(
            type_id="t-1", mcp_html_to_doc_tool_id="", output_format="pdf"
        )
        assert config.mcp_html_to_doc_tool_id == ""

    def test_non_mcp_prefix_rejected(self):
        with pytest.raises(ValueError):
            DocumentGeneratorToolConfig(
                type_id="t-1",
                mcp_html_to_doc_tool_id="internal:doc",
                output_format="docx",
            )

    @pytest.mark.parametrize("fmt", ["", "hwp", "PDF"])
    def test_invalid_output_format_rejected(self, fmt):
        with pytest.raises(ValueError):
            DocumentGeneratorToolConfig(
                type_id="t-1", mcp_html_to_doc_tool_id="mcp_abc", output_format=fmt
            )

    def test_model_dump_roundtrip(self):
        config = DocumentGeneratorToolConfig(
            type_id="t-1", mcp_html_to_doc_tool_id="mcp_abc", output_format="docx"
        )
        dumped = config.model_dump()
        assert dumped == {
            "type_id": "t-1",
            "mcp_html_to_doc_tool_id": "mcp_abc",
            "output_format": "docx",
        }
        assert DocumentGeneratorToolConfig(**dumped) == config
