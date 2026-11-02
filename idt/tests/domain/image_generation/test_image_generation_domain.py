"""image_generation 도메인 — image-generation-tool Design §3.1 / §8.2 #1·#2·#3."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.domain.image_generation.exceptions import (
    ImageTurnCapExceededError,
    InvalidImageRequestError,
)
from src.domain.image_generation.policies import ImageGenerationPolicy
from src.domain.image_generation.schemas import ImageRequestDraft
from src.domain.image_generation.tool_config import ImageGenerationToolConfig
from src.domain.image_generation.value_objects import (
    GenerationMode,
    ImageQuality,
    ImageSize,
)


class TestValidatePrompt:
    def test_strips_whitespace(self) -> None:
        assert ImageGenerationPolicy.validate_prompt("  배너  \n", max_chars=100) == "배너"

    @pytest.mark.parametrize("bad", ["", "   ", "\n"])
    def test_empty_raises(self, bad: str) -> None:
        with pytest.raises(InvalidImageRequestError):
            ImageGenerationPolicy.validate_prompt(bad, max_chars=100)

    def test_over_limit_raises(self) -> None:
        with pytest.raises(InvalidImageRequestError):
            ImageGenerationPolicy.validate_prompt("x" * 101, max_chars=100)


class TestTurnCap:
    def test_under_and_at_limit(self) -> None:
        ImageGenerationPolicy.check_turn_cap(0, max_per_turn=4)
        ImageGenerationPolicy.check_turn_cap(3, max_per_turn=4)

    def test_at_or_over_limit_raises(self) -> None:
        with pytest.raises(ImageTurnCapExceededError):
            ImageGenerationPolicy.check_turn_cap(4, max_per_turn=4)
        with pytest.raises(ImageTurnCapExceededError):
            ImageGenerationPolicy.check_turn_cap(5, max_per_turn=4)

    def test_sub_agent_cap_is_half_with_floor_one(self) -> None:
        assert ImageGenerationPolicy.sub_agent_cap(4) == 2
        assert ImageGenerationPolicy.sub_agent_cap(1) == 1
        assert ImageGenerationPolicy.sub_agent_cap(0) == 1


class TestResolveMode:
    def test_edit_with_attachment_stays_edit(self) -> None:
        assert ImageGenerationPolicy.resolve_mode(GenerationMode.EDIT, has_attachment=True) == (
            GenerationMode.EDIT, False,
        )

    def test_edit_without_attachment_falls_back(self) -> None:
        assert ImageGenerationPolicy.resolve_mode(GenerationMode.EDIT, has_attachment=False) == (
            GenerationMode.GENERATE, True,
        )

    def test_generate_never_falls_back(self) -> None:
        assert ImageGenerationPolicy.resolve_mode(GenerationMode.GENERATE, has_attachment=True) == (
            GenerationMode.GENERATE, False,
        )


class TestOutputFilename:
    def test_format(self) -> None:
        name = ImageGenerationPolicy.output_filename(datetime(2026, 10, 30, 15, 30, 12, tzinfo=timezone.utc))
        assert name.startswith("generated-20261030-153012-")
        assert name.endswith(".png")
        assert len(name) == len("generated-20261030-153012-") + 6 + 4

    def test_extension_follows_mime(self) -> None:
        # Analysis G-I3: 어댑터가 JPEG/WEBP 를 돌려주면 파일명 확장자도 맞춘다
        now = datetime(2026, 10, 30, 15, 30, 12, tzinfo=timezone.utc)
        assert ImageGenerationPolicy.output_filename(now, mime="image/jpeg").endswith(".jpg")
        assert ImageGenerationPolicy.output_filename(now, mime="image/webp").endswith(".webp")
        assert ImageGenerationPolicy.output_filename(now, mime="image/png").endswith(".png")
        assert ImageGenerationPolicy.output_filename(now, mime="application/x-unknown").endswith(".png")


class TestToolConfig:
    def test_defaults(self) -> None:
        cfg = ImageGenerationToolConfig(llm_model_id="m1")
        assert cfg.default_size == "1024x1024" and cfg.quality == "standard"
        assert cfg.model_dump() == {"llm_model_id": "m1", "default_size": "1024x1024", "quality": "standard"}

    def test_empty_model_raises(self) -> None:
        with pytest.raises(ValueError):
            ImageGenerationToolConfig(llm_model_id="")

    @pytest.mark.parametrize("size", ["512x512", "", "1024"])
    def test_bad_size_raises(self, size: str) -> None:
        with pytest.raises(ValueError):
            ImageGenerationToolConfig(llm_model_id="m", default_size=size)

    def test_bad_quality_raises(self) -> None:
        with pytest.raises(ValueError):
            ImageGenerationToolConfig(llm_model_id="m", quality="ultra")

    def test_roundtrip_from_dict(self) -> None:
        cfg = ImageGenerationToolConfig(**{"llm_model_id": "m", "default_size": "1536x1024", "quality": "hd"})
        assert cfg.default_size == ImageSize.LANDSCAPE_1536.value and cfg.quality == ImageQuality.HD.value


class TestImageRequestDraft:
    def test_valid(self) -> None:
        d = ImageRequestDraft(
            prompt="p", size="1024x1024", quality="standard", mode="edit",
            source_image_index=0, reason="r",
        )
        assert d.mode == "edit" and d.source_image_index == 0

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ImageRequestDraft(
                prompt="p", size="1024x1024", quality="standard", mode="generate",
                source_image_index=None, reason="r", extra="x",
            )

    def test_literal_enforced(self) -> None:
        with pytest.raises(ValidationError):
            ImageRequestDraft(
                prompt="p", size="999x999", quality="standard", mode="generate",
                source_image_index=None, reason="r",
            )
