"""OpenAICompatibleVisionAdapter — vLLM/Ollama 등 OpenAI 호환 로컬 엔드포인트.

Design Ref: multimodal-extractor §9.5 — 이미지 블록은 OpenAI 포맷(detail 생략),
strict(json_schema) 미지원 서버가 많아 output_modes=("json", "text") 로
strict 를 제외한다.
레지스트리에는 "ollama" 와 "openai_compatible" 두 키로 등록된다(§9.5).
"""

import base64

from src.domain.multimodal.interfaces import DescribeOptions
from src.domain.multimodal.value_objects import ImageCandidate
from src.infrastructure.multimodal.vision.base_vision_adapter import BaseVisionAdapter


class OpenAICompatibleVisionAdapter(BaseVisionAdapter):
    provider = "openai_compatible"
    output_modes = ("json", "text")

    def build_image_block(
        self, image: ImageCandidate, options: DescribeOptions
    ) -> dict:
        b64 = base64.b64encode(image.image_bytes).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{image.mime};base64,{b64}"},
        }
