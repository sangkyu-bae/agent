"""multimodal-extractor Design §3.3/§4.1 (FR-11, FR-19): supports_vision DTO 관통."""

import pytest
from src.application.llm_model.create_llm_model_use_case import (
    CreateLlmModelUseCase,
)
from src.application.llm_model.schemas import (
    CreateLlmModelRequest,
    UpdateLlmModelRequest,
)
from src.application.llm_model.update_llm_model_use_case import (
    UpdateLlmModelUseCase,
)

from tests.application.llm_model.conftest import InMemoryLlmModelRepository


def _req(**over) -> CreateLlmModelRequest:
    base = dict(
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        api_key_env="OPENAI_API_KEY",
    )
    base.update(over)
    return CreateLlmModelRequest(**base)


@pytest.mark.asyncio
async def test_create_defaults_supports_vision_false(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    resp = await CreateLlmModelUseCase(repo, mock_logger).execute(_req(), "r")
    assert resp.supports_vision is False
    assert (await repo.find_by_id(resp.id, "r")).supports_vision is False


@pytest.mark.asyncio
async def test_create_with_supports_vision_true(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    resp = await CreateLlmModelUseCase(repo, mock_logger).execute(
        _req(supports_vision=True), "r"
    )
    assert resp.supports_vision is True
    assert (await repo.find_by_id(resp.id, "r")).supports_vision is True


@pytest.mark.asyncio
async def test_update_toggles_supports_vision(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    created = await CreateLlmModelUseCase(repo, mock_logger).execute(_req(), "r")
    uc = UpdateLlmModelUseCase(repo, mock_logger)
    resp = await uc.execute(
        created.id, UpdateLlmModelRequest(supports_vision=True), "r"
    )
    assert resp.supports_vision is True
    resp = await uc.execute(created.id, UpdateLlmModelRequest(display_name="x"), "r")
    assert resp.supports_vision is True  # 미지정 시 보존
    resp = await uc.execute(
        created.id, UpdateLlmModelRequest(supports_vision=False), "r"
    )
    assert resp.supports_vision is False
