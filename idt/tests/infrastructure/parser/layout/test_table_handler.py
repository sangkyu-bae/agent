"""Tests for TableHandler."""
import pytest

from src.domain.parser.document_element import BoundingBox, DocumentElement
from src.infrastructure.parser.layout.table_handler import (
    TableHandler,
    TableResult,
)


def _table_elem(md_text: str) -> DocumentElement:
    return DocumentElement(
        page_no=1,
        text=md_text,
        bbox=BoundingBox(10.0, 100.0, 500.0, 300.0),
        block_type="table",
    )


SAMPLE_TABLE = (
    "| 등급 | 금리 | 한도 |\n"
    "| --- | --- | --- |\n"
    "| A | 3.5% | 1억원 |\n"
    "| B | 4.0% | 5000만원 |"
)


class TestTableHandler:

    def test_process_normal_table(self) -> None:
        handler = TableHandler()
        result = handler.process_table_element(
            _table_elem(SAMPLE_TABLE), section_title="대출 금리"
        )

        assert result.markdown == SAMPLE_TABLE
        assert len(result.semantic_sentences) == 2
        assert result.metadata["row_count"] == 2
        assert result.metadata["columns"] == ["등급", "금리", "한도"]

    def test_semantic_sentences_with_section_title(self) -> None:
        handler = TableHandler()
        result = handler.process_table_element(
            _table_elem(SAMPLE_TABLE), section_title="대출 금리"
        )

        assert "대출 금리에서" in result.semantic_sentences[0]
        assert "등급은(는) A" in result.semantic_sentences[0]
        assert "금리은(는) 3.5%" in result.semantic_sentences[0]

    def test_semantic_sentences_without_section_title(self) -> None:
        handler = TableHandler()
        result = handler.process_table_element(
            _table_elem(SAMPLE_TABLE), section_title=""
        )

        assert not result.semantic_sentences[0].startswith("에서")

    def test_empty_table(self) -> None:
        handler = TableHandler()
        result = handler.process_table_element(
            _table_elem(""), section_title="섹션"
        )

        assert result.semantic_sentences == []

    def test_header_only_table(self) -> None:
        md = "| 컬럼A | 컬럼B |\n| --- | --- |"
        handler = TableHandler()
        result = handler.process_table_element(
            _table_elem(md), section_title=""
        )

        assert result.semantic_sentences == []

    def test_has_numeric_data_true(self) -> None:
        handler = TableHandler()
        result = handler.process_table_element(
            _table_elem(SAMPLE_TABLE), section_title=""
        )

        assert result.metadata["has_numeric_data"] is True

    def test_has_numeric_data_false(self) -> None:
        md = "| 이름 | 부서 |\n| --- | --- |\n| 홍길동 | 개발팀 |"
        handler = TableHandler()
        result = handler.process_table_element(
            _table_elem(md), section_title=""
        )

        assert result.metadata["has_numeric_data"] is False

    def test_mismatched_column_count_skipped(self) -> None:
        md = "| A | B |\n| --- | --- |\n| 1 | 2 | 3 |"
        handler = TableHandler()
        result = handler.process_table_element(
            _table_elem(md), section_title=""
        )

        assert result.semantic_sentences == []

    def test_empty_cells_excluded_from_sentence(self) -> None:
        md = "| 항목 | 값 |\n| --- | --- |\n| 이름 |  |"
        handler = TableHandler()
        result = handler.process_table_element(
            _table_elem(md), section_title=""
        )

        assert len(result.semantic_sentences) == 1
        assert "값은(는)" not in result.semantic_sentences[0]
