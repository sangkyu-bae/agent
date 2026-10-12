"""supported_formats — 확장자→포맷 판정 단일 진실원 (kb-excel-upload D1)."""
from src.domain.parser.supported_formats import (
    FORMAT_EXCEL,
    FORMAT_HWP,
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


class TestResolveHwpFormat:
    # hwp-parser Design §8 U-01
    def test_hwp(self):
        assert resolve_format("공문.hwp") == FORMAT_HWP

    def test_hwpx_uppercase(self):
        assert resolve_format("공문.HWPX") == FORMAT_HWP

    def test_windows_path(self):
        assert resolve_format(r"C:\a\b.hwpx") == FORMAT_HWP


class TestSupportedFormatsDisplay:
    def test_lists_all_extensions(self):
        display = supported_formats_display()
        assert "pdf" in display
        assert "xlsx" in display
        assert "xls" in display
        assert "hwp" in display
        assert "hwpx" in display
