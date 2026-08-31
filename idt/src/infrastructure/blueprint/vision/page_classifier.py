"""VisionPageClassifier — 페이지 PNG → PagePatternDraft (기존 비전 어댑터 재사용).

Design Ref: golden-sample-blueprint §9.3 / D8
- 어댑터의 describe_with(messages, schema) 와 build_image_block 만 사용한다.
- 페이지 PNG 를 ImageCandidate 로 감싸 벤더별 이미지 블록을 그대로 재사용.
"""

from __future__ import annotations

import hashlib
import struct

from src.domain.blueprint.interfaces import PageHints
from src.domain.blueprint.schemas import PagePatternDraft
from src.domain.multimodal.interfaces import DescribeOptions
from src.domain.multimodal.value_objects import BBox, ElementType, ImageCandidate
from src.infrastructure.blueprint.prompts import build_classify_messages


def _png_size(data: bytes) -> tuple[int, int]:
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return int(w), int(h)
    return 1, 1


class VisionPageClassifier:
    def __init__(self, adapter) -> None:
        self._adapter = adapter

    async def classify(
        self, page_png: bytes, hints: PageHints, language: str
    ) -> PagePatternDraft:
        w, h = _png_size(page_png)
        candidate = ImageCandidate(
            page=hints.page_number,
            bbox=BBox(0, 0, float(w), float(h)),
            image_bytes=page_png,
            mime="image/png",
            width=w,
            height=h,
            area_ratio=1.0,
            sha256=hashlib.sha256(page_png).hexdigest(),
            hint_type=ElementType.PAGE_SCAN,
        )
        options = DescribeOptions(language, "detailed")
        block = self._adapter.build_image_block(candidate, options)
        messages = build_classify_messages(hints, language, block)
        outcome = await self._adapter.describe_with(messages, PagePatternDraft)
        return outcome.draft
