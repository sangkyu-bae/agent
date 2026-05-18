"""Tests for ElementExtractor."""
from unittest.mock import MagicMock, PropertyMock
import pytest

from src.domain.parser.document_element import BoundingBox, DocumentElement
from src.infrastructure.parser.layout.element_extractor import ElementExtractor


def _make_page_dict(blocks: list[dict]) -> dict:
    return {"blocks": blocks}


def _text_block(
    text: str,
    bbox: tuple = (10.0, 20.0, 200.0, 35.0),
    font_size: float = 10.0,
    font_name: str = "Arial",
) -> dict:
    return {
        "type": 0,
        "lines": [
            {
                "bbox": bbox,
                "spans": [
                    {
                        "text": text,
                        "size": font_size,
                        "font": font_name,
                    }
                ],
            }
        ],
    }


def _image_block() -> dict:
    return {"type": 1, "image": b"fake"}


class TestElementExtractor:
    """Tests for ElementExtractor.extract()."""

    def _mock_page(self, blocks: list[dict]) -> MagicMock:
        page = MagicMock()
        page.get_text.return_value = _make_page_dict(blocks)
        return page

    def test_extract_single_text_block(self) -> None:
        page = self._mock_page([_text_block("대출 금리 안내")])
        extractor = ElementExtractor()
        elements = extractor.extract(page, page_no=1)

        assert len(elements) == 1
        assert elements[0].text == "대출 금리 안내"
        assert elements[0].page_no == 1
        assert elements[0].block_type == "paragraph"

    def test_extract_preserves_bbox(self) -> None:
        page = self._mock_page([
            _text_block("텍스트", bbox=(50.0, 100.0, 300.0, 120.0))
        ])
        extractor = ElementExtractor()
        elements = extractor.extract(page, page_no=1)

        assert elements[0].bbox == BoundingBox(50.0, 100.0, 300.0, 120.0)

    def test_extract_preserves_font_size(self) -> None:
        page = self._mock_page([_text_block("제목", font_size=16.0)])
        extractor = ElementExtractor()
        elements = extractor.extract(page, page_no=1)

        assert elements[0].font_size == 16.0

    def test_extract_detects_bold(self) -> None:
        page = self._mock_page([
            _text_block("굵은 텍스트", font_name="Arial-Bold")
        ])
        extractor = ElementExtractor()
        elements = extractor.extract(page, page_no=1)

        assert elements[0].is_bold is True

    def test_extract_non_bold(self) -> None:
        page = self._mock_page([
            _text_block("일반 텍스트", font_name="Arial")
        ])
        extractor = ElementExtractor()
        elements = extractor.extract(page, page_no=1)

        assert elements[0].is_bold is False

    def test_skip_empty_text_lines(self) -> None:
        block = {
            "type": 0,
            "lines": [
                {"bbox": (0, 0, 100, 20), "spans": [{"text": "   ", "size": 10.0, "font": "Arial"}]},
                {"bbox": (0, 25, 100, 45), "spans": [{"text": "유효 텍스트", "size": 10.0, "font": "Arial"}]},
            ],
        }
        page = self._mock_page([block])
        extractor = ElementExtractor()
        elements = extractor.extract(page, page_no=1)

        assert len(elements) == 1
        assert elements[0].text == "유효 텍스트"

    def test_skip_image_blocks(self) -> None:
        page = self._mock_page([_image_block(), _text_block("텍스트")])
        extractor = ElementExtractor()
        elements = extractor.extract(page, page_no=1)

        assert len(elements) == 1
        assert elements[0].text == "텍스트"

    def test_multiple_blocks(self) -> None:
        page = self._mock_page([
            _text_block("첫번째"),
            _text_block("두번째"),
            _text_block("세번째"),
        ])
        extractor = ElementExtractor()
        elements = extractor.extract(page, page_no=2)

        assert len(elements) == 3
        assert all(e.page_no == 2 for e in elements)

    def test_extract_returns_empty_on_exception(self) -> None:
        page = MagicMock()
        page.get_text.side_effect = RuntimeError("corrupted page")
        extractor = ElementExtractor()
        elements = extractor.extract(page, page_no=1)

        assert elements == []

    def test_multi_span_line(self) -> None:
        block = {
            "type": 0,
            "lines": [
                {
                    "bbox": (10, 20, 300, 35),
                    "spans": [
                        {"text": "금리: ", "size": 10.0, "font": "Arial"},
                        {"text": "3.5%", "size": 10.0, "font": "Arial-Bold"},
                    ],
                }
            ],
        }
        page = self._mock_page([block])
        extractor = ElementExtractor()
        elements = extractor.extract(page, page_no=1)

        assert len(elements) == 1
        assert elements[0].text == "금리: 3.5%"
        assert elements[0].is_bold is True


class TestElementExtractorTables:
    """Tests for ElementExtractor.extract_tables()."""

    _DEFAULT_ROWS = [["A", "B"], ["1", "2"]]
    _DEFAULT_HEADERS = ["ColA", "ColB"]

    def _mock_table(
        self,
        bbox: tuple = (10.0, 100.0, 500.0, 300.0),
        rows: list[list] | None = None,
        header_names: list[str] | None = None,
        empty: bool = False,
    ) -> MagicMock:
        table = MagicMock()
        table.bbox = bbox
        table.extract.return_value = [] if empty else (rows if rows is not None else self._DEFAULT_ROWS)
        header = MagicMock()
        header.names = header_names if header_names is not None else self._DEFAULT_HEADERS
        table.header = header
        return table

    def _mock_page_with_tables(
        self, tables: list[MagicMock]
    ) -> MagicMock:
        page = MagicMock()
        page.find_tables.return_value = tables
        return page

    def test_extract_single_table(self) -> None:
        table = self._mock_table()
        page = self._mock_page_with_tables([table])
        extractor = ElementExtractor()
        elements = extractor.extract_tables(page, page_no=1)

        assert len(elements) == 1
        assert elements[0].block_type == "table"
        assert "ColA" in elements[0].text
        assert "ColB" in elements[0].text

    def test_table_bbox_preserved(self) -> None:
        table = self._mock_table(bbox=(20.0, 50.0, 400.0, 250.0))
        page = self._mock_page_with_tables([table])
        extractor = ElementExtractor()
        elements = extractor.extract_tables(page, page_no=1)

        assert elements[0].bbox == BoundingBox(20.0, 50.0, 400.0, 250.0)

    def test_empty_table_skipped(self) -> None:
        table = self._mock_table(empty=True)
        page = self._mock_page_with_tables([table])
        extractor = ElementExtractor()
        elements = extractor.extract_tables(page, page_no=1)

        assert elements == []

    def test_table_generates_markdown(self) -> None:
        table = self._mock_table(
            header_names=["등급", "금리"],
            rows=[["A", "3.5%"], ["B", "4.0%"]],
        )
        page = self._mock_page_with_tables([table])
        extractor = ElementExtractor()
        elements = extractor.extract_tables(page, page_no=1)

        text = elements[0].text
        assert "| 등급 | 금리 |" in text
        assert "| A | 3.5% |" in text
        assert "| B | 4.0% |" in text

    def test_extract_tables_returns_empty_on_exception(self) -> None:
        page = MagicMock()
        page.find_tables.side_effect = RuntimeError("no tables support")
        extractor = ElementExtractor()
        elements = extractor.extract_tables(page, page_no=1)

        assert elements == []
