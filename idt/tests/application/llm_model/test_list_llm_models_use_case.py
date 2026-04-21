"""ListLlmModelsUseCase 테스트."""
from datetime import datetime, timezone

import pytest

from src.application.llm_model.list_llm_models_use_case import (
    ListLlmModelsUseCase,
)
from src.domain.llm_model.entity import LlmModel

from tests.application.llm_model.conftest import InMemoryLlmModelRepository


@pytest.mark.asyncio
async def test_list_returns_only_active(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    # 비활성화 모델 1건 추가
    now = datetime.now(timezone.utc)
    inactive = LlmModel(
        id="inactive-1",
        provider="openai",
        model_name="gpt-3.5-turbo",
        display_name="GPT-3.5",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=False,
        is_default=False,
        created_at=now,
        updated_at=now,
    )
    await repo.save(inactive, "req-0")

    use_case = ListLlmModelsUseCase(repository=repo, logger=mock_logger)
    resp = await use_case.execute(include_inactive=False, request_id="req-1")

    ids = {m.id for m in resp.models}
    assert seeded_model.id in ids
    assert "inactive-1" not in ids


@pytest.mark.asyncio
async def test_list_all_includes_inactive(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    now = datetime.now(timezone.utc)
    inactive = LlmModel(
        id="inactive-2",
        provider="openai",
        model_name="gpt-3.5-turbo",
        display_name="GPT-3.5",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=False,
        is_default=False,
        created_at=now,
        updated_at=now,
    )
    await repo.save(inactive, "req-0")

    use_case = ListLlmModelsUseCase(repository=repo, logger=mock_logger)
    resp = await use_case.execute(include_inactive=True, request_id="req-1")

    ids = {m.id for m in resp.models}
    assert "inactive-2" in ids
    assert seeded_model.id in ids
