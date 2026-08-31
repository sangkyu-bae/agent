"""추출기 · 비전 어댑터 레지스트리.

Design Ref: multimodal-extractor §9.5 / Plan FR-17
— 추출기 키 = 소문자 확장자, 어댑터 키 = LlmModel.provider 문자열.
  미등록 키는 명시적 오류(UnsupportedFormatError / UnsupportedVisionProviderError).
  어댑터 1개 추가 = 파일 1개 + register() 1줄.
"""

from collections.abc import Callable
from typing import Any

from src.domain.multimodal.errors import (
    UnsupportedFormatError,
    UnsupportedVisionProviderError,
)
from src.domain.multimodal.interfaces import ImageExtractorPort, VisionDescriberPort

VisionAdapterFactory = Callable[..., VisionDescriberPort]


class ExtractorRegistry:
    def __init__(self) -> None:
        self._by_ext: dict[str, ImageExtractorPort] = {}

    def register(self, extractor: ImageExtractorPort) -> None:
        for ext in extractor.supported_extensions:
            key = ext.lower().lstrip(".")
            if key in self._by_ext:
                raise ValueError(f"extractor for '{key}' already registered")
            self._by_ext[key] = extractor

    def supported(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_ext))

    def resolve(self, filename: str) -> ImageExtractorPort:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        try:
            return self._by_ext[ext]
        except KeyError:
            raise UnsupportedFormatError(ext, self.supported()) from None


class VisionAdapterRegistry:
    def __init__(self) -> None:
        self._by_provider: dict[str, VisionAdapterFactory] = {}

    def register(
        self, factory: VisionAdapterFactory, keys: tuple[str, ...] | None = None
    ) -> None:
        """keys 생략 시 factory.provider 를 키로 쓴다(클래스 속성)."""
        for key in keys or (getattr(factory, "provider"),):
            if key in self._by_provider:
                raise ValueError(f"vision adapter for '{key}' already registered")
            self._by_provider[key] = factory

    def supported(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_provider))

    def build(self, provider: str, **kwargs: Any) -> VisionDescriberPort:
        try:
            factory = self._by_provider[provider]
        except KeyError:
            raise UnsupportedVisionProviderError(provider, self.supported()) from None
        return factory(**kwargs)
