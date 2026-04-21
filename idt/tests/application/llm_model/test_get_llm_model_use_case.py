"""GetLlmModelUseCase 테스트."""
import pytest

from src.application.llm_model.get_llm_model_use_case import GetLlmModelUseCase

from tests.application.llm_model.conftest import InMemoryLlmModelRepository


@pytest.mark.asyncio
async def test_get_llm_model_success(
    repo: InMemoryLlmModelRepository, mock_logger, seeded_model
) -> None:
    use_case = GetLlmModelUseCase(repository=repo, logger=mock_logger)
    resp = await use_case.execute(seeded_model.id, request_id="req-1")
    assert resp.id == seeded_model.id
    assert resp.model_name == seeded_model.model_name


@pytest.mark.asyncio
async def test_get_llm_model_missing_raises(
    repo: InMemoryLlmModelRepository, mock_logger
) -> None:
    use_case = GetLlmModelUseCase(repository=repo, logger=mock_logger)
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        await use_case.execute("missing", request_id="req-1")
