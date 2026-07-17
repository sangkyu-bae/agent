"""ExcelDocumentParserAdapter — ExcelData→List[Document] 변환 (kb-excel-upload D4/D6)."""
from unittest.mock import MagicMock

import pytest

from src.domain.excel.entities.excel_data import ExcelData
from src.domain.excel.entities.sheet_data import SheetData
from src.domain.excel.value_objects.excel_metadata import ExcelMetadata
from src.infrastructure.excel.excel_document_parser_adapter import (
    ExcelDocumentParserAdapter,
)

MAX_ROWS = 100


def _excel_data(sheets: dict) -> ExcelData:
    return ExcelData(
        file_id="file-1",
        filename="한도표.xlsx",
        sheets=sheets,
        metadata=ExcelMetadata(
            file_id="file-1",
            filename="한도표.xlsx",
            sheet_names=list(sheets.keys()),
            total_rows=sum(s.row_count for s in sheets.values()),
            user_id="u1",
        ),
    )


def _sheet(name: str, rows: list, columns: list) -> SheetData:
    return SheetData(sheet_name=name, data=rows, columns=columns)


@pytest.fixture
def mock_excel_parser() -> MagicMock:
    parser = MagicMock()
    parser.parse_bytes.return_value = _excel_data(
        {
            "요율": _sheet("요율", [{"등급": "A", "요율": 3.5}], ["등급", "요율"]),
            "한도": _sheet("한도", [{"상품": "주담대"}], ["상품"]),
        }
    )
    return parser


@pytest.fixture
def adapter(mock_excel_parser: MagicMock) -> ExcelDocumentParserAdapter:
    return ExcelDocumentParserAdapter(
        excel_parser=mock_excel_parser, max_rows_per_sheet=MAX_ROWS
    )


class TestParseBytes:
    def test_one_document_per_sheet(self, adapter):
        docs = adapter.parse_bytes(b"xlsx", "한도표.xlsx", "u1")
        assert len(docs) == 2
        assert docs[0].page_content == "등급: A | 요율: 3.5"
        assert docs[1].page_content == "상품: 주담대"

    def test_metadata_mirrors_pdf_contract(self, adapter):
        # page/total_pages/parser/document_id 키는 다운스트림 계약 (D4)
        docs = adapter.parse_bytes(b"xlsx", "한도표.xlsx", "u1")
        first = docs[0].metadata
        assert first["filename"] == "한도표.xlsx"
        assert first["user_id"] == "u1"
        assert first["page"] == 1
        assert first["total_pages"] == 2
        assert first["parser"] == "pandas_excel"
        assert first["sheet_name"] == "요율"
        assert first["row_count"] == 1
        assert docs[1].metadata["page"] == 2
        # 같은 파일의 시트는 같은 document_id를 공유
        assert first["document_id"] == docs[1].metadata["document_id"]

    def test_empty_sheet_is_skipped(self, adapter, mock_excel_parser):
        mock_excel_parser.parse_bytes.return_value = _excel_data(
            {
                "빈시트": _sheet("빈시트", [], ["a"]),
                "데이터": _sheet("데이터", [{"a": 1}], ["a"]),
            }
        )
        docs = adapter.parse_bytes(b"xlsx", "한도표.xlsx", "u1")
        assert len(docs) == 1
        assert docs[0].metadata["sheet_name"] == "데이터"
        assert docs[0].metadata["total_pages"] == 1

    def test_all_sheets_empty_raises(self, adapter, mock_excel_parser):
        mock_excel_parser.parse_bytes.return_value = _excel_data(
            {"빈시트": _sheet("빈시트", [], ["a"])}
        )
        with pytest.raises(ValueError, match="No parsable sheet"):
            adapter.parse_bytes(b"xlsx", "한도표.xlsx", "u1")

    def test_row_limit_exceeded_raises_with_sheet_name(
        self, adapter, mock_excel_parser
    ):
        big_rows = [{"a": i} for i in range(MAX_ROWS + 1)]
        mock_excel_parser.parse_bytes.return_value = _excel_data(
            {"대량": _sheet("대량", big_rows, ["a"])}
        )
        with pytest.raises(ValueError) as exc_info:
            adapter.parse_bytes(b"xlsx", "한도표.xlsx", "u1")
        msg = str(exc_info.value)
        assert "대량" in msg
        assert str(MAX_ROWS) in msg


class TestInterfaceContract:
    def test_parser_name(self, adapter):
        assert adapter.get_parser_name() == "pandas_excel"

    def test_no_ocr(self, adapter):
        assert adapter.supports_ocr() is False
