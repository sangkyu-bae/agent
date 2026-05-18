"""좌표 + 반복 빈도 기반 헤더/푸터/페이지번호 제거."""
from src.domain.parser.document_element import DocumentElement


class NoiseRemover:
    """좌표 + 반복 빈도 기반 헤더/푸터/페이지번호 제거."""

    HEADER_RATIO: float = 0.10
    FOOTER_RATIO: float = 0.90
    REPEAT_THRESHOLD: float = 0.60

    def remove(
        self,
        pages_elements: dict[int, list[DocumentElement]],
        page_height: float,
    ) -> dict[int, list[DocumentElement]]:
        """여러 페이지에서 반복 헤더/푸터를 제거."""
        total_pages = len(pages_elements)
        if total_pages < 2:
            return pages_elements

        header_counts = self._collect_zone_texts(
            pages_elements, page_height, "header"
        )
        footer_counts = self._collect_zone_texts(
            pages_elements, page_height, "footer"
        )

        all_counts: dict[str, int] = {}
        for text, count in header_counts.items():
            all_counts[text] = all_counts.get(text, 0) + count
        for text, count in footer_counts.items():
            all_counts[text] = all_counts.get(text, 0) + count

        noise_texts = self._find_repeated_texts(all_counts, total_pages)
        noise_texts |= self._detect_page_numbers(pages_elements, page_height)

        return self._filter_elements(pages_elements, noise_texts, page_height)

    def _collect_zone_texts(
        self,
        pages_elements: dict[int, list[DocumentElement]],
        page_height: float,
        zone: str,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for elements in pages_elements.values():
            for elem in elements:
                in_zone = (
                    elem.bbox.is_within_top_ratio(page_height, self.HEADER_RATIO)
                    if zone == "header"
                    else elem.bbox.is_within_bottom_ratio(page_height, self.FOOTER_RATIO)
                )
                if in_zone:
                    normalized = elem.text.strip().lower()
                    counts[normalized] = counts.get(normalized, 0) + 1
        return counts

    def _find_repeated_texts(
        self, text_counts: dict[str, int], total_pages: int
    ) -> set[str]:
        threshold = total_pages * self.REPEAT_THRESHOLD
        return {
            text for text, count in text_counts.items()
            if count >= threshold
        }

    def _detect_page_numbers(
        self,
        pages_elements: dict[int, list[DocumentElement]],
        page_height: float,
    ) -> set[str]:
        numbers: set[str] = set()
        for elements in pages_elements.values():
            for elem in elements:
                if elem.bbox.is_within_bottom_ratio(
                    page_height, self.FOOTER_RATIO
                ):
                    stripped = elem.text.strip()
                    cleaned = stripped.replace("-", "").replace("/", "")
                    if stripped.isdigit() or cleaned.isdigit():
                        numbers.add(stripped.lower())
        return numbers

    def _filter_elements(
        self,
        pages_elements: dict[int, list[DocumentElement]],
        noise_texts: set[str],
        page_height: float,
    ) -> dict[int, list[DocumentElement]]:
        result: dict[int, list[DocumentElement]] = {}
        for page_no, elements in pages_elements.items():
            filtered = []
            for elem in elements:
                normalized = elem.text.strip().lower()
                is_noise_zone = (
                    elem.bbox.is_within_top_ratio(
                        page_height, self.HEADER_RATIO
                    )
                    or elem.bbox.is_within_bottom_ratio(
                        page_height, self.FOOTER_RATIO
                    )
                )
                if is_noise_zone and normalized in noise_texts:
                    continue
                filtered.append(elem)
            result[page_no] = filtered
        return result
