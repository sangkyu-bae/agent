"""CreateLlmModelUseCase 테스트."""
import pytest

from src.application.llm_model.create_llm_model_use_case import (
    CreateLlmModelUseCase,
)
from src.application.llm_model.schemas import CreateLlmModelRequest

from tests.application.llm_model.conftest import InMemoryLlmModelRepository


@pytest.mark.asyncio
async def test_create_llm_model_success(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    use_case = CreateLlmModelUseCase(repository=repo, logger=mock_logger)
    req = CreateLlmModelRequest(
        provider="anthropic",
        model_name="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        api_key_env="ANTHROPIC_API_KEY",
        max_tokens=200000,
    )
    resp = await use_case.execute(req, request_id="req-1")

    assert resp.provider == "anthropic"
    assert resp.model_name == "claude-sonnet-4-6"
    assert resp.is_active is True
    assert resp.is_default is False
    # DB 저장 확인
    saved = await repo.find_by_id(resp.id, "req-1")
    assert saved is not None
    assert saved.model_name == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_create_llm_model_duplicate_fails(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    use_case = CreateLlmModelUseCase(repository=repo, logger=mock_logger)
    req = CreateLlmModelRequest(
        provider=seeded_model.provider,
        model_name=seeded_model.model_name,
        display_name="dup",
        api_key_env="OPENAI_API_KEY",
    )
    with pytest.raises(ValueError, match="이미 등록된 모델"):
        await use_case.execute(req, request_id="req-2")


@pytest.mark.asyncio
async def test_set_default_unsets_previous(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    # seeded_model은 is_default=True
    assert seeded_model.is_default is True

    use_case = CreateLlmModelUseCase(repository=repo, logger=mock_logger)
    req = CreateLlmModelRequest(
        provider="openai",
        model_name="gpt-4o-mini",
        display_name="GPT-4o Mini",
        api_key_env="OPENAI_API_KEY",
        is_default=True,
    )
    new_resp = await use_case.execute(req, request_id="req-3")

    # 기존 기본 모델은 해제, 새 모델이 기본
    assert new_resp.is_default is True
    previous = await repo.find_by_id(seeded_model.id, "req-3")
    assert previous is not None
    assert previous.is_default is False


@pytest.mark.asyncio
async def test_create_rejects_empty_model_name(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    use_case = CreateLlmModelUseCase(repository=repo, logger=mock_logger)
    # Pydantic은 빈 문자열을 허용하므로 Policy가 막아야 함
    req = CreateLlmModelRequest(
        provider="openai",
        model_name="   ",
        display_name="x",
        api_key_env="OPENAI_API_KEY",
    )
    with pytest.raises(ValueError, match="빈 문자열"):
        await use_case.execute(req, request_id="req-4")
