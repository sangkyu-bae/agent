"""좌표 기반 읽기 순서 재구성."""
from dataclasses import replace

from src.domain.parser.document_element import DocumentElement
from src.infrastructure.parser.layout.column_detector import (
    ColumnDetector,
    LayoutType,
)


class ReadingOrderReconstructor:
    """좌표 기반 읽기 순서 재구성."""

    Y_TOLERANCE: float = 5.0

    def reconstruct(
        self,
        elements: list[DocumentElement],
        layout_type: LayoutType,
        page_width: float,
    ) -> list[DocumentElement]:
        """읽기 순서에 따라 요소를 정렬하고 reading_order를 부여."""
        if not elements:
            return []

        if layout_type == LayoutType.SINGLE:
            ordered = self._sort_single(elements)
        elif layout_type == LayoutType.DOUBLE:
            ordered = self._sort_double(elements, page_width)
        else:
            ordered = self._sort_mixed(elements, page_width)

        return [
            replace(elem, reading_order=idx)
            for idx, elem in enumerate(ordered)
        ]

    def _sort_single(
        self, elements: list[DocumentElement]
    ) -> list[DocumentElement]:
        return sorted(elements, key=lambda e: (e.bbox.y0, e.bbox.x0))

    def _sort_double(
        self, elements: list[DocumentElement], page_width: float
    ) -> list[DocumentElement]:
        detector = ColumnDetector()
        left, right, full = detector.split_columns(elements, page_width)

        left_sorted = sorted(left, key=lambda e: (e.bbox.y0, e.bbox.x0))
        right_sorted = sorted(right, key=lambda e: (e.bbox.y0, e.bbox.x0))
        full_sorted = sorted(full, key=lambda e: e.bbox.y0)

        return self._interleave_full_width(
            left_sorted, right_sorted, full_sorted
        )

    def _sort_mixed(
        self, elements: list[DocumentElement], page_width: float
    ) -> list[DocumentElement]:
        detector = ColumnDetector()
        left, right, full = detector.split_columns(elements, page_width)

        full_sorted = sorted(full, key=lambda e: e.bbox.y0)
        boundaries = [e.bbox.y0 for e in full_sorted]

        remaining_left = sorted(left, key=lambda e: e.bbox.y0)
        remaining_right = sorted(right, key=lambda e: e.bbox.y0)

        result: list[DocumentElement] = []
        prev_y = 0.0

        for i, boundary_y in enumerate(boundaries):
            zone_left = [
                e for e in remaining_left if prev_y <= e.bbox.y0 < boundary_y
            ]
            zone_right = [
                e for e in remaining_right if prev_y <= e.bbox.y0 < boundary_y
            ]
            result.extend(
                sorted(zone_left, key=lambda e: (e.bbox.y0, e.bbox.x0))
            )
            result.extend(
                sorted(zone_right, key=lambda e: (e.bbox.y0, e.bbox.x0))
            )
            result.append(full_sorted[i])
            prev_y = boundary_y

        zone_left = [e for e in remaining_left if e.bbox.y0 >= prev_y]
        zone_right = [e for e in remaining_right if e.bbox.y0 >= prev_y]
        result.extend(
            sorted(zone_left, key=lambda e: (e.bbox.y0, e.bbox.x0))
        )
        result.extend(
            sorted(zone_right, key=lambda e: (e.bbox.y0, e.bbox.x0))
        )

        return result

    def _interleave_full_width(
        self,
        left: list[DocumentElement],
        right: list[DocumentElement],
        full: list[DocumentElement],
    ) -> list[DocumentElement]:
        result: list[DocumentElement] = []
        column_items = sorted(left + right, key=lambda e: e.bbox.y0)

        full_idx = 0
        for item in column_items:
            while (
                full_idx < len(full)
                and full[full_idx].bbox.y0 <= item.bbox.y0
            ):
                result.append(full[full_idx])
                full_idx += 1
            result.append(item)

        while full_idx < len(full):
            result.append(full[full_idx])
            full_idx += 1

        return result
