"""썸네일 생성 (PyMuPDF Pixmap).

Design Ref: multimodal-extractor §4.2 preview — 원본 image_bytes 는 외부 노출 금지,
긴 변 ≤ max_side 의 PNG 썸네일만 base64 로 내보낸다 (Design §7).
"""

import base64

import fitz


def thumbnail_b64(image_bytes: bytes, max_side: int = 256) -> str | None:
    """디코딩 실패 시 None (미리보기는 썸네일 없이도 성립한다)."""
    try:
        pix = fitz.Pixmap(image_bytes)
        if pix.n - pix.alpha >= 4:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        longest = max(pix.width, pix.height)
        if longest > max_side:
            scale = max_side / longest
            pix = fitz.Pixmap(
                pix, int(pix.width * scale) or 1, int(pix.height * scale) or 1, None
            )
        return base64.b64encode(pix.tobytes("png")).decode("ascii")
    except Exception:  # noqa: BLE001 — 썸네일 실패는 치명적이지 않다
        return None
