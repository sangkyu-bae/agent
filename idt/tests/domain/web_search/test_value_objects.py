"""Tests for web search value objects."""

import pytest

from src.domain.web_search.value_objects import SearchResult, SearchResultItem


class TestSearchResultItem:
    """Tests for SearchResultItem value object."""

    def test_create_with_required_fields(self) -> None:
        """SearchResultItem should be created with required fields."""
        item = SearchResultItem(
            title="Test Title",
            url="https://example.com",
            content="Test content snippet",
            score=0.95,
        )
        assert item.title == "Test Title"
        assert item.url == "https://example.com"
        assert item.content == "Test content snippet"
        assert item.score == 0.95
        assert item.raw_content is None

    def test_raw_content_is_optional(self) -> None:
        """raw_content field should be optional."""
        item = SearchResultItem(
            title="Test Title",
            url="https://example.com",
            content="Test content snippet",
            score=0.95,
            raw_content="Full raw content here",
        )
        assert item.raw_content == "Full raw content here"

    def test_create_with_zero_score(self) -> None:
        """SearchResultItem should accept zero score."""
        item = SearchResultItem(
            title="Test Title",
            url="https://example.com",
            content="Test content",
            score=0.0,
        )
        assert item.score == 0.0


class TestSearchResult:
    """Tests for SearchResult value object."""

    def test_result_count_returns_correct_count(self) -> None:
        """result_count property should return correct item count."""
        items = [
            SearchResultItem(
                title="Item 1",
                url="https://example.com/1",
                content="Content 1",
                score=0.9,
            ),
            SearchResultItem(
                title="Item 2",
                url="https://example.com/2",
                content="Content 2",
                score=0.8,
            ),
        ]
        result = SearchResult(query="test query", items=items)
        assert result.result_count == 2

    def test_is_empty_returns_true_when_no_results(self) -> None:
        """is_empty property should return True when items list is empty."""
        result = SearchResult(query="test query", items=[])
        assert result.is_empty is True

    def test_is_empty_returns_false_when_has_results(self) -> None:
        """is_empty property should return False when items list has items."""
        items = [
            SearchResultItem(
                title="Item 1",
                url="https://example.com/1",
                content="Content 1",
                score=0.9,
            ),
        ]
        result = SearchResult(query="test query", items=items)
        assert result.is_empty is False

    def test_stores_query_correctly(self) -> None:
        """SearchResult should store the query correctly."""
        result = SearchResult(query="my search query", items=[])
        assert result.query == "my search query"

    def test_result_count_with_empty_items(self) -> None:
        """result_count should return 0 for empty items list."""
        result = SearchResult(query="test query", items=[])
        assert result.result_count == 0
