"""markdown 텍스트에서 표를 감지하고 검색 최적화 버전을 생성."""
import re

from src.domain.chunking.table_content_generator import (
    PreprocessResult,
    TableContentGenerator,
    TableSpan,
)


class TableFlatteningPreprocessor:
    """markdown 텍스트에서 표를 감지하여 부모/자식용 텍스트를 분리."""

    _TABLE_LINE = re.compile(r"^\s*\|.+\|\s*$")
    _SEPARATOR = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")

    def __init__(self, generator: TableContentGenerator) -> None:
        self._generator = generator

    def process(
        self,
        text: str,
        section_title: str = "",
    ) -> PreprocessResult:
        tables = self._detect_tables(text)

        if not tables:
            return PreprocessResult(
                parent_text=text,
                child_text=text,
                table_count=0,
            )

        child_text = text
        all_metadata: list[dict] = []

        for table_span in reversed(tables):
            table_md = text[table_span.start : table_span.end]
            result = self._generator.generate(table_md, section_title)

            child_text = (
                child_text[: table_span.start]
                + result.search_optimized_text
                + child_text[table_span.end :]
            )
            all_metadata.append(result.metadata)

        return PreprocessResult(
            parent_text=text,
            child_text=child_text,
            table_count=len(tables),
            metadata=self._merge_table_metadata(all_metadata),
        )

    def _detect_tables(self, text: str) -> list[TableSpan]:
        lines = text.split("\n")
        tables: list[TableSpan] = []

        current_pos = 0
        table_start_pos: int | None = None
        has_separator = False

        for line in lines:
            is_table_line = bool(self._TABLE_LINE.match(line))
            is_separator = bool(self._SEPARATOR.match(line))

            if is_table_line:
                if table_start_pos is None:
                    table_start_pos = current_pos
                if is_separator:
                    has_separator = True
            else:
                if table_start_pos is not None and has_separator:
                    tables.append(
                        TableSpan(start=table_start_pos, end=current_pos)
                    )
                table_start_pos = None
                has_separator = False

            current_pos += len(line) + 1

        if table_start_pos is not None and has_separator:
            table_end = min(current_pos - 1, len(text))
            tables.append(TableSpan(start=table_start_pos, end=table_end))

        return tables

    def _merge_table_metadata(self, metadata_list: list[dict]) -> dict:
        if not metadata_list:
            return {}
        if len(metadata_list) == 1:
            return metadata_list[0]

        all_columns: list[list[str]] = []
        total_rows = 0
        has_numeric = False

        for meta in metadata_list:
            if "columns" in meta:
                all_columns.append(meta["columns"])
            total_rows += meta.get("row_count", 0)
            if meta.get("has_numeric_data"):
                has_numeric = True

        return {
            "table_columns": all_columns,
            "total_row_count": total_rows,
            "has_numeric_data": has_numeric,
            "multi_table": len(metadata_list) > 1,
        }
