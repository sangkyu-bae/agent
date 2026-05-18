"""Domain value object for document section tree.

문서 섹션 트리 구조 — 외부 의존 없음.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.parser.document_element import DocumentElement


@dataclass
class SectionNode:
    """문서 섹션 트리의 노드."""

    title: str
    level: int
    elements: list[DocumentElement]
    children: list[SectionNode]
    page_range: tuple[int, int]

    @property
    def text_content(self) -> str:
        """섹션 내 모든 요소의 텍스트를 순서대로 결합."""
        return "\n".join(e.text for e in self.elements)

    @property
    def has_table(self) -> bool:
        return any(
            e.block_type in ("table", "table_row") for e in self.elements
        )

    def flatten(self) -> list[SectionNode]:
        """트리를 평탄화하여 모든 노드를 리스트로 반환."""
        result: list[SectionNode] = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result
