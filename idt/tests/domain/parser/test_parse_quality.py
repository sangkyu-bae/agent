"""Tests for ParseQualityScore value object."""
import pytest

from src.domain.parser.parse_quality import ParseQualityScore


class TestParseQualityScore:
    """Tests for ParseQualityScore value object."""

    def test_create_valid_score(self) -> None:
        score = ParseQualityScore(
            page=1,
            score=0.85,
            text_char_count=500,
            avg_word_length=3.5,
            order_consistency=0.95,
            issues=(),
        )
        assert score.page == 1
        assert score.score == 0.85
        assert score.text_char_count == 500
        assert score.avg_word_length == 3.5
        assert score.order_consistency == 0.95
        assert score.issues == ()

    def test_score_below_zero_raises_error(self) -> None:
        with pytest.raises(ValueError, match="score must be between 0.0 and 1.0"):
            ParseQualityScore(
                page=1, score=-0.1, text_char_count=0,
                avg_word_length=0.0, order_consistency=1.0, issues=(),
            )

    def test_score_above_one_raises_error(self) -> None:
        with pytest.raises(ValueError, match="score must be between 0.0 and 1.0"):
            ParseQualityScore(
                page=1, score=1.1, text_char_count=0,
                avg_word_length=0.0, order_consistency=1.0, issues=(),
            )

    def test_score_boundary_zero(self) -> None:
        score = ParseQualityScore(
            page=0, score=0.0, text_char_count=0,
            avg_word_length=0.0, order_consistency=0.0, issues=("empty_page",),
        )
        assert score.score == 0.0

    def test_score_boundary_one(self) -> None:
        score = ParseQualityScore(
            page=1, score=1.0, text_char_count=1000,
            avg_word_length=5.0, order_consistency=1.0, issues=(),
        )
        assert score.score == 1.0

    def test_order_consistency_below_zero_raises(self) -> None:
        with pytest.raises(
            ValueError, match="order_consistency must be between 0.0 and 1.0"
        ):
            ParseQualityScore(
                page=1, score=0.5, text_char_count=100,
                avg_word_length=3.0, order_consistency=-0.1, issues=(),
            )

    def test_order_consistency_above_one_raises(self) -> None:
        with pytest.raises(
            ValueError, match="order_consistency must be between 0.0 and 1.0"
        ):
            ParseQualityScore(
                page=1, score=0.5, text_char_count=100,
                avg_word_length=3.0, order_consistency=1.1, issues=(),
            )

    def test_fallback_required_true_when_below_threshold(self) -> None:
        score = ParseQualityScore(
            page=1, score=0.5, text_char_count=50,
            avg_word_length=2.0, order_consistency=0.6, issues=("low_text",),
        )
        assert score.fallback_required is True

    def test_fallback_required_false_when_above_threshold(self) -> None:
        score = ParseQualityScore(
            page=1, score=0.8, text_char_count=500,
            avg_word_length=4.0, order_consistency=0.9, issues=(),
        )
        assert score.fallback_required is False

    def test_fallback_required_false_at_exactly_threshold(self) -> None:
        score = ParseQualityScore(
            page=1, score=0.7, text_char_count=200,
            avg_word_length=3.0, order_consistency=0.8, issues=(),
        )
        assert score.fallback_required is False

    def test_threshold_class_variable(self) -> None:
        assert ParseQualityScore.FALLBACK_THRESHOLD == 0.7

    def test_issues_are_immutable_tuple(self) -> None:
        score = ParseQualityScore(
            page=1, score=0.5, text_char_count=30,
            avg_word_length=1.2, order_consistency=0.4,
            issues=("fragmented_text", "reading_order_broken"),
        )
        assert isinstance(score.issues, tuple)
        assert len(score.issues) == 2

    def test_is_immutable(self) -> None:
        score = ParseQualityScore(
            page=1, score=0.9, text_char_count=800,
            avg_word_length=4.5, order_consistency=0.95, issues=(),
        )
        with pytest.raises(AttributeError):
            score.score = 0.5
