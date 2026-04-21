"""DeactivateLlmModelUseCase 테스트."""
import pytest

from src.application.llm_model.deactivate_llm_model_use_case import (
    DeactivateLlmModelUseCase,
)

from tests.application.llm_model.conftest import InMemoryLlmModelRepository


@pytest.mark.asyncio
async def test_deactivate_does_not_delete(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    use_case = DeactivateLlmModelUseCase(repository=repo, logger=mock_logger)
    resp = await use_case.execute(seeded_model.id, request_id="req-1")

    # DB 레코드는 존재하고, is_active=False, is_default=False
    assert resp.is_active is False
    assert resp.is_default is False
    persisted = await repo.find_by_id(seeded_model.id, "req-1")
    assert persisted is not None
    assert persisted.is_active is False
    assert persisted.is_default is False


@pytest.mark.asyncio
async def test_deactivate_missing_raises(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    use_case = DeactivateLlmModelUseCase(repository=repo, logger=mock_logger)
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        await use_case.execute("missing-id", request_id="req-2")
