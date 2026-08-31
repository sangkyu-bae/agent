"""ExtractorRegistry / VisionAdapterRegistry — Design §9.5, FR-17."""

import pytest
from src.application.multimodal.registries import (
    ExtractorRegistry,
    VisionAdapterRegistry,
)
from src.domain.multimodal.errors import (
    UnsupportedFormatError,
    UnsupportedVisionProviderError,
)


class _PdfExtractor:
    supported_extensions = frozenset({"pdf"})

    def extract(self, file_bytes, filename, analysis):
        return []


class _Adapter:
    provider = "fake"

    def __init__(self, llm_factory, llm_model, logger, callbacks=None):
        self.args = (llm_factory, llm_model, logger, callbacks)

    async def describe(self, image, element_type, options):
        raise NotImplementedError


def test_extractor_registry_resolves_by_lowercase_extension():
    reg = ExtractorRegistry()
    ex = _PdfExtractor()
    reg.register(ex)
    assert reg.resolve("Report.PDF") is ex
    assert reg.supported() == ("pdf",)


def test_extractor_registry_unknown_extension_raises_with_supported_list():
    reg = ExtractorRegistry()
    reg.register(_PdfExtractor())
    with pytest.raises(UnsupportedFormatError) as ei:
        reg.resolve("slides.pptx")
    assert ei.value.extension == "pptx" and ei.value.supported == ("pdf",)


def test_extractor_registry_filename_without_extension():
    reg = ExtractorRegistry()
    reg.register(_PdfExtractor())
    with pytest.raises(UnsupportedFormatError):
        reg.resolve("noext")


def test_vision_registry_register_under_multiple_keys_and_build():
    reg = VisionAdapterRegistry()
    reg.register(_Adapter, keys=("ollama", "openai_compatible"))
    assert reg.supported() == ("ollama", "openai_compatible")
    built = reg.build("ollama", llm_factory="F", llm_model="M", logger="L")
    assert isinstance(built, _Adapter) and built.args == ("F", "M", "L", None)


def test_vision_registry_default_key_is_adapter_provider():
    reg = VisionAdapterRegistry()
    reg.register(_Adapter)
    assert reg.supported() == ("fake",)


def test_vision_registry_unknown_provider_raises():
    reg = VisionAdapterRegistry()
    reg.register(_Adapter)
    with pytest.raises(UnsupportedVisionProviderError) as ei:
        reg.build("gemini", llm_factory=None, llm_model=None, logger=None)
    assert ei.value.provider == "gemini"


def test_vision_registry_rejects_duplicate_key():
    reg = VisionAdapterRegistry()
    reg.register(_Adapter)
    with pytest.raises(ValueError):
        reg.register(_Adapter)
