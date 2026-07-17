"""ExtensionRoutingParser — 확장자 기반 파서 위임 (kb-excel-upload D3)."""
from unittest.mock import MagicMock

import pytest

from src.domain.parser.exceptions import UnsupportedFileFormatError
from src.infrastructure.parser.extension_routing_parser import (
    ExtensionRoutingParser,
)


@pytest.fixture
def pdf_parser() -> MagicMock:
    parser = MagicMock()
    parser.parse_bytes.return_value = ["pdf-doc"]
    parser.parse.return_value = ["pdf-doc"]
    parser.supports_ocr.return_value = False
    return parser


@pytest.fixture
def excel_parser() -> MagicMock:
    parser = MagicMock()
    parser.parse_bytes.return_value = ["excel-doc"]
    parser.parse.return_value = ["excel-doc"]
    return parser


@pytest.fixture
def router(pdf_parser: MagicMock, excel_parser: MagicMock) -> ExtensionRoutingParser:
    return ExtensionRoutingParser(pdf_parser=pdf_parser, excel_parser=excel_parser)


class TestParseBytesRouting:
    def test_pdf_delegates_to_pdf_parser(self, router, pdf_parser, excel_parser):
        result = router.parse_bytes(b"data", "doc.pdf", "u1")
        assert result == ["pdf-doc"]
        pdf_parser.parse_bytes.assert_called_once()
        excel_parser.parse_bytes.assert_not_called()

    def test_xlsx_delegates_to_excel_parser(self, router, pdf_parser, excel_parser):
        result = router.parse_bytes(b"data", "표.xlsx", "u1")
        assert result == ["excel-doc"]
        excel_parser.parse_bytes.assert_called_once()
        pdf_parser.parse_bytes.assert_not_called()

    def test_xls_delegates_to_excel_parser(self, router, excel_parser):
        router.parse_bytes(b"data", "legacy.xls", "u1")
        excel_parser.parse_bytes.assert_called_once()

    def test_uppercase_extension_routes(self, router, excel_parser):
        router.parse_bytes(b"data", "DATA.XLSX", "u1")
        excel_parser.parse_bytes.assert_called_once()

    def test_unsupported_extension_raises_before_parsing(
        self, router, pdf_parser, excel_parser
    ):
        with pytest.raises(UnsupportedFileFormatError, match=r"\.docx"):
            router.parse_bytes(b"data", "doc.docx", "u1")
        pdf_parser.parse_bytes.assert_not_called()
        excel_parser.parse_bytes.assert_not_called()


class TestParseFilePathRouting:
    def test_routes_by_basename(self, router, excel_parser):
        router.parse("C:/tmp/데이터.xlsx", "u1")
        excel_parser.parse.assert_called_once()

    def test_unsupported_raises(self, router):
        with pytest.raises(UnsupportedFileFormatError):
            router.parse("C:/tmp/note.txt", "u1")


class TestInterfaceContract:
    def test_parser_name(self, router):
        assert router.get_parser_name() == "extension_routing"

    def test_supports_ocr_delegates_to_pdf(self, router, pdf_parser):
        pdf_parser.supports_ocr.return_value = True
        assert router.supports_ocr() is True
        pdf_parser.supports_ocr.assert_called_once()
