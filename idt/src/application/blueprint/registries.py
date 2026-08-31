"""SampleExtractorRegistry — 확장자 키로 SampleExtractorPort 를 해석한다.

Design Ref: golden-sample-blueprint §2.2 / multimodal ExtractorRegistry 동형.
새 포맷은 register() 만으로 추가된다 (Plan §2.1 확장성).
"""

from __future__ import annotations

from pathlib import PurePath

from src.domain.blueprint.errors import UnsupportedSampleFormatError
from src.domain.blueprint.interfaces import SampleExtractorPort


class SampleExtractorRegistry:
    def __init__(self) -> None:
        self._by_ext: dict[str, SampleExtractorPort] = {}

    def register(self, extractor: SampleExtractorPort) -> None:
        for ext in extractor.supported_extensions:
            key = ext.lower().lstrip(".")
            if key in self._by_ext:
                raise ValueError(f"extractor for '.{key}' already registered")
            self._by_ext[key] = extractor

    def resolve(self, filename: str) -> SampleExtractorPort:
        ext = PurePath(filename).suffix.lower().lstrip(".")
        extractor = self._by_ext.get(ext)
        if extractor is None:
            raise UnsupportedSampleFormatError(ext, self.supported)
        return extractor

    @property
    def supported(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_ext))
