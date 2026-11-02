"""PilImageNormalizer 테스트 — chat-image-attachment Design §8.2 #3, #4."""
import io

import pytest
from PIL import Image

from src.domain.agent_attachment.exceptions import InvalidAttachmentError
from src.infrastructure.agent_attachment.image_normalizer import PilImageNormalizer


def _png(w: int, h: int, mode: str = "RGBA") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (w, h), (10, 20, 30, 128) if mode == "RGBA" else (10, 20, 30)).save(
        buf, format="PNG"
    )
    return buf.getvalue()


def _jpeg(w: int, h: int, orientation: int | None = None) -> bytes:
    img = Image.new("RGB", (w, h), (200, 100, 50))
    buf = io.BytesIO()
    if orientation is None:
        img.save(buf, format="JPEG", quality=90)
    else:
        exif = Image.Exif()
        exif[0x0112] = orientation  # Orientation
        img.save(buf, format="JPEG", quality=90, exif=exif.tobytes())
    return buf.getvalue()


def _webp(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (1, 2, 3)).save(buf, format="WEBP")
    return buf.getvalue()


@pytest.fixture
def norm() -> PilImageNormalizer:
    return PilImageNormalizer(max_pixels=40_000_000)


class TestResize:
    def test_long_edge_over_limit_is_downscaled_keeping_ratio(self, norm) -> None:
        out, dims = norm.normalize(_png(3000, 1000), max_edge_px=1568, jpeg_quality=90)
        assert (dims.width, dims.height) == (1568, 523)
        assert dims.mime == "image/png"
        with Image.open(io.BytesIO(out)) as im:
            assert im.size == (1568, 523)
            assert im.mode == "RGBA"  # 알파 보존

    def test_portrait_uses_height_as_long_edge(self, norm) -> None:
        _, dims = norm.normalize(_jpeg(500, 4000), max_edge_px=1000, jpeg_quality=90)
        assert (dims.width, dims.height) == (125, 1000)
        assert dims.mime == "image/jpeg"

    def test_small_image_returns_original_bytes(self, norm) -> None:
        src = _png(100, 80)
        out, dims = norm.normalize(src, max_edge_px=1568, jpeg_quality=90)
        assert out == src
        assert (dims.width, dims.height, dims.mime) == (100, 80, "image/png")

    def test_exif_orientation_is_applied(self, norm) -> None:
        # orientation 6 = 90° CW → 가로세로 뒤바뀜
        _, dims = norm.normalize(_jpeg(300, 100, orientation=6), max_edge_px=1568, jpeg_quality=90)
        assert (dims.width, dims.height) == (100, 300)

    def test_webp_roundtrip(self, norm) -> None:
        out, dims = norm.normalize(_webp(2000, 2000), max_edge_px=1000, jpeg_quality=90)
        assert dims.mime == "image/webp"
        with Image.open(io.BytesIO(out)) as im:
            assert im.format == "WEBP" and im.size == (1000, 1000)

    def test_result_larger_than_original_keeps_original(self, norm, monkeypatch) -> None:
        src = _jpeg(2000, 2000)
        # 재인코딩 결과를 인위적으로 부풀려 원본 유지 분기를 확인
        monkeypatch.setattr(
            PilImageNormalizer, "_encode", lambda self, im, fmt, q: src + b"\x00" * 10
        )
        out, dims = norm.normalize(src, max_edge_px=1000, jpeg_quality=90)
        assert out == src
        assert (dims.width, dims.height) == (2000, 2000)


class TestRejects:
    def test_corrupt_bytes_raise_invalid(self, norm) -> None:
        with pytest.raises(InvalidAttachmentError):
            norm.normalize(b"\x89PNG\r\n\x1a\n" + b"garbage" * 10, max_edge_px=1568, jpeg_quality=90)

    def test_decompression_bomb_raises_invalid(self) -> None:
        tiny = PilImageNormalizer(max_pixels=1000)
        with pytest.raises(InvalidAttachmentError):
            tiny.normalize(_png(100, 100), max_edge_px=1568, jpeg_quality=90)

    def test_exif_metadata_is_dropped(self, norm) -> None:
        out, _ = norm.normalize(_jpeg(2000, 1000, orientation=1), max_edge_px=1000, jpeg_quality=90)
        with Image.open(io.BytesIO(out)) as im:
            assert not im.getexif()
