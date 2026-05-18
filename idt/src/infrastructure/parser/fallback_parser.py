"""품질 점수 기반 파서 자동 전환 오케스트레이터."""
from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.documents import Document

from src.domain.parser.parse_quality import ParseQualityScore
from src.infrastructure.parser.layout.layout_analyzer import LayoutAnalyzer
from src.infrastructure.parser.layout.quality_scorer import QualityScorer
from src.infrastructure.logging import get_logger

if TYPE_CHECKING:
    import fitz
    from src.domain.parser.interfaces import PDFParserInterface
    from src.domain.logging.interfaces.logger_interface import LoggerInterface

logger = get_logger(__name__)


class FallbackParser:
    """품질 점수 기반 파서 자동 전환 오케스트레이터.

    파서 순서: LayoutAnalyzer(PyMuPDF) → secondary → tertiary
    """

    def __init__(
        self,
        layout_analyzer: LayoutAnalyzer,
        secondary_parser: PDFParserInterface | None = None,
        tertiary_parser: PDFParserInterface | None = None,
        quality_scorer: QualityScorer | None = None,
    ) -> None:
        self._layout_analyzer = layout_analyzer
        self._secondary = secondary_parser
        self._tertiary = tertiary_parser
        self._quality_scorer = quality_scorer or QualityScorer()
        self._fallback_parsers = [
            p for p in [secondary_parser, tertiary_parser] if p
        ]

    def parse_with_fallback(
        self,
        pdf_doc: fitz.Document,
        file_bytes: bytes,
        filename: str,
        user_id: str,
    ) -> tuple[list[Document], ParseQualityScore, str]:
        """품질이 충족될 때까지 파서를 순차 시도."""
        documents, quality = self._layout_analyzer.analyze(
            pdf_doc, filename, user_id
        )

        logger.info(
            "Primary parser attempt",
            parser="pymupdf_layout",
            quality_score=quality.score,
            issues=list(quality.issues),
        )

        if not quality.fallback_required:
            return documents, quality, "pymupdf_layout"

        for parser in self._fallback_parsers:
            try:
                fallback_docs = parser.parse_bytes(
                    file_bytes, filename, user_id
                )
                fallback_quality = self._quality_scorer.score_documents(
                    fallback_docs
                )

                logger.info(
                    "Fallback parser attempt",
                    parser=parser.get_parser_name(),
                    quality_score=fallback_quality.score,
                )

                if not fallback_quality.fallback_required:
                    return (
                        fallback_docs,
                        fallback_quality,
                        parser.get_parser_name(),
                    )

                if fallback_quality.score > quality.score:
                    documents, quality = fallback_docs, fallback_quality

            except Exception as e:
                logger.warning(
                    "Fallback parser failed",
                    parser=parser.get_parser_name(),
                    error=str(e),
                )
                continue

        logger.warning(
            "All parsers below quality threshold",
            filename=filename,
            best_score=quality.score,
        )

        return documents, quality, "best_effort"
