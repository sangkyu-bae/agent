"""규칙 기반 표 → 의미 문장 변환."""
import re

from src.domain.chunking.table_content_generator import (
    TableContentGenerator,
    TableConversionResult,
)


class RuleBasedTableContentGenerator(TableContentGenerator):
    """규칙 기반 표 → 의미 문장 변환 구현체."""

    _SEPARATOR_PATTERN = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")

    def generate(
        self, table_markdown: str, section_title: str
    ) -> TableConversionResult:
        rows = self._parse_markdown_table(table_markdown)

        if not rows or len(rows) < 2:
            return TableConversionResult(
                original_markdown=table_markdown,
                search_optimized_text=table_markdown,
                metadata={"parse_failed": True},
            )

        headers = rows[0]
        data_rows = rows[1:]
        sentences = self._generate_sentences(headers, data_rows, section_title)

        return TableConversionResult(
            original_markdown=table_markdown,
            search_optimized_text="\n".join(sentences),
            metadata={
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
            if self._SEPARATOR_PATTERN.match(line):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells:
                rows.append(cells)
        return rows

    def _generate_sentences(
        self,
        headers: list[str],
        data_rows: list[list[str]],
        section_title: str,
    ) -> list[str]:
        prefix = f"{section_title}에서 " if section_title else ""
        sentences: list[str] = []

        for row in data_rows:
            if len(row) != len(headers):
                continue
            parts = [
                f"{h}은(는) {v}"
                for h, v in zip(headers, row)
                if v and v.strip()
            ]
            if parts:
                sentences.append(prefix + ", ".join(parts) + ".")

        return sentences

    def _has_numeric_data(self, data_rows: list[list[str]]) -> bool:
        for row in data_rows:
            for cell in row:
                cleaned = (
                    cell.replace(",", "")
                    .replace("%", "")
                    .replace("원", "")
                    .replace("억", "")
                    .replace("만", "")
                    .strip()
                )
                try:
                    float(cleaned)
                    return True
                except ValueError:
                    continue
        return False
