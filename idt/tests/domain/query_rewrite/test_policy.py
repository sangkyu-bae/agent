"""Tests for QueryRewritePolicy."""

import pytest

from src.domain.query_rewrite.policy import QueryRewritePolicy


class TestQueryRewritePolicy:
    """Tests for QueryRewritePolicy."""

    class TestRequiresRewrite:
        """Tests for requires_rewrite method."""

        def test_requires_rewrite_short_query_returns_true(self) -> None:
            """Short queries (single keyword) should require rewrite."""
            result = QueryRewritePolicy.requires_rewrite("금리")
            assert result is True

        def test_requires_rewrite_question_without_context_returns_true(self) -> None:
            """Questions without sufficient context should require rewrite."""
            result = QueryRewritePolicy.requires_rewrite("이거 어떻게 해?")
            assert result is True

        def test_requires_rewrite_well_formed_query_returns_false(self) -> None:
            """Well-formed queries with clear intent should not require rewrite."""
            result = QueryRewritePolicy.requires_rewrite(
                "2024년 한국은행 기준금리 인상 정책에 대해 알려주세요"
            )
            assert result is False

        def test_requires_rewrite_empty_query_returns_false(self) -> None:
            """Empty queries should not require rewrite (validation error)."""
            result = QueryRewritePolicy.requires_rewrite("")
            assert result is False

        def test_requires_rewrite_whitespace_query_returns_false(self) -> None:
            """Whitespace-only queries should not require rewrite."""
            result = QueryRewritePolicy.requires_rewrite("   ")
            assert result is False

        def test_requires_rewrite_ambiguous_pronoun_returns_true(self) -> None:
            """Queries with ambiguous pronouns should require rewrite."""
            result = QueryRewritePolicy.requires_rewrite("그것에 대해 알려줘")
            assert result is True

        def test_requires_rewrite_long_well_formed_query_returns_false(self) -> None:
            """Long well-formed queries should not require rewrite."""
            query = "국민연금 개혁안에서 제시된 연금 수령 시작 나이 변경 사항을 상세히 설명해주세요"
            result = QueryRewritePolicy.requires_rewrite(query)
            assert result is False

        def test_requires_rewrite_vague_question_returns_true(self) -> None:
            """Vague questions should require rewrite."""
            result = QueryRewritePolicy.requires_rewrite("뭐야?")
            assert result is True

    class TestValidateRewrittenQuery:
        """Tests for validate_rewritten_query method."""

        def test_validate_rewritten_query_valid_returns_true(self) -> None:
            """Valid rewritten query should pass validation."""
            result = QueryRewritePolicy.validate_rewritten_query(
                "2024년 기준금리 정책 변화에 대한 정보"
            )
            assert result is True

        def test_validate_rewritten_query_empty_returns_false(self) -> None:
            """Empty rewritten query should fail validation."""
            result = QueryRewritePolicy.validate_rewritten_query("")
            assert result is False

        def test_validate_rewritten_query_too_short_returns_false(self) -> None:
            """Too short rewritten query should fail validation."""
            result = QueryRewritePolicy.validate_rewritten_query("a")
            assert result is False

        def test_validate_rewritten_query_too_long_returns_false(self) -> None:
            """Too long rewritten query should fail validation."""
            long_query = "a" * 1001
            result = QueryRewritePolicy.validate_rewritten_query(long_query)
            assert result is False
