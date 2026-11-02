"""ImageGeneratorRegistry — provider 키 → 어댑터 팩토리 (Design §4.3 / D-06).

VisionAdapterRegistry 동형. 어댑터 1개 추가 = 파일 1개 + register() 1줄.
"""
from collections.abc import Callable
from typing import Any

from src.domain.image_generation.exceptions import UnsupportedImageProviderError
from src.domain.image_generation.interfaces import ImageGeneratorPort

ImageGeneratorFactory = Callable[..., ImageGeneratorPort]


class ImageGeneratorRegistry:
    def __init__(self) -> None:
        self._by_provider: dict[str, ImageGeneratorFactory] = {}

    def register(
        self, factory: ImageGeneratorFactory, keys: tuple[str, ...] | None = None
    ) -> None:
        """keys 생략 시 factory.provider 를 키로 쓴다(클래스 속성)."""
        for key in keys or (getattr(factory, "provider"),):
            if key in self._by_provider:
                raise ValueError(f"image generator for '{key}' already registered")
            self._by_provider[key] = factory

    def supported(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_provider))

    def build(self, provider: str, **kwargs: Any) -> ImageGeneratorPort:
        try:
            factory = self._by_provider[provider]
        except KeyError:
            raise UnsupportedImageProviderError(provider, self.supported()) from None
        return factory(**kwargs)
