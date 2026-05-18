"""Domain value objects for PDF document elements.

BoundingBox와 DocumentElement는 좌표 기반 PDF 요소 추출의 핵심 VO.
외부 의존 없음 — dataclass, typing만 사용.
"""
from dataclasses import dataclass, replace
from typing import Literal


BlockType = Literal[
    "title", "heading", "paragraph", "table", "table_row",
    "header", "footer", "footnote", "figure_caption", "reference",
    "list_item", "page_number",
]


@dataclass(frozen=True)
class BoundingBox:
    """PDF 페이지 내 요소의 좌표 영역."""

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x1 < self.x0:
            raise ValueError("x1 must be >= x0")
        if self.y1 < self.y0:
            raise ValueError("y1 must be >= y0")

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def area(self) -> float:
        return self.width * self.height

    def is_within_top_ratio(
        self, page_height: float, ratio: float = 0.10
    ) -> bool:
        """요소가 페이지 상단 ratio 영역 안에 있는지 판단."""
        return self.y1 <= page_height * ratio

    def is_within_bottom_ratio(
        self, page_height: float, ratio: float = 0.90
    ) -> bool:
        """요소가 페이지 하단 ratio 영역 안에 있는지 판단."""
        return self.y0 >= page_height * ratio


@dataclass(frozen=True)
class DocumentElement:
    """PDF 페이지에서 추출한 원자 요소."""

    page_no: int
    text: str
    bbox: BoundingBox
    block_type: BlockType
    section_title: str = ""
    reading_order: int = 0
    font_size: float = 0.0
    is_bold: bool = False
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.page_no < 1:
            raise ValueError("page_no must be >= 1")
        if not isinstance(self.bbox, BoundingBox):
            raise TypeError("bbox must be a BoundingBox instance")
