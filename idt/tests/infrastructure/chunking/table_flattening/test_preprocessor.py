"""Tests for TableFlatteningPreprocessor."""
import pytest

from src.domain.chunking.table_content_generator import (
    PreprocessResult,
    TableContentGenerator,
    TableConversionResult,
)
from src.infrastructure.chunking.table_flattening.preprocessor import (
    TableFlatteningPreprocessor,
)
from src.infrastructure.chunking.table_flattening.rule_based_generator import (
    RuleBasedTableContentGenerator,
)


class TestTableFlatteningPreprocessor:

    @pytest.fixture
    def preprocessor(self):
        generator = RuleBasedTableContentGenerator()
        return TableFlatteningPreprocessor(generator)

    def test_no_table_passthrough(self, preprocessor):
        text = "일반 텍스트입니다.\n\n두번째 문단입니다."
        result = preprocessor.process(text, "")

        assert result.parent_text == text
        assert result.child_text == text
        assert result.table_count == 0

    def test_single_table_detected(self, preprocessor):
        text = (
            "본문 내용.\n\n"
            "| 등급 | 금리 |\n"
            "|---|---|\n"
            "| A | 3.5% |\n"
            "\n후속 내용."
        )
        result = preprocessor.process(text, "대출 금리")

        assert result.table_count == 1
        assert "|" in result.parent_text
        assert "등급은(는) A" in result.child_text
        assert "3.5%" in result.child_text

    def test_multiple_tables_detected(self, preprocessor):
        text = (
            "첫 번째 표:\n\n"
            "| A | B |\n|---|---|\n| 1 | 2 |\n"
            "\n중간 텍스트.\n\n"
            "| C | D |\n|---|---|\n| 3 | 4 |\n"
        )
        result = preprocessor.process(text, "")

        assert result.table_count == 2

    def test_surrounding_text_preserved(self, preprocessor):
        text = (
            "앞 내용.\n\n"
            "| 항목 | 값 |\n|---|---|\n| X | 100 |\n"
            "\n뒤 내용."
        )
        result = preprocessor.process(text, "")

        assert "앞 내용." in result.parent_text
        assert "뒤 내용." in result.parent_text
        assert "앞 내용." in result.child_text
        assert "뒤 내용." in result.child_text

    def test_parent_text_unchanged(self, preprocessor):
        text = (
            "본문.\n\n"
            "| 항목 | 값 |\n|---|---|\n| X | 100 |\n"
        )
        result = preprocessor.process(text, "")

        assert result.parent_text == text

    def test_child_text_has_sentences_no_pipes(self, preprocessor):
        text = "| 항목 | 값 |\n|---|---|\n| X | 100 |\n"
        result = preprocessor.process(text, "")

        assert "|" not in result.child_text
        assert "항목은(는) X" in result.child_text

    def test_table_at_end_of_text(self, preprocessor):
        text = "본문.\n\n| 항목 | 값 |\n|---|---|\n| X | 100 |"
        result = preprocessor.process(text, "")

        assert result.table_count == 1

    def test_table_at_start_of_text(self, preprocessor):
        text = "| 항목 | 값 |\n|---|---|\n| X | 100 |\n\n후속 내용."
        result = preprocessor.process(text, "")

        assert result.table_count == 1
        assert "후속 내용." in result.child_text

    def test_non_table_pipe_lines_ignored(self, preprocessor):
        text = "파이프 | 기호가 | 있지만 표 아님\n일반 텍스트."
        result = preprocessor.process(text, "")

        assert result.table_count == 0

    def test_metadata_merged_for_multiple_tables(self, preprocessor):
        text = (
            "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
            "\n중간.\n\n"
            "| C | D |\n|---|---|\n| 5 | 6 |\n"
        )
        result = preprocessor.process(text, "")

        assert result.table_count == 2
        assert result.metadata.get("multi_table") is True
        assert result.metadata.get("total_row_count") == 3

    def test_result_is_preprocess_result(self, preprocessor):
        text = "일반 텍스트."
        result = preprocessor.process(text, "")

        assert isinstance(result, PreprocessResult)

    def test_custom_generator_used(self):
        """TableContentGenerator 인터페이스를 교체할 수 있는지 확인."""

        class MockGenerator(TableContentGenerator):
            def generate(self, table_markdown, section_title):
                return TableConversionResult(
                    original_markdown=table_markdown,
                    search_optimized_text="MOCK_RESULT",
                    metadata={"mock": True},
                )

        preprocessor = TableFlatteningPreprocessor(MockGenerator())
        text = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        result = preprocessor.process(text, "")

        assert "MOCK_RESULT" in result.child_text
