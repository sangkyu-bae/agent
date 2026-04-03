"""Infrastructure tests for xhtml2pdf HTML→PDF converter.

Uses mocking for the external xhtml2pdf library.
"""
import io
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.pdf_export.weasyprint_converter import WeasyprintConverter


class TestWeasyprintConverter:
    def test_get_converter_name_returns_xhtml2pdf(self):
        converter = WeasyprintConverter()
        assert converter.get_converter_name() == "xhtml2pdf"

    def test_convert_calls_pisa_with_html_content(self):
        fake_pdf = b"%PDF-1.4 fake"
        mock_result = MagicMock()
        mock_result.err = 0

        with patch(
            "src.infrastructure.pdf_export.weasyprint_converter.pisa.CreatePDF",
            return_value=mock_result,
        ) as mock_pisa:
            # BytesIO를 통해 결과 bytes 반환하도록 설정
            def side_effect(src, dest, **kwargs):
                dest.write(fake_pdf)
                return mock_result

            mock_pisa.side_effect = side_effect

            converter = WeasyprintConverter()
            result = converter.convert("<h1>Hello</h1>")

        mock_pisa.assert_called_once()
        assert result == fake_pdf

    def test_convert_prepends_css_style_tag_when_css_provided(self):
        fake_pdf = b"%PDF-1.4 fake"
        mock_result = MagicMock()
        mock_result.err = 0
        captured_html = []

        def side_effect(src, dest, **kwargs):
            captured_html.append(src.read())
            dest.write(fake_pdf)
            return mock_result

        with patch(
            "src.infrastructure.pdf_export.weasyprint_converter.pisa.CreatePDF",
            side_effect=side_effect,
        ):
            converter = WeasyprintConverter()
            converter.convert(
                "<h1>Hi</h1>", css_content="body { font-size: 12pt; }"
            )

        assert "<style>body { font-size: 12pt; }</style>" in captured_html[0]
        assert "<h1>Hi</h1>" in captured_html[0]

    def test_convert_passes_base_url_as_path(self):
        mock_result = MagicMock()
        mock_result.err = 0
        captured_kwargs = []

        def side_effect(src, dest, **kwargs):
            captured_kwargs.append(kwargs)
            dest.write(b"fake")
            return mock_result

        with patch(
            "src.infrastructure.pdf_export.weasyprint_converter.pisa.CreatePDF",
            side_effect=side_effect,
        ):
            converter = WeasyprintConverter()
            converter.convert("<h1>Hi</h1>", base_url="https://example.com")

        assert captured_kwargs[0]["path"] == "https://example.com"

    def test_convert_raises_value_error_on_empty_html(self):
        converter = WeasyprintConverter()
        with pytest.raises(ValueError, match="html_content must not be empty"):
            converter.convert("   ")

    def test_convert_raises_runtime_error_on_pisa_error(self):
        mock_result = MagicMock()
        mock_result.err = 1  # 오류 코드

        with patch(
            "src.infrastructure.pdf_export.weasyprint_converter.pisa.CreatePDF",
            return_value=mock_result,
        ):
            converter = WeasyprintConverter()
            with pytest.raises(RuntimeError, match="xhtml2pdf 변환 오류"):
                converter.convert("<h1>Hello</h1>")

    def test_convert_raises_runtime_error_on_exception(self):
        with patch(
            "src.infrastructure.pdf_export.weasyprint_converter.pisa.CreatePDF",
            side_effect=Exception("unexpected crash"),
        ):
            converter = WeasyprintConverter()
            with pytest.raises(RuntimeError, match="PDF 변환 중 오류가 발생했습니다"):
                converter.convert("<h1>Hello</h1>")
