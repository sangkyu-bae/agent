"""표를 markdown + 의미 문장 + 메타데이터로 변환."""
from dataclasses import dataclass

from src.domain.parser.document_element import DocumentElement


@dataclass
class TableResult:
    """표 처리 결과."""

    markdown: str
    semantic_sentences: list[str]
    metadata: dict


class TableHandler:
    """표 DocumentElement를 markdown + 의미 문장으로 변환."""

    def process_table_element(
        self,
        table_element: DocumentElement,
        section_title: str,
    ) -> TableResult:
        """표 DocumentElement를 3가지 형태로 변환."""
        md_text = table_element.text
        rows = self._parse_markdown_table(md_text)

        if not rows or len(rows) < 2:
            return TableResult(
                markdown=md_text,
                semantic_sentences=[],
                metadata={
                    "block_type": "table",
                    "section_title": section_title,
                },
            )

        headers = rows[0]
        data_rows = rows[1:]

        sentences = self._generate_semantic_sentences(
            headers, data_rows, section_title
        )

        return TableResult(
            markdown=md_text,
            semantic_sentences=sentences,
            metadata={
                "block_type": "table",
                "section_title": section_title,
                "columns": headers,
                "row_count": len(data_rows),
                "has_numeric_data": self._has_numeric_data(data_rows),
            },
        )

    def _parse_markdown_table(self, md_text: str) -> list[list[str]]:
        rows: list[list[str]] = []
        for line in md_text.strip().split("\n"):
            line = line.strip()
            if not line.startswith("|"):
                continue
            if "---" in line:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(cells)
        return rows

    def _generate_semantic_sentences(
        self,
        headers: list[str],
        data_rows: list[list[str]],
        section_title: str,
    ) -> list[str]:
        sentences: list[str] = []
        prefix = f"{section_title}에서 " if section_title else ""

        for row in data_rows:
            if len(row) != len(headers):
                continue
            parts = []
            for header, value in zip(headers, row):
                if value and value.strip():
                    parts.append(f"{header}은(는) {value}")
            if parts:
                sentence = prefix + ", ".join(parts) + "."
                sentences.append(sentence)

        return sentences

    def _has_numeric_data(self, data_rows: list[list[str]]) -> bool:
        for row in data_rows:
            for cell in row:
                cleaned = (
                    cell.replace(",", "")
                    .replace("%", "")
                    .replace("원", "")
                    .strip()
                )
                try:
                    float(cleaned)
                    return True
                except ValueError:
                    continue
        return False
