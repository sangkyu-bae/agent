"""VendorImageBlockBuilder 테스트 — chat-image-attachment Design §3.3 / §8.2 #5 / D-08."""
import base64

import pytest

from src.infrastructure.agent_attachment.image_block_builder import (
    VendorImageBlockBuilder,
)

DATA = b"\x89PNG\r\n\x1a\n-fake-"
B64 = base64.b64encode(DATA).decode("ascii")


@pytest.fixture
def builder() -> VendorImageBlockBuilder:
    return VendorImageBlockBuilder()


class TestSupports:
    @pytest.mark.parametrize("p", ["openai", "anthropic", "openai_compatible", "ollama"])
    def test_known_providers(self, builder, p: str) -> None:
        assert builder.supports(p) is True

    @pytest.mark.parametrize("p", ["gemini", "", "OPENAI"])
    def test_unknown_providers(self, builder, p: str) -> None:
        assert builder.supports(p) is False


class TestBuild:
    def test_openai_block_has_detail(self, builder) -> None:
        block = builder.build("openai", mime="image/png", data=DATA, detail="high")
        assert block == {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{B64}", "detail": "high"},
        }

    @pytest.mark.parametrize("p", ["openai_compatible", "ollama"])
    def test_compatible_block_omits_detail(self, builder, p: str) -> None:
        block = builder.build(p, mime="image/jpeg", data=DATA, detail="high")
        assert block == {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{B64}"},
        }

    def test_anthropic_block(self, builder) -> None:
        block = builder.build("anthropic", mime="image/webp", data=DATA, detail="high")
        assert block == {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/webp", "data": B64},
        }

    def test_unknown_provider_raises(self, builder) -> None:
        with pytest.raises(ValueError):
            builder.build("gemini", mime="image/png", data=DATA, detail="high")


class TestParityWithVisionAdapters:
    """D-08: 기존 비전 어댑터 포맷과 동치 — 두 곳의 포맷이 갈라지면 여기서 잡는다."""

    def test_openai_matches_vision_adapter(self, builder) -> None:
        from src.domain.multimodal.interfaces import DescribeOptions
        from src.domain.multimodal.value_objects import BBox, ElementType, ImageCandidate
        from src.infrastructure.multimodal.vision.openai_vision_adapter import (
            OpenAIVisionAdapter,
        )

        cand = ImageCandidate(
            page=1, bbox=BBox(0, 0, 1, 1), image_bytes=DATA, mime="image/png",
            width=1, height=1, area_ratio=1.0, sha256="x", hint_type=ElementType.FIGURE,
        )
        adapter_block = OpenAIVisionAdapter.build_image_block(
            object.__new__(OpenAIVisionAdapter), cand,
            DescribeOptions(output_language="ko", detail_level="detailed"),
        )
        assert builder.build("openai", mime="image/png", data=DATA, detail="high") == adapter_block

    def test_anthropic_matches_vision_adapter(self, builder) -> None:
        from src.domain.multimodal.interfaces import DescribeOptions
        from src.domain.multimodal.value_objects import BBox, ElementType, ImageCandidate
        from src.infrastructure.multimodal.vision.anthropic_vision_adapter import (
            AnthropicVisionAdapter,
        )

        cand = ImageCandidate(
            page=1, bbox=BBox(0, 0, 1, 1), image_bytes=DATA, mime="image/png",
            width=1, height=1, area_ratio=1.0, sha256="x", hint_type=ElementType.FIGURE,
        )
        adapter_block = AnthropicVisionAdapter.build_image_block(
            object.__new__(AnthropicVisionAdapter), cand,
            DescribeOptions(output_language="ko", detail_level="detailed"),
        )
        assert builder.build("anthropic", mime="image/png", data=DATA, detail="high") == adapter_block


class TestBuildFromPath:
    def test_reads_file_and_builds(self, builder, tmp_path) -> None:
        f = tmp_path / "a.png"
        f.write_bytes(DATA)
        block = builder.build_from_path("anthropic", mime="image/png", path=str(f), detail="high")
        assert block["source"]["data"] == B64

    def test_missing_file_raises_oserror(self, builder, tmp_path) -> None:
        with pytest.raises(OSError):
            builder.build_from_path("openai", mime="image/png", path=str(tmp_path / "nope.png"), detail="high")
