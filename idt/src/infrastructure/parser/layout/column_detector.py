"""페이지 레이아웃(1단/2단/혼합) 감지."""
from enum import Enum

from src.domain.parser.document_element import DocumentElement


class LayoutType(Enum):
    SINGLE = "single"
    DOUBLE = "double"
    MIXED = "mixed"


class ColumnDetector:
    """페이지 레이아웃(1단/2단/혼합) 감지."""

    COLUMN_GAP_RATIO: float = 0.05
    FULL_WIDTH_RATIO: float = 0.70
    COLUMN_THRESHOLD: float = 0.30

    def detect(
        self,
        elements: list[DocumentElement],
        page_width: float,
    ) -> LayoutType:
        """요소들의 x좌표 분포로 레이아웃 유형 감지."""
        if not elements:
            return LayoutType.SINGLE

        midpoint = page_width / 2
        gap_threshold = page_width * self.COLUMN_GAP_RATIO

        left_count = 0
        right_count = 0
        full_width_count = 0

        for elem in elements:
            if elem.bbox.width >= page_width * self.FULL_WIDTH_RATIO:
                full_width_count += 1
            elif elem.bbox.center_x < midpoint - gap_threshold:
                left_count += 1
            elif elem.bbox.center_x > midpoint + gap_threshold:
                right_count += 1

        total_non_full = left_count + right_count
        if total_non_full == 0:
            return LayoutType.SINGLE

        left_ratio = left_count / total_non_full
        right_ratio = right_count / total_non_full

        if left_ratio >= self.COLUMN_THRESHOLD and right_ratio >= self.COLUMN_THRESHOLD:
            if full_width_count > 0:
                return LayoutType.MIXED
            return LayoutType.DOUBLE

        return LayoutType.SINGLE

    def split_columns(
        self,
        elements: list[DocumentElement],
        page_width: float,
    ) -> tuple[list[DocumentElement], list[DocumentElement], list[DocumentElement]]:
        """요소를 좌측/우측/전체너비로 분리."""
        midpoint = page_width / 2
        left: list[DocumentElement] = []
        right: list[DocumentElement] = []
        full: list[DocumentElement] = []

        for elem in elements:
            if elem.bbox.width >= page_width * self.FULL_WIDTH_RATIO:
                full.append(elem)
            elif elem.bbox.center_x < midpoint:
                left.append(elem)
            else:
                right.append(elem)

        return left, right, full
