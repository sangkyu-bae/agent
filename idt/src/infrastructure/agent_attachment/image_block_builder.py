"""VendorImageBlockBuilder — LLM provider 별 이미지 content block.

Design Ref: chat-image-attachment §3.3 / D-08
- 포맷은 기존 비전 어댑터(infrastructure/multimodal/vision/*)와 동일하다.
  어댑터는 LLM 인스턴스를 생성하는 무거운 객체라 포맷만 떼어 가벼운 빌더로 둔다.
  두 곳의 동치는 tests/infrastructure/agent_attachment/
  test_image_block_builder.py 가 고정한다.
- provider 키 = LlmModel.provider 문자열 (vision 레지스트리와 동일 키).
"""
from __future__ import annotations

import base64
from pathlib import Path


class VendorImageBlockBuilder:
    _OPENAI_WITH_DETAIL = frozenset({"openai"})
    _OPENAI_COMPATIBLE = frozenset({"openai_compatible", "ollama"})
    _ANTHROPIC = frozenset({"anthropic"})

    def supports(self, provider: str) -> bool:
        return provider in (
            self._OPENAI_WITH_DETAIL | self._OPENAI_COMPATIBLE | self._ANTHROPIC
        )

    def build(self, provider: str, *, mime: str, data: bytes, detail: str) -> dict:
        b64 = base64.b64encode(data).decode("ascii")
        if provider in self._OPENAI_WITH_DETAIL:
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}", "detail": detail},
            }
        if provider in self._OPENAI_COMPATIBLE:
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        if provider in self._ANTHROPIC:
            return {
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            }
        raise ValueError(f"이미지 입력을 지원하지 않는 provider 입니다: {provider!r}")

    def build_from_path(
        self, provider: str, *, mime: str, path: str, detail: str
    ) -> dict:
        return self.build(provider, mime=mime, data=Path(path).read_bytes(), detail=detail)
