"""Tests for RuleBasedTableContentGenerator."""
import pytest

from src.domain.chunking.table_content_generator import (
    TableContentGenerator,
    TableConversionResult,
)
from src.infrastructure.chunking.table_flattening.rule_based_generator import (
    RuleBasedTableContentGenerator,
)


class TestRuleBasedTableContentGenerator:

    @pytest.fixture
    def generator(self):
        return RuleBasedTableContentGenerator()

    def test_implements_interface(self, generator):
        assert isinstance(generator, TableContentGenerator)

    def test_generate_simple_table(self, generator):
        table_md = (
            "| 등급 | 금리 |\n"
            "|---|---|\n"
            "| A | 3.5% |\n"
            "| B | 4.2% |\n"
        )
        result = generator.generate(table_md, "대출 금리")

        assert isinstance(result, TableConversionResult)
        assert "A" in result.search_optimized_text
        assert "3.5%" in result.search_optimized_text
        assert "B" in result.search_optimized_text
        assert "|" not in result.search_optimized_text

    def test_generate_with_section_title(self, generator):
        table_md = "| 항목 | 값 |\n|---|---|\n| X | 100 |\n"
        result = generator.generate(table_md, "수수료 안내")

        assert result.search_optimized_text.startswith("수수료 안내에서 ")

    def test_generate_without_section_title(self, generator):
        table_md = "| 항목 | 값 |\n|---|---|\n| X | 100 |\n"
        result = generator.generate(table_md, "")

        assert not result.search_optimized_text.startswith("에서 ")

    def test_generate_numeric_data_detected(self, generator):
        table_md = "| 항목 | 값 |\n|---|---|\n| 금리 | 3.5% |\n"
        result = generator.generate(table_md, "")

        assert result.metadata["has_numeric_data"] is True

    def test_generate_non_numeric_data(self, generator):
        table_md = "| 이름 | 설명 |\n|---|---|\n| 상품A | 일반 대출 |\n"
        result = generator.generate(table_md, "")

        assert result.metadata["has_numeric_data"] is False

    def test_generate_empty_cells_skipped(self, generator):
        table_md = "| 항목 | 값 | 비고 |\n|---|---|---|\n| X | 100 |  |\n"
        result = generator.generate(table_md, "")

        assert "비고" not in result.search_optimized_text

    def test_generate_header_only_table(self, generator):
        table_md = "| 항목 | 값 |\n|---|---|\n"
        result = generator.generate(table_md, "")

        assert result.search_optimized_text == table_md
        assert result.metadata.get("parse_failed") is True

    def test_generate_mismatched_columns_skipped(self, generator):
        table_md = (
            "| 항목 | 값 |\n"
            "|---|---|\n"
            "| A | 1 | extra |\n"
            "| B | 2 |\n"
        )
        result = generator.generate(table_md, "")

        assert "B" in result.search_optimized_text
        assert "A" not in result.search_optimized_text

    def test_generate_preserves_original(self, generator):
        table_md = "| 항목 | 값 |\n|---|---|\n| X | 100 |\n"
        result = generator.generate(table_md, "")

        assert result.original_markdown == table_md

    def test_metadata_has_columns_and_row_count(self, generator):
        table_md = (
            "| 등급 | 금리 | 한도 |\n"
            "|---|---|---|\n"
            "| A | 3.5% | 1억 |\n"
            "| B | 4.2% | 5천 |\n"
        )
        result = generator.generate(table_md, "")

        assert result.metadata["columns"] == ["등급", "금리", "한도"]
        assert result.metadata["row_count"] == 2
