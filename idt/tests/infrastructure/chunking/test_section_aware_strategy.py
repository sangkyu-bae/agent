"""Tests for SectionAwareChunkingStrategy."""
import pytest

from langchain_core.documents import Document

from src.domain.chunking.value_objects import ChunkingConfig
from src.infrastructure.chunking.strategies.section_aware_strategy import (
    SectionAwareChunkingStrategy,
)


def _doc(
    text: str,
    section_title: str = "",
    has_table: bool = False,
    block_type: str = "paragraph",
) -> Document:
    return Document(
        page_content=text,
        metadata={
            "section_title": section_title,
            "has_table": has_table,
            "block_type": block_type,
        },
    )


class TestSectionAwareChunkingStrategy:

    def _make_strategy(
        self, chunk_size: int = 100, overlap: int = 10
    ) -> SectionAwareChunkingStrategy:
        config = ChunkingConfig(chunk_size=chunk_size, chunk_overlap=overlap)
        return SectionAwareChunkingStrategy(config, min_chunk_size=20)

    def test_empty_input(self) -> None:
        strategy = self._make_strategy()
        assert strategy.chunk([]) == []

    def test_single_small_doc_unchanged(self) -> None:
        strategy = self._make_strategy()
        docs = [_doc("짧은 문서입니다.")]
        result = strategy.chunk(docs)

        assert len(result) == 1
        assert result[0].page_content == "짧은 문서입니다."

    def test_table_not_split(self) -> None:
        long_table = "| " + " | ".join(["데이터"] * 50) + " |"
        strategy = self._make_strategy(chunk_size=20)
        docs = [_doc(long_table, has_table=True)]
        result = strategy.chunk(docs)

        assert len(result) == 1
        assert result[0].page_content == long_table

    def test_large_doc_split(self) -> None:
        long_text = "이것은 긴 문서입니다. " * 100
        strategy = self._make_strategy(chunk_size=50)
        docs = [_doc(long_text)]
        result = strategy.chunk(docs)

        assert len(result) > 1

    def test_section_boundary_respected(self) -> None:
        docs = [
            _doc("섹션A 내용", section_title="A"),
            _doc("섹션B 내용", section_title="B"),
        ]
        strategy = self._make_strategy()
        result = strategy.chunk(docs)

        assert len(result) == 2

    def test_short_chunks_merged_same_section(self) -> None:
        docs = [
            _doc("짧", section_title="A"),
            _doc("은", section_title="A"),
        ]
        strategy = self._make_strategy(chunk_size=100)
        result = strategy.chunk(docs)

        assert len(result) == 1
        assert "짧" in result[0].page_content
        assert "은" in result[0].page_content

    def test_short_chunks_not_merged_different_sections(self) -> None:
        docs = [
            _doc("짧A", section_title="A"),
            _doc("짧B", section_title="B"),
        ]
        strategy = self._make_strategy(chunk_size=100)
        result = strategy.chunk(docs)

        assert len(result) == 2

    def test_chunk_metadata_preserved(self) -> None:
        strategy = self._make_strategy()
        docs = [_doc("내용입니다", section_title="섹션1")]
        result = strategy.chunk(docs)

        assert result[0].metadata["section_title"] == "섹션1"

    def test_strategy_name(self) -> None:
        strategy = self._make_strategy()
        assert strategy.get_strategy_name() == "section_aware"

    def test_chunk_size(self) -> None:
        strategy = self._make_strategy(chunk_size=200)
        assert strategy.get_chunk_size() == 200
