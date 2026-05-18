"""파싱 결과 품질을 0.0~1.0으로 점수화."""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.parser.document_element import DocumentElement
from src.domain.parser.parse_quality import ParseQualityScore

if TYPE_CHECKING:
    from langchain_core.documents import Document


class QualityScorer:
    """파싱 결과 품질을 0.0~1.0으로 점수화."""

    def score_page(
        self,
        elements: list[DocumentElement],
        page_height: float,
    ) -> ParseQualityScore:
        """한 페이지의 파싱 품질을 산출."""
        if not elements:
            return ParseQualityScore(
                page=0, score=0.0, text_char_count=0,
                avg_word_length=0.0, order_consistency=0.0,
                issues=("empty_page",),
            )

        issues: list[str] = []
        scores: list[float] = []

        text_length = sum(len(e.text) for e in elements)
        if text_length < 50:
            issues.append("low_text_extraction")
            scores.append(0.2)
        elif text_length < 200:
            scores.append(0.6)
        else:
            scores.append(1.0)

        all_text = " ".join(e.text for e in elements)
        words = all_text.split()
        avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
        if avg_word_len < 1.5:
            issues.append("fragmented_text")
            scores.append(0.3)
        else:
            scores.append(1.0)

        y_coords = [e.bbox.y0 for e in elements]
        order_score = self._calculate_order_consistency(y_coords)
        if order_score < 0.7:
            issues.append("reading_order_broken")
        scores.append(order_score)

        has_pipe = any("|" in e.text for e in elements)
        has_table_type = any(e.block_type == "table" for e in elements)
        if has_pipe and not has_table_type:
            issues.append("table_not_detected")
            scores.append(0.7)
        else:
            scores.append(1.0)

        final_score = sum(scores) / len(scores)

        return ParseQualityScore(
            page=elements[0].page_no,
            score=round(final_score, 3),
            text_char_count=text_length,
            avg_word_length=round(avg_word_len, 2),
            order_consistency=round(order_score, 3),
            issues=tuple(issues),
        )

    def score_documents(
        self,
        documents: list[Document],
    ) -> ParseQualityScore:
        """Document 리스트 전체의 종합 품질 점수."""
        if not documents:
            return ParseQualityScore(
                page=0, score=0.0, text_char_count=0,
                avg_word_length=0.0, order_consistency=1.0,
                issues=("no_documents",),
            )

        total_chars = sum(len(d.page_content) for d in documents)
        all_text = " ".join(d.page_content for d in documents)
        words = all_text.split()
        avg_word_len = sum(len(w) for w in words) / max(len(words), 1)

        issues: list[str] = []
        scores: list[float] = []

        if total_chars < 100:
            issues.append("low_text_extraction")
            scores.append(0.2)
        else:
            scores.append(1.0)

        if avg_word_len < 1.5:
            issues.append("fragmented_text")
            scores.append(0.3)
        else:
            scores.append(1.0)

        final_score = sum(scores) / len(scores)

        return ParseQualityScore(
            page=0,
            score=round(final_score, 3),
            text_char_count=total_chars,
            avg_word_length=round(avg_word_len, 2),
            order_consistency=1.0,
            issues=tuple(issues),
        )

    def _calculate_order_consistency(
        self, y_coords: list[float]
    ) -> float:
        if len(y_coords) <= 1:
            return 1.0
        in_order = sum(
            1 for i in range(len(y_coords) - 1)
            if y_coords[i] <= y_coords[i + 1] + 5.0
        )
        return in_order / (len(y_coords) - 1)
