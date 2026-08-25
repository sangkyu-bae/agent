"""SampleExtractorRegistry — 확장자 키 해석 (Design §2.2 / ExtractorRegistry 동형)."""

import pytest
from src.application.blueprint.registries import SampleExtractorRegistry
from src.domain.blueprint.errors import UnsupportedSampleFormatError


class _Pdf:
    supported_extensions = ("pdf",)

    def extract(self, data, filename, max_pages):
        return "pdf-stats"


class _Pptx:
    supported_extensions = ("pptx", "ppt")

    def extract(self, data, filename, max_pages):
        return "pptx-stats"


def test_resolve_by_extension_case_insensitive():
    reg = SampleExtractorRegistry()
    reg.register(_Pdf())
    reg.register(_Pptx())
    assert reg.resolve("a.PDF").extract(b"", "a.PDF", 1) == "pdf-stats"
    assert reg.resolve("deck.pptx").extract(b"", "deck.pptx", 1) == "pptx-stats"
    assert reg.supported == ("pdf", "ppt", "pptx")


def test_unsupported_raises_with_supported_list():
    reg = SampleExtractorRegistry()
    reg.register(_Pdf())
    with pytest.raises(UnsupportedSampleFormatError) as ei:
        reg.resolve("x.docx")
    assert ei.value.extension == "docx" and ei.value.supported == ("pdf",)
    with pytest.raises(UnsupportedSampleFormatError):
        reg.resolve("noext")


def test_duplicate_extension_registration_is_rejected():
    reg = SampleExtractorRegistry()
    reg.register(_Pdf())
    with pytest.raises(ValueError):
        reg.register(_Pdf())
