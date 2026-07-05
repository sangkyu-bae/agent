"""CreateAgentUseCase — FR-09: system_prompt 프리필 테스트 (nl-agent-composer D1)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.schemas import CreateAgentRequest
from src.domain.llm_model.entity import LlmModel


def _make_default_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-default",
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=True,
        created_at=now,
        updated_at=now,
    )


def _make_use_case():
    tool_selector = MagicMock()
    prompt_generator = MagicMock()
    prompt_generator.generate = AsyncMock(return_value="자동 생성된 프롬프트")
    repository = MagicMock()

    async def _save_passthrough(agent, req_id):
        return agent

    repository.save = AsyncMock(side_effect=_save_passthrough)

    llm_model_repository = MagicMock()
    default_model = _make_default_llm_model()
    llm_model_repository.find_by_id = AsyncMock(return_value=default_model)
    llm_model_repository.find_default = AsyncMock(return_value=default_model)

    perm_repo = MagicMock()
    perm_repo.find_by_collection_name = AsyncMock(return_value=None)

    use_case = CreateAgentUseCase(
        tool_selector=tool_selector,
        prompt_generator=prompt_generator,
        repository=repository,
        llm_model_repository=llm_model_repository,
        perm_repo=perm_repo,
        logger=MagicMock(),
    )
    return use_case, repository, prompt_generator


def _request(system_prompt: str | None) -> CreateAgentRequest:
    return CreateAgentRequest(
        user_request="검색 에이전트",
        name="검색 도우미",
        user_id=str(uuid.uuid4()),
        tool_ids=["tavily_search"],
        system_prompt=system_prompt,
    )


class TestSystemPromptPrefill:
    @pytest.mark.asyncio
    async def test_prefill_skips_generator_and_saves_as_is(self):
        use_case, repository, prompt_generator = _make_use_case()

        result = await use_case.execute(_request("화면에서 수정된 프롬프트"), "req-1")

        prompt_generator.generate.assert_not_called()
        assert result.system_prompt == "화면에서 수정된 프롬프트"
        saved_agent = repository.save.call_args[0][0]
        assert saved_agent.system_prompt == "화면에서 수정된 프롬프트"

    @pytest.mark.asyncio
    async def test_none_falls_back_to_generator(self):
        use_case, _, prompt_generator = _make_use_case()

        result = await use_case.execute(_request(None), "req-1")

        prompt_generator.generate.assert_awaited_once()
        assert result.system_prompt == "자동 생성된 프롬프트"

    def test_over_4000_chars_rejected_by_schema(self):
        with pytest.raises(ValidationError):
            _request("가" * 4001)
