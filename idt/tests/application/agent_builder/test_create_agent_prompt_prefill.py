"""CreateAgentUseCase — system_prompt 필수화 테스트 (agent-instruction-required).

이전 nl-agent-composer D1의 '프리필 우선, 없으면 자동생성' 동작을 대체한다.
지침은 이제 필수값이며 자동생성 경로(PromptGenerator)는 제거되었다.
"""
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
        repository=repository,
        llm_model_repository=llm_model_repository,
        perm_repo=perm_repo,
        logger=MagicMock(),
    )
    return use_case, repository


def _request(system_prompt: str | None) -> CreateAgentRequest:
    return CreateAgentRequest(
        user_request="검색 에이전트",
        name="검색 도우미",
        user_id=str(uuid.uuid4()),
        tool_ids=["tavily_search"],
        system_prompt=system_prompt,
    )


class TestSystemPromptRequired:
    @pytest.mark.asyncio
    async def test_provided_prompt_saved_as_is(self):
        use_case, repository = _make_use_case()

        result = await use_case.execute(_request("화면에서 입력한 지침"), "req-1")

        assert result.system_prompt == "화면에서 입력한 지침"
        saved_agent = repository.save.call_args[0][0]
        assert saved_agent.system_prompt == "화면에서 입력한 지침"

    @pytest.mark.asyncio
    async def test_none_prompt_raises(self):
        # 자동생성 제거: None이면 더 이상 fallback 없이 에러
        use_case, _ = _make_use_case()
        with pytest.raises(ValueError, match="비어"):
            await use_case.execute(_request(None), "req-1")

    @pytest.mark.asyncio
    async def test_empty_prompt_raises(self):
        use_case, _ = _make_use_case()
        with pytest.raises(ValueError, match="비어"):
            await use_case.execute(_request(""), "req-1")

    def test_over_4000_chars_rejected_by_schema(self):
        with pytest.raises(ValidationError):
            _request("가" * 4001)
