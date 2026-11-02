"""채팅·비전 모델 후보는 model_kind=chat 만 — image-generation-tool Design §4.2 / §8.2 #13·#14.

이미지 생성 모델이 에이전트 모델·비전 모델로 연결되지 않도록 서버가 막는다.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
from src.application.multimodal.settings_use_case import MultimodalSettingsUseCase
from src.domain.llm_model.entity import LlmModel


def _model(kind: str, **over) -> LlmModel:
    now = datetime.now(timezone.utc)
    base = dict(
        id=f"m-{kind}", provider="openai", model_name="x", display_name=f"X-{kind}",
        description=None, api_key_env="K", max_tokens=None, is_active=True,
        is_default=False, created_at=now, updated_at=now, model_kind=kind,
        supports_vision=True,
    )
    base.update(over)
    return LlmModel(**base)


def _repo(model: LlmModel | None) -> MagicMock:
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=model)
    repo.find_default = AsyncMock(return_value=_model("chat", id="default"))
    return repo


class TestCreateAgent:
    @pytest.mark.asyncio
    async def test_image_model_rejected(self) -> None:
        uc = CreateAgentUseCase.__new__(CreateAgentUseCase)
        uc._llm_model_repository = _repo(_model("image"))
        with pytest.raises(ValueError) as ei:
            await uc._resolve_llm_model_id("m-image", "r")
        assert "X-image" in str(ei.value)

    @pytest.mark.asyncio
    async def test_chat_model_accepted(self) -> None:
        uc = CreateAgentUseCase.__new__(CreateAgentUseCase)
        uc._llm_model_repository = _repo(_model("chat"))
        assert await uc._resolve_llm_model_id("m-chat", "r") == "m-chat"


class TestUpdateAgent:
    @pytest.mark.asyncio
    async def test_image_model_rejected(self) -> None:
        uc = UpdateAgentUseCase.__new__(UpdateAgentUseCase)
        uc._llm_model_repo = _repo(_model("image"))
        with pytest.raises(ValueError):
            await uc._validate_llm_model("m-image", "r")


class TestMultimodalVisionModel:
    @pytest.mark.asyncio
    async def test_image_kind_not_vision_capable(self) -> None:
        from src.application.multimodal.settings_use_case import VisionModelNotCapableError

        uc = MultimodalSettingsUseCase.__new__(MultimodalSettingsUseCase)
        uc._llm_model_repo = _repo(_model("image"))
        with pytest.raises(VisionModelNotCapableError):
            await uc._validate_model("m-image", "r")
