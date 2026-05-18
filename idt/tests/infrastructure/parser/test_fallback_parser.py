"""Tests for FallbackParser."""
from unittest.mock import MagicMock
import pytest

from src.domain.parser.parse_quality import ParseQualityScore
from src.infrastructure.parser.fallback_parser import FallbackParser


def _good_quality() -> ParseQualityScore:
    return ParseQualityScore(
        page=0, score=0.9, text_char_count=1000,
        avg_word_length=4.0, order_consistency=0.95, issues=(),
    )


def _bad_quality() -> ParseQualityScore:
    return ParseQualityScore(
        page=0, score=0.4, text_char_count=50,
        avg_word_length=2.0, order_consistency=0.5,
        issues=("low_text_extraction",),
    )


def _mock_analyzer(quality: ParseQualityScore) -> MagicMock:
    analyzer = MagicMock()
    analyzer.analyze.return_value = ([MagicMock()], quality)
    return analyzer


def _mock_parser(
    name: str, docs: list | None = None, raises: bool = False
) -> MagicMock:
    parser = MagicMock()
    parser.get_parser_name.return_value = name
    if raises:
        parser.parse_bytes.side_effect = RuntimeError("parse failed")
    else:
        parser.parse_bytes.return_value = docs or [MagicMock(page_content="text " * 50)]
    return parser


class TestFallbackParser:

    def test_primary_sufficient_no_fallback(self) -> None:
        analyzer = _mock_analyzer(_good_quality())
        secondary = _mock_parser("secondary")

        fb = FallbackParser(analyzer, secondary_parser=secondary)
        docs, quality, parser_used = fb.parse_with_fallback(
            MagicMock(), b"pdf", "test.pdf", "user1"
        )

        assert parser_used == "pymupdf_layout"
        secondary.parse_bytes.assert_not_called()

    def test_fallback_to_secondary(self) -> None:
        analyzer = _mock_analyzer(_bad_quality())
        secondary = _mock_parser("docling")

        scorer = MagicMock()
        scorer.score_documents.return_value = _good_quality()

        fb = FallbackParser(
            analyzer, secondary_parser=secondary, quality_scorer=scorer
        )
        docs, quality, parser_used = fb.parse_with_fallback(
            MagicMock(), b"pdf", "test.pdf", "user1"
        )

        assert parser_used == "docling"
        secondary.parse_bytes.assert_called_once()

    def test_fallback_to_tertiary(self) -> None:
        analyzer = _mock_analyzer(_bad_quality())
        secondary = _mock_parser("docling")
        tertiary = _mock_parser("llamaparser")

        scorer = MagicMock()
        scorer.score_documents.side_effect = [_bad_quality(), _good_quality()]

        fb = FallbackParser(
            analyzer,
            secondary_parser=secondary,
            tertiary_parser=tertiary,
            quality_scorer=scorer,
        )
        docs, quality, parser_used = fb.parse_with_fallback(
            MagicMock(), b"pdf", "test.pdf", "user1"
        )

        assert parser_used == "llamaparser"

    def test_all_parsers_fail_returns_best_effort(self) -> None:
        analyzer = _mock_analyzer(_bad_quality())
        secondary = _mock_parser("docling")

        scorer = MagicMock()
        scorer.score_documents.return_value = _bad_quality()

        fb = FallbackParser(
            analyzer, secondary_parser=secondary, quality_scorer=scorer
        )
        docs, quality, parser_used = fb.parse_with_fallback(
            MagicMock(), b"pdf", "test.pdf", "user1"
        )

        assert parser_used == "best_effort"

    def test_secondary_exception_continues_to_tertiary(self) -> None:
        analyzer = _mock_analyzer(_bad_quality())
        secondary = _mock_parser("docling", raises=True)
        tertiary = _mock_parser("llamaparser")

        scorer = MagicMock()
        scorer.score_documents.return_value = _good_quality()

        fb = FallbackParser(
            analyzer,
            secondary_parser=secondary,
            tertiary_parser=tertiary,
            quality_scorer=scorer,
        )
        docs, quality, parser_used = fb.parse_with_fallback(
            MagicMock(), b"pdf", "test.pdf", "user1"
        )

        assert parser_used == "llamaparser"

    def test_no_fallback_parsers(self) -> None:
        analyzer = _mock_analyzer(_bad_quality())

        fb = FallbackParser(analyzer)
        docs, quality, parser_used = fb.parse_with_fallback(
            MagicMock(), b"pdf", "test.pdf", "user1"
        )

        assert parser_used == "best_effort"
