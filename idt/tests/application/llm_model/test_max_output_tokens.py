"""claude-agent-e2e-fixes Design §3.2 (L1·L2): max_output_tokens DTO·유스케이스·캐시 관통."""
import pytest
from pydantic import ValidationError

from src.application.llm_model.create_llm_model_use_case import CreateLlmModelUseCase
from src.application.llm_model.schemas import CreateLlmModelRequest, UpdateLlmModelRequest
from src.application.llm_model.update_llm_model_use_case import UpdateLlmModelUseCase
from src.application.llm_model.utility_llm_provider import _from_cache_dict, _to_cache_dict

from tests.application.llm_model.conftest import InMemoryLlmModelRepository


def _req(**over) -> CreateLlmModelRequest:
    base = dict(
        provider="anthropic", model_name="claude-opus-5-5",
        display_name="Opus 5.5", api_key_env="ANTHROPIC_API_KEY",
    )
    base.update(over)
    return CreateLlmModelRequest(**base)


@pytest.mark.asyncio
async def test_create_defaults_to_none(repo: InMemoryLlmModelRepository, mock_logger) -> None:
    resp = await CreateLlmModelUseCase(repo, mock_logger).execute(_req(), "r")
    assert resp.max_output_tokens is None


@pytest.mark.asyncio
async def test_create_with_value(repo: InMemoryLlmModelRepository, mock_logger) -> None:
    resp = await CreateLlmModelUseCase(repo, mock_logger).execute(_req(max_output_tokens=32000), "r")
    assert resp.max_output_tokens == 32000
    assert (await repo.find_by_id(resp.id, "r")).max_output_tokens == 32000


@pytest.mark.asyncio
async def test_update_set_preserve_and_clear(repo: InMemoryLlmModelRepository, mock_logger) -> None:
    created = await CreateLlmModelUseCase(repo, mock_logger).execute(_req(), "r")
    uc = UpdateLlmModelUseCase(repo, mock_logger)
    assert (await uc.execute(created.id, UpdateLlmModelRequest(max_output_tokens=20000), "r")).max_output_tokens == 20000
    # 필드 미지정 → 보존
    assert (await uc.execute(created.id, UpdateLlmModelRequest(display_name="x"), "r")).max_output_tokens == 20000
    # 명시적 null → 기본값으로 되돌림 (비우고 저장)
    assert (await uc.execute(created.id, UpdateLlmModelRequest(max_output_tokens=None), "r")).max_output_tokens is None


@pytest.mark.parametrize("value", [0, -1, 128001])
def test_out_of_range_rejected(value) -> None:  # L1
    with pytest.raises(ValidationError):
        _req(max_output_tokens=value)
    with pytest.raises(ValidationError):
        UpdateLlmModelRequest(max_output_tokens=value)


def test_upper_bound_accepted() -> None:
    assert _req(max_output_tokens=128000).max_output_tokens == 128000


@pytest.mark.asyncio
async def test_utility_cache_round_trip(repo: InMemoryLlmModelRepository, mock_logger) -> None:  # L2
    created = await CreateLlmModelUseCase(repo, mock_logger).execute(_req(max_output_tokens=24000), "r")
    model = await repo.find_by_id(created.id, "r")
    data = _to_cache_dict(model)
    assert _from_cache_dict(data).max_output_tokens == 24000
    data.pop("max_output_tokens")  # 배포 전 캐시 항목 호환
    assert _from_cache_dict(data).max_output_tokens is None
