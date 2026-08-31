"""AnthropicVisionAdapter — Anthropic source.base64 블록.

Design Ref: multimodal-extractor §9.5.
"""

import base64

from src.domain.multimodal.interfaces import DescribeOptions
from src.domain.multimodal.value_objects import ImageCandidate
from src.infrastructure.multimodal.vision.base_vision_adapter import BaseVisionAdapter


class AnthropicVisionAdapter(BaseVisionAdapter):
    provider = "anthropic"

    def build_image_block(
        self, image: ImageCandidate, options: DescribeOptions
    ) -> dict:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.mime,
                "data": base64.b64encode(image.image_bytes).decode("ascii"),
            },
        }
