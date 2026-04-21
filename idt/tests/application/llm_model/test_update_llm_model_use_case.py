"""UpdateLlmModelUseCase 테스트."""
from datetime import datetime, timezone

import pytest

from src.application.llm_model.schemas import UpdateLlmModelRequest
from src.application.llm_model.update_llm_model_use_case import (
    UpdateLlmModelUseCase,
)
from src.domain.llm_model.entity import LlmModel

from tests.application.llm_model.conftest import InMemoryLlmModelRepository


@pytest.mark.asyncio
async def test_update_display_name(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    use_case = UpdateLlmModelUseCase(repository=repo, logger=mock_logger)
    resp = await use_case.execute(
        seeded_model.id,
        UpdateLlmModelRequest(display_name="GPT-4o Pro"),
        request_id="req-1",
    )
    assert resp.display_name == "GPT-4o Pro"


@pytest.mark.asyncio
async def test_update_set_default_unsets_previous(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    # 두 번째 모델 등록 (비-default)
    now = datetime.now(timezone.utc)
    other = LlmModel(
        id="other-1",
        provider="openai",
        model_name="gpt-4o-mini",
        display_name="GPT-4o Mini",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
    )
    await repo.save(other, "req-0")

    use_case = UpdateLlmModelUseCase(repository=repo, logger=mock_logger)
    # other를 default로 변경
    resp = await use_case.execute(
        "other-1",
        UpdateLlmModelRequest(is_default=True),
        request_id="req-1",
    )
    assert resp.is_default is True

    # seeded_model은 default 해제
    prev = await repo.find_by_id(seeded_model.id, "req-1")
    assert prev is not None
    assert prev.is_default is False


@pytest.mark.asyncio
async def test_update_missing_raises(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    use_case = UpdateLlmModelUseCase(repository=repo, logger=mock_logger)
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        await use_case.execute(
            "missing-id",
            UpdateLlmModelRequest(display_name="x"),
            request_id="req-1",
        )
