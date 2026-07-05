"""DocumentExtractorToolConfig 검증 테스트 (Design §2-3)."""
import pytest

from src.domain.document_extractor.tool_config import DocumentExtractorToolConfig


def _config(**kwargs) -> DocumentExtractorToolConfig:
    base = dict(
        template_id="tpl-1",
        mcp_pdf_to_html_tool_id="mcp_abc",
        mcp_html_to_doc_tool_id="mcp_def",
        output_format="pdf",
    )
    base.update(kwargs)
    return DocumentExtractorToolConfig(**base)


class TestDocumentExtractorToolConfig:
    def test_valid_config(self):
        config = _config()
        assert config.template_id == "tpl-1"
        assert config.output_format == "pdf"

    def test_docx_output_format_allowed(self):
        assert _config(output_format="docx").output_format == "docx"

    def test_empty_template_id_rejected(self):
        with pytest.raises(ValueError):
            _config(template_id="")

    @pytest.mark.parametrize(
        "field", ["mcp_pdf_to_html_tool_id", "mcp_html_to_doc_tool_id"]
    )
    def test_mcp_prefix_required(self, field):
        with pytest.raises(ValueError):
            _config(**{field: "not_mcp_id"})

    def test_invalid_output_format_rejected(self):
        with pytest.raises(ValueError):
            _config(output_format="hwp")

    def test_frozen(self):
        with pytest.raises(AttributeError):
            _config().template_id = "x"
