"""OpenAIVisionAdapter — OpenAI image_url 블록.

Design Ref: multimodal-extractor §9.5
— detail_level 을 image_url.detail(high/low)로 매핑.
"""

import base64

from src.domain.multimodal.interfaces import DescribeOptions
from src.domain.multimodal.value_objects import ImageCandidate
from src.infrastructure.multimodal.vision.base_vision_adapter import BaseVisionAdapter

_DETAIL = {"brief": "low", "detailed": "high"}


class OpenAIVisionAdapter(BaseVisionAdapter):
    provider = "openai"

    def build_image_block(
        self, image: ImageCandidate, options: DescribeOptions
    ) -> dict:
        b64 = base64.b64encode(image.image_bytes).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{image.mime};base64,{b64}",
                "detail": _DETAIL.get(options.detail_level, "high"),
            },
        }
