"""thumbnail_b64 — Design §4.2/§7: 긴 변 ≤ max_side PNG, 실패 시 None."""

import base64

import fitz
from src.infrastructure.multimodal.thumbnail import thumbnail_b64


def _png(w: int, h: int) -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h), False)
    pix.clear_with(120)
    return pix.tobytes("png")


def _decode(b64: str) -> fitz.Pixmap:
    return fitz.Pixmap(base64.b64decode(b64))


def test_downscales_long_side_to_max_side_keeping_aspect():
    out = thumbnail_b64(_png(1200, 600), max_side=256)
    assert out is not None
    pix = _decode(out)
    assert pix.width == 256 and 120 <= pix.height <= 130


def test_small_image_is_not_upscaled():
    out = thumbnail_b64(_png(100, 80), max_side=256)
    assert out is not None
    pix = _decode(out)
    assert (pix.width, pix.height) == (100, 80)


def test_output_is_png_base64():
    raw = base64.b64decode(thumbnail_b64(_png(300, 300)) or "")
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_undecodable_bytes_return_none():
    assert thumbnail_b64(b"not an image") is None
