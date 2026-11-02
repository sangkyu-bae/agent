"""model_kind·price_per_image_usd CRUD — image-generation-tool Design §4.1 / §8.2 #12."""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.application.llm_model.create_llm_model_use_case import CreateLlmModelUseCase
from src.application.llm_model.schemas import (
    CreateLlmModelRequest,
    LlmModelResponse,
    UpdateLlmModelRequest,
    UpdatePricingRequest,
)
from src.application.llm_model.update_llm_model_pricing_use_case import (
    UpdateLlmModelPricingUseCase,
)
from src.application.llm_model.update_llm_model_use_case import UpdateLlmModelUseCase

from tests.application.llm_model.conftest import InMemoryLlmModelRepository


def _image_request(**over) -> CreateLlmModelRequest:
    base = dict(
        provider="openai", model_name="gpt-image-1", display_name="GPT Image 1",
        api_key_env="OPENAI_API_KEY", model_kind="image",
        price_per_image_usd=Decimal("0.0400"),
    )
    base.update(over)
    return CreateLlmModelRequest(**base)


@pytest.mark.asyncio
async def test_create_image_model_persists_kind_and_price(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    uc = CreateLlmModelUseCase(repository=repo, logger=mock_logger)
    resp = await uc.execute(_image_request(), request_id="r")
    assert resp.model_kind == "image"
    assert resp.price_per_image_usd == Decimal("0.0400")
    saved = await repo.find_by_id(resp.id, "r")
    assert saved is not None and saved.model_kind == "image"


@pytest.mark.asyncio
async def test_create_defaults_to_chat_kind(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    uc = CreateLlmModelUseCase(repository=repo, logger=mock_logger)
    resp = await uc.execute(
        CreateLlmModelRequest(
            provider="openai", model_name="gpt-4o", display_name="g",
            api_key_env="OPENAI_API_KEY",
        ),
        request_id="r",
    )
    assert resp.model_kind == "chat" and resp.price_per_image_usd is None


@pytest.mark.asyncio
async def test_create_image_model_as_default_rejected(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    uc = CreateLlmModelUseCase(repository=repo, logger=mock_logger)
    with pytest.raises(ValueError):
        await uc.execute(_image_request(is_default=True), request_id="r")


def test_create_request_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        CreateLlmModelRequest(
            provider="openai", model_name="x", display_name="x",
            api_key_env="K", model_kind="audio",
        )


@pytest.mark.asyncio
async def test_update_can_change_kind_and_price(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    seeded_model.is_default = False  # 기본 모델은 image 로 바꿀 수 없다 (별도 테스트)
    await repo.update(seeded_model, "r")
    uc = UpdateLlmModelUseCase(repository=repo, logger=mock_logger)
    resp = await uc.execute(
        seeded_model.id,
        UpdateLlmModelRequest(model_kind="image", price_per_image_usd=Decimal("0.08")),
        request_id="r",
    )
    assert resp.model_kind == "image"
    assert resp.price_per_image_usd == Decimal("0.08")


@pytest.mark.asyncio
async def test_update_default_model_to_image_rejected(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    seeded_model.is_default = True
    await repo.update(seeded_model, "r")
    uc = UpdateLlmModelUseCase(repository=repo, logger=mock_logger)
    with pytest.raises(ValueError):
        await uc.execute(seeded_model.id, UpdateLlmModelRequest(model_kind="image"), request_id="r")


@pytest.mark.asyncio
async def test_pricing_update_accepts_image_price(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    cost_calc = MagicMock()
    uc = UpdateLlmModelPricingUseCase(repository=repo, cost_calculator=cost_calc, logger=mock_logger)
    resp = await uc.execute(
        seeded_model.id,
        UpdatePricingRequest(
            input_price_per_1k_usd=Decimal("0.001"), output_price_per_1k_usd=Decimal("0.002"),
            price_per_image_usd=Decimal("0.05"),
        ),
        request_id="r",
    )
    assert resp.price_per_image_usd == Decimal("0.05")
    cost_calc.invalidate.assert_called_once_with(seeded_model.id)


@pytest.mark.asyncio
async def test_pricing_update_without_image_price_keeps_existing(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    seeded_model.price_per_image_usd = Decimal("0.03")
    await repo.update(seeded_model, "r")
    uc = UpdateLlmModelPricingUseCase(repository=repo, cost_calculator=MagicMock(), logger=mock_logger)
    resp = await uc.execute(
        seeded_model.id,
        UpdatePricingRequest(input_price_per_1k_usd=Decimal("0"), output_price_per_1k_usd=Decimal("0")),
        request_id="r",
    )
    assert resp.price_per_image_usd == Decimal("0.03")


def test_response_exposes_fields(seeded_model) -> None:
    seeded_model.model_kind = "image"
    seeded_model.price_per_image_usd = Decimal("0.04")
    resp = LlmModelResponse.from_domain(seeded_model)
    assert resp.model_kind == "image" and resp.price_per_image_usd == Decimal("0.04")
