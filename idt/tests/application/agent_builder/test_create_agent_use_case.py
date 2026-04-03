"""CreateAgentUseCase 단위 테스트 — Mock 의존성."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.schemas import CreateAgentRequest, CreateAgentResponse
from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition, WorkflowSkeleton


def _make_worker(tool_id: str, sort_order: int = 0) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id,
        worker_id=f"{tool_id}_worker",
        description="테스트",
        sort_order=sort_order,
    )


def _make_use_case():
    tool_selector = MagicMock()
    prompt_generator = MagicMock()
    repository = MagicMock()
    logger = MagicMock()

    skeleton = WorkflowSkeleton(
        workers=[_make_worker("tavily_search", 0), _make_worker("excel_export", 1)],
        flow_hint="search 후 export",
    )
    tool_selector.select = AsyncMock(return_value=skeleton)
    prompt_generator.generate = AsyncMock(return_value="자동 생성된 시스템 프롬프트")

    now = datetime.now(timezone.utc)
    saved_agent = AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name="AI 뉴스 수집기",
        description="AI 관련 뉴스 검색하고 엑셀로 저장하는 에이전트 만들어줘",
        system_prompt="자동 생성된 시스템 프롬프트",
        flow_hint="search 후 export",
        workers=skeleton.workers,
        model_name="gpt-4o-mini",
        status="active",
        created_at=now,
        updated_at=now,
    )
    repository.save = AsyncMock(return_value=saved_agent)

    use_case = CreateAgentUseCase(
        tool_selector=tool_selector,
        prompt_generator=prompt_generator,
        repository=repository,
        logger=logger,
    )
    return use_case, tool_selector, prompt_generator, repository


class TestCreateAgentUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_create_agent_response(self):
        use_case, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="AI 관련 뉴스 검색하고 엑셀로 저장하는 에이전트 만들어줘",
            name="AI 뉴스 수집기",
            user_id="user-1",
        )
        result = await use_case.execute(request, "req-1")
        assert isinstance(result, CreateAgentResponse)
        assert result.name == "AI 뉴스 수집기"
        assert result.system_prompt == "자동 생성된 시스템 프롬프트"

    @pytest.mark.asyncio
    async def test_execute_calls_tool_selector(self):
        use_case, tool_selector, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청", name="테스트", user_id="user-1"
        )
        await use_case.execute(request, "req-1")
        tool_selector.select.assert_awaited_once_with("테스트 요청", "req-1")

    @pytest.mark.asyncio
    async def test_execute_calls_prompt_generator(self):
        use_case, _, prompt_generator, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청", name="테스트", user_id="user-1"
        )
        await use_case.execute(request, "req-1")
        prompt_generator.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_calls_repository_save(self):
        use_case, _, _, repository = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청", name="테스트", user_id="user-1"
        )
        await use_case.execute(request, "req-1")
        repository.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_response_contains_tool_ids(self):
        use_case, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청", name="테스트", user_id="user-1"
        )
        result = await use_case.execute(request, "req-1")
        assert set(result.tool_ids) == {"tavily_search", "excel_export"}

    @pytest.mark.asyncio
    async def test_execute_raises_on_tool_count_zero(self):
        use_case, tool_selector, _, _ = _make_use_case()
        tool_selector.select = AsyncMock(
            return_value=WorkflowSkeleton(workers=[], flow_hint="")
        )
        request = CreateAgentRequest(
            user_request="요청", name="테스트", user_id="user-1"
        )
        with pytest.raises(ValueError, match="최소"):
            await use_case.execute(request, "req-1")
