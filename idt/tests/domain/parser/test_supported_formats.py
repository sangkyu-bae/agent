"""supported_formats — 확장자→포맷 판정 단일 진실원 (kb-excel-upload D1)."""
from src.domain.parser.supported_formats import (
    FORMAT_EXCEL,
    FORMAT_PDF,
    resolve_format,
    supported_formats_display,
)


class TestResolveFormat:
    def test_pdf(self):
        assert resolve_format("doc.pdf") == FORMAT_PDF

    def test_xlsx(self):
        assert resolve_format("data.xlsx") == FORMAT_EXCEL

    def test_xls(self):
        assert resolve_format("legacy.xls") == FORMAT_EXCEL

    def test_uppercase_extension(self):
        assert resolve_format("DATA.XLSX") == FORMAT_EXCEL

    def test_korean_filename(self):
        assert resolve_format("여신한도표.xlsx") == FORMAT_EXCEL

    def test_unsupported_returns_none(self):
        assert resolve_format("doc.docx") is None

    def test_no_extension_returns_none(self):
        assert resolve_format("README") is None

    def test_multi_dot_uses_last_suffix(self):
        assert resolve_format("backup.pdf.xlsx") == FORMAT_EXCEL


class TestSupportedFormatsDisplay:
    def test_lists_all_extensions(self):
        display = supported_formats_display()
        assert "pdf" in display
        assert "xlsx" in display
        assert "xls" in display
