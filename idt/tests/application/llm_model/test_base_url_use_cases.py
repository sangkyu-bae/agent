"""LLM-MODEL-REG-002: Create/Update UseCase base_url 왕복 + Response 노출."""
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


@pytest.mark.asyncio
async def test_create_with_base_url(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    use_case = CreateLlmModelUseCase(repository=repo, logger=mock_logger)
    req = CreateLlmModelRequest(
        provider="openai",
        model_name="Qwen2.5-32B-Instruct",
        display_name="사내 Qwen",
        api_key_env="QWEN_API_KEY",
        base_url="http://10.0.0.5:8000/v1",
    )
    resp = await use_case.execute(req, request_id="req-1")

    assert resp.base_url == "http://10.0.0.5:8000/v1"
    saved = await repo.find_by_id(resp.id, "req-1")
    assert saved.base_url == "http://10.0.0.5:8000/v1"


@pytest.mark.asyncio
async def test_create_without_base_url_is_none(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    use_case = CreateLlmModelUseCase(repository=repo, logger=mock_logger)
    req = CreateLlmModelRequest(
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        api_key_env="OPENAI_API_KEY",
    )
    resp = await use_case.execute(req, request_id="req-1")

    assert resp.base_url is None


@pytest.mark.asyncio
async def test_update_base_url(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    use_case = UpdateLlmModelUseCase(repository=repo, logger=mock_logger)
    req = UpdateLlmModelRequest(base_url="http://10.0.0.7:8000/v1")

    resp = await use_case.execute(seeded_model.id, req, request_id="req-2")

    assert resp.base_url == "http://10.0.0.7:8000/v1"


@pytest.mark.asyncio
async def test_update_empty_base_url_normalized_to_none(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    """빈 문자열 전송 시 self-host 해제 → None 정규화 (R3)."""
    seeded_model.base_url = "http://10.0.0.7:8000/v1"
    use_case = UpdateLlmModelUseCase(repository=repo, logger=mock_logger)
    req = UpdateLlmModelRequest(base_url="")

    resp = await use_case.execute(seeded_model.id, req, request_id="req-3")

    assert resp.base_url is None
