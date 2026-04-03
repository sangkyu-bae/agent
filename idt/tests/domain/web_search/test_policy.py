"""Tests for WebSearchPolicy."""

import pytest

from src.domain.web_search.policy import WebSearchPolicy


class TestWebSearchPolicy:
    """Tests for WebSearchPolicy."""

    class TestValidateQuery:
        """Tests for validate_query method."""

        def test_returns_true_with_valid_query(self) -> None:
            """Valid query should return True."""
            result = WebSearchPolicy.validate_query("What is Python programming?")
            assert result is True

        def test_returns_false_with_empty_query(self) -> None:
            """Empty string query should return False."""
            result = WebSearchPolicy.validate_query("")
            assert result is False

        def test_returns_false_with_none_query(self) -> None:
            """None query should return False."""
            result = WebSearchPolicy.validate_query(None)
            assert result is False

        def test_returns_false_with_too_short_query(self) -> None:
            """Query shorter than MIN_QUERY_LENGTH should return False."""
            result = WebSearchPolicy.validate_query("test")
            assert result is False

        def test_returns_true_with_min_length_query(self) -> None:
            """Query with exactly MIN_QUERY_LENGTH characters should return True."""
            query = "a" * WebSearchPolicy.MIN_QUERY_LENGTH
            result = WebSearchPolicy.validate_query(query)
            assert result is True

        def test_returns_false_with_too_long_query(self) -> None:
            """Query longer than MAX_QUERY_LENGTH should return False."""
            query = "a" * (WebSearchPolicy.MAX_QUERY_LENGTH + 1)
            result = WebSearchPolicy.validate_query(query)
            assert result is False

        def test_returns_true_with_max_length_query(self) -> None:
            """Query with exactly MAX_QUERY_LENGTH characters should return True."""
            query = "a" * WebSearchPolicy.MAX_QUERY_LENGTH
            result = WebSearchPolicy.validate_query(query)
            assert result is True

        def test_returns_false_with_whitespace_only_query(self) -> None:
            """Whitespace-only query should return False."""
            result = WebSearchPolicy.validate_query("     ")
            assert result is False

        def test_strips_whitespace_before_validation(self) -> None:
            """Query should be stripped before length validation."""
            query = "  valid query here  "
            result = WebSearchPolicy.validate_query(query)
            assert result is True

    class TestValidateMaxResults:
        """Tests for validate_max_results method."""

        def test_returns_same_value_when_valid(self) -> None:
            """Valid max_results should return the same value."""
            result = WebSearchPolicy.validate_max_results(5)
            assert result == 5

        def test_returns_default_when_less_than_one(self) -> None:
            """max_results less than 1 should return default value."""
            result = WebSearchPolicy.validate_max_results(0)
            assert result == WebSearchPolicy.DEFAULT_MAX_RESULTS

            result = WebSearchPolicy.validate_max_results(-1)
            assert result == WebSearchPolicy.DEFAULT_MAX_RESULTS

        def test_returns_max_limit_when_exceeds(self) -> None:
            """max_results exceeding MAX_RESULTS_LIMIT should return limit."""
            result = WebSearchPolicy.validate_max_results(20)
            assert result == WebSearchPolicy.MAX_RESULTS_LIMIT

        def test_returns_default_when_none(self) -> None:
            """None max_results should return default value."""
            result = WebSearchPolicy.validate_max_results(None)
            assert result == WebSearchPolicy.DEFAULT_MAX_RESULTS

        def test_returns_exact_limit_value(self) -> None:
            """max_results equal to MAX_RESULTS_LIMIT should return the same."""
            result = WebSearchPolicy.validate_max_results(
                WebSearchPolicy.MAX_RESULTS_LIMIT
            )
            assert result == WebSearchPolicy.MAX_RESULTS_LIMIT

        def test_returns_exact_default_value(self) -> None:
            """max_results equal to DEFAULT_MAX_RESULTS should return the same."""
            result = WebSearchPolicy.validate_max_results(
                WebSearchPolicy.DEFAULT_MAX_RESULTS
            )
            assert result == WebSearchPolicy.DEFAULT_MAX_RESULTS
