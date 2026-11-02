"""image_generate 설정 바인딩·모델 검증 — Design §4.2 / §8.2 #13."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.image_generation.binding import (
    IMAGE_CONFIG_INVALID,
    IMAGE_MODEL_INVALID,
    apply_image_generation_config,
    validate_image_generation_model,
)
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.agent_builder.tool_registry import TOOL_REGISTRY
from src.domain.llm_model.entity import LlmModel


def _worker(tool_id="image_generate") -> WorkerDefinition:
    return WorkerDefinition(tool_id=tool_id, worker_id=f"{tool_id}_worker", description="d", sort_order=0)


def _req(**over):
    base = dict(llm_model_id="img-1", default_size="1024x1024", quality="standard")
    base.update(over)
    return SimpleNamespace(**base)


def _model(kind="image", active=True) -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="img-1", provider="openai", model_name="gpt-image-1", display_name="GPT Image",
        description=None, api_key_env="K", max_tokens=None, is_active=active, is_default=False,
        created_at=now, updated_at=now, model_kind=kind,
    )


class TestToolRegistry:
    def test_image_generate_registered_as_action(self) -> None:
        meta = TOOL_REGISTRY["image_generate"]
        assert meta.name == "이미지 생성"
        assert str(meta.category) in ("action", "ToolCategory.ACTION") or meta.category is not None
        assert "이미지" in meta.description and "편집" in meta.description


class TestApplyConfig:
    def test_injects_tool_config(self) -> None:
        w = _worker()
        cfg = apply_image_generation_config(_req(quality="hd"), [w])
        assert w.tool_config == {"llm_model_id": "img-1", "default_size": "1024x1024", "quality": "hd"}
        assert cfg.quality == "hd"

    def test_no_worker_raises_config_invalid(self) -> None:
        with pytest.raises(ValueError) as ei:
            apply_image_generation_config(_req(), [_worker("tavily_search")])
        assert str(ei.value).startswith(IMAGE_CONFIG_INVALID)

    def test_bad_size_raises_config_invalid(self) -> None:
        with pytest.raises(ValueError) as ei:
            apply_image_generation_config(_req(default_size="2x2"), [_worker()])
        assert str(ei.value).startswith(IMAGE_CONFIG_INVALID)


class TestValidateModel:
    @pytest.mark.asyncio
    async def test_passes_for_active_image_model(self) -> None:
        w = _worker(); w.tool_config = {"llm_model_id": "img-1"}
        repo = MagicMock(); repo.find_by_id = AsyncMock(return_value=_model())
        await validate_image_generation_model([w], repo, "r")

    @pytest.mark.asyncio
    async def test_chat_model_rejected(self) -> None:
        w = _worker(); w.tool_config = {"llm_model_id": "img-1"}
        repo = MagicMock(); repo.find_by_id = AsyncMock(return_value=_model(kind="chat"))
        with pytest.raises(ValueError) as ei:
            await validate_image_generation_model([w], repo, "r")
        assert str(ei.value).startswith(IMAGE_MODEL_INVALID)

    @pytest.mark.asyncio
    async def test_missing_and_inactive_rejected(self) -> None:
        w = _worker(); w.tool_config = {"llm_model_id": "img-1"}
        repo = MagicMock(); repo.find_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError):
            await validate_image_generation_model([w], repo, "r")
        repo.find_by_id = AsyncMock(return_value=_model(active=False))
        with pytest.raises(ValueError):
            await validate_image_generation_model([w], repo, "r")

    @pytest.mark.asyncio
    async def test_no_worker_or_no_config_is_noop(self) -> None:
        repo = MagicMock(); repo.find_by_id = AsyncMock()
        await validate_image_generation_model([_worker("tavily_search")], repo, "r")
        await validate_image_generation_model([_worker()], repo, "r")  # tool_config None
        repo.find_by_id.assert_not_awaited()
