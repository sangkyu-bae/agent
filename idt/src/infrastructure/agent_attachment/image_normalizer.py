"""PilImageNormalizer — 업로드 이미지 리사이즈·EXIF 방향·메타 제거.

Design Ref: chat-image-attachment §3.1 / §7 / D-07
- 긴 변이 max_edge_px 초과면 비율 유지 축소. 결과가 원본보다 크면 원본 유지.
- EXIF Orientation 은 반영하고 메타데이터는 재인코딩으로 제거한다.
- png/webp 는 알파 보존, jpeg 는 RGB + quality.
- 디코딩 폭탄은 PIL MAX_IMAGE_PIXELS 로 차단 → InvalidAttachmentError.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

from src.domain.agent_attachment.exceptions import InvalidAttachmentError
from src.domain.agent_attachment.value_objects import ImageDimensions

_FORMAT_BY_MIME = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
_MIME_BY_FORMAT = {v: k for k, v in _FORMAT_BY_MIME.items()}
_EXIF_ORIENTATION = 0x0112


class PilImageNormalizer:
    def __init__(self, max_pixels: int) -> None:
        self._max_pixels = max_pixels

    def normalize(
        self, data: bytes, *, max_edge_px: int, jpeg_quality: int
    ) -> tuple[bytes, ImageDimensions]:
        img, fmt = self._open(data)
        with img:
            mime = _MIME_BY_FORMAT[fmt]
            original_size = img.size
            # Pillow 12 의 exif_transpose 는 방향 태그가 없어도 복사본을 돌려주므로
            # 태그를 직접 읽어 "변경 필요" 여부를 판정한다.
            needs_transpose = img.getexif().get(_EXIF_ORIENTATION, 1) not in (None, 1)
            oriented = (ImageOps.exif_transpose(img) or img) if needs_transpose else img
            needs_resize = max(oriented.size) > max_edge_px
            if not needs_resize and not needs_transpose:
                # 회전·축소 불필요 → 원본 그대로 (재인코딩 비용·품질 손실 없음)
                return data, ImageDimensions(*original_size, mime)
            if needs_resize:
                oriented.thumbnail((max_edge_px, max_edge_px), Image.Resampling.LANCZOS)
            out = self._encode(oriented, fmt, jpeg_quality)
            if len(out) > len(data):
                # D-07: 재인코딩이 더 크면 원본 유지
                return data, ImageDimensions(*original_size, mime)
            return out, ImageDimensions(*oriented.size, mime)

    def _open(self, data: bytes) -> tuple[Image.Image, str]:
        prev = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = self._max_pixels
        try:
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()  # 구조 검증 (verify 후 재오픈 필요)
            img = Image.open(io.BytesIO(data))
            img.load()
            fmt = img.format or ""
            if fmt not in _MIME_BY_FORMAT:
                img.close()
                raise InvalidAttachmentError(
                    f"지원하지 않는 이미지 포맷입니다: {fmt}"
                )
            return img, fmt
        except (
            UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError,
        ) as e:
            raise InvalidAttachmentError(f"이미지를 읽을 수 없습니다: {e}") from e
        finally:
            Image.MAX_IMAGE_PIXELS = prev

    def _encode(self, img: Image.Image, fmt: str, jpeg_quality: int) -> bytes:
        buf = io.BytesIO()
        if fmt == "JPEG":
            img.convert("RGB").save(
                buf, format="JPEG", quality=jpeg_quality, optimize=True
            )
        elif fmt == "PNG":
            img.save(buf, format="PNG", optimize=True)
        else:
            img.save(buf, format="WEBP", quality=jpeg_quality)
        return buf.getvalue()
