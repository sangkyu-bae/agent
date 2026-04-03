"""Tests for web search result formatter."""

import pytest

from src.domain.web_search.value_objects import SearchResult, SearchResultItem
from src.infrastructure.web_search.formatter import format_search_result_to_xml


class TestFormatSearchResultToXml:
    """Tests for format_search_result_to_xml function."""

    def test_format_returns_xml_with_required_fields(self) -> None:
        """Formatter should return XML with title, url, content fields."""
        items = [
            SearchResultItem(
                title="Test Article",
                url="https://example.com/article",
                content="This is the article content.",
                score=0.95,
            ),
        ]
        result = SearchResult(query="test query", items=items)

        xml_output = format_search_result_to_xml(result)

        assert "<search_results>" in xml_output
        assert "</search_results>" in xml_output
        assert "<result>" in xml_output
        assert "<title>Test Article</title>" in xml_output
        assert "<url>https://example.com/article</url>" in xml_output
        assert "<content>This is the article content.</content>" in xml_output
        assert "<score>0.95</score>" in xml_output

    def test_format_includes_raw_content_when_present_and_enabled(self) -> None:
        """Formatter should include raw_content when present and enabled."""
        items = [
            SearchResultItem(
                title="Test Article",
                url="https://example.com/article",
                content="Snippet content",
                score=0.95,
                raw_content="Full raw content of the page.",
            ),
        ]
        result = SearchResult(query="test query", items=items)

        xml_output = format_search_result_to_xml(result, include_raw_content=True)

        assert "<raw_content>Full raw content of the page.</raw_content>" in xml_output

    def test_format_excludes_raw_content_when_disabled(self) -> None:
        """Formatter should exclude raw_content when disabled."""
        items = [
            SearchResultItem(
                title="Test Article",
                url="https://example.com/article",
                content="Snippet content",
                score=0.95,
                raw_content="Full raw content of the page.",
            ),
        ]
        result = SearchResult(query="test query", items=items)

        xml_output = format_search_result_to_xml(result, include_raw_content=False)

        assert "<raw_content>" not in xml_output

    def test_format_handles_special_characters(self) -> None:
        """Formatter should escape special XML characters."""
        items = [
            SearchResultItem(
                title="Article with <tags> & symbols",
                url="https://example.com/?a=1&b=2",
                content="Content with \"quotes\" and 'apostrophes'",
                score=0.95,
            ),
        ]
        result = SearchResult(query="test query", items=items)

        xml_output = format_search_result_to_xml(result)

        assert "&lt;tags&gt;" in xml_output
        assert "&amp;" in xml_output

    def test_format_handles_multiple_results(self) -> None:
        """Formatter should handle multiple search results."""
        items = [
            SearchResultItem(
                title="Article 1",
                url="https://example.com/1",
                content="Content 1",
                score=0.95,
            ),
            SearchResultItem(
                title="Article 2",
                url="https://example.com/2",
                content="Content 2",
                score=0.85,
            ),
        ]
        result = SearchResult(query="test query", items=items)

        xml_output = format_search_result_to_xml(result)

        assert xml_output.count("<result>") == 2
        assert xml_output.count("</result>") == 2
        assert "<title>Article 1</title>" in xml_output
        assert "<title>Article 2</title>" in xml_output

    def test_format_handles_empty_results(self) -> None:
        """Formatter should handle empty search results."""
        result = SearchResult(query="test query", items=[])

        xml_output = format_search_result_to_xml(result)

        assert "<search_results>" in xml_output
        assert "</search_results>" in xml_output
        assert "<result>" not in xml_output

    def test_format_excludes_raw_content_when_none(self) -> None:
        """Formatter should not include raw_content tag when value is None."""
        items = [
            SearchResultItem(
                title="Article",
                url="https://example.com",
                content="Content",
                score=0.95,
                raw_content=None,
            ),
        ]
        result = SearchResult(query="test query", items=items)

        xml_output = format_search_result_to_xml(result, include_raw_content=True)

        assert "<raw_content>" not in xml_output
