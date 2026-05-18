"""요소들에서 heading을 감지하고 섹션 트리를 구성."""
from dataclasses import replace

from src.domain.parser.document_element import DocumentElement
from src.domain.parser.section_tree import SectionNode


class SectionBuilder:
    """font_size 기반 heading 감지 → 섹션 트리 구성."""

    HEADING_SIZE_RATIO: float = 1.2

    def build(
        self,
        elements: list[DocumentElement],
    ) -> list[SectionNode]:
        """정렬된 요소 리스트에서 섹션 트리를 구성."""
        if not elements:
            return []

        avg_font_size = self._calculate_avg_font_size(elements)
        heading_threshold = avg_font_size * self.HEADING_SIZE_RATIO

        classified = self._classify_headings(elements, heading_threshold)
        return self._build_tree(classified)

    def assign_section_titles(
        self,
        elements: list[DocumentElement],
    ) -> list[DocumentElement]:
        """각 요소에 section_title을 부여한 새 리스트 반환."""
        if not elements:
            return []

        avg_font_size = self._calculate_avg_font_size(elements)
        heading_threshold = avg_font_size * self.HEADING_SIZE_RATIO

        current_title = ""
        result: list[DocumentElement] = []

        for elem in elements:
            is_heading = (
                elem.font_size >= heading_threshold
                and (elem.is_bold or elem.font_size > heading_threshold)
            )
            if is_heading:
                current_title = elem.text
            result.append(replace(elem, section_title=current_title))

        return result

    def _calculate_avg_font_size(
        self, elements: list[DocumentElement]
    ) -> float:
        sizes = [e.font_size for e in elements if e.font_size > 0]
        return sum(sizes) / len(sizes) if sizes else 10.0

    def _classify_headings(
        self,
        elements: list[DocumentElement],
        heading_threshold: float,
    ) -> list[tuple[DocumentElement, int]]:
        font_sizes = sorted(
            set(
                e.font_size
                for e in elements
                if e.font_size >= heading_threshold
            ),
            reverse=True,
        )
        size_to_level = {
            size: idx + 1 for idx, size in enumerate(font_sizes)
        }

        result: list[tuple[DocumentElement, int]] = []
        for elem in elements:
            is_heading = (
                elem.font_size >= heading_threshold
                and (elem.is_bold or elem.font_size > heading_threshold)
            )
            if is_heading:
                level = size_to_level.get(elem.font_size, 0)
                result.append(
                    (replace(elem, block_type="heading"), level)
                )
            else:
                result.append((elem, 0))

        return result

    def _build_tree(
        self,
        classified: list[tuple[DocumentElement, int]],
    ) -> list[SectionNode]:
        if not classified:
            return []

        root_sections: list[SectionNode] = []
        current_section: SectionNode | None = None
        current_elements: list[DocumentElement] = []

        for elem, level in classified:
            if level > 0:
                if current_section:
                    current_section.elements = current_elements
                    root_sections.append(current_section)
                elif current_elements:
                    root_sections.append(SectionNode(
                        title="",
                        level=0,
                        elements=current_elements,
                        children=[],
                        page_range=(
                            current_elements[0].page_no,
                            current_elements[-1].page_no,
                        ),
                    ))

                current_section = SectionNode(
                    title=elem.text,
                    level=level,
                    elements=[],
                    children=[],
                    page_range=(elem.page_no, elem.page_no),
                )
                current_elements = [elem]
            else:
                current_elements.append(elem)

        if current_section:
            current_section.elements = current_elements
            if current_elements:
                current_section.page_range = (
                    current_section.page_range[0],
                    current_elements[-1].page_no,
                )
            root_sections.append(current_section)
        elif current_elements:
            root_sections.append(SectionNode(
                title="",
                level=0,
                elements=current_elements,
                children=[],
                page_range=(
                    current_elements[0].page_no,
                    current_elements[-1].page_no,
                ),
            ))

        return root_sections
