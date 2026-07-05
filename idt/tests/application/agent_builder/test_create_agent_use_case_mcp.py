"""CreateAgentUseCase — FR-08: 명시적 tool_ids 경로의 mcp_* 수용 테스트."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.schemas import CreateAgentRequest
from src.domain.llm_model.entity import LlmModel
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType


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


def _mcp_registration(server_id: str = "srv-1", is_active: bool = True) -> MCPServerRegistration:
    now = datetime.now(timezone.utc)
    return MCPServerRegistration(
        id=server_id,
        user_id="user-1",
        name="테스트 MCP 서버",
        description="웹 페이지 수집 MCP",
        endpoint="https://mcp.example.com",
        transport=MCPTransportType.STREAMABLE_HTTP,
        input_schema=None,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def _make_use_case(mcp_server_repo=None):
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
        mcp_server_repo=mcp_server_repo,
    )
    return use_case, repository, prompt_generator


def _request(tool_ids: list[str], system_prompt: str | None = None) -> CreateAgentRequest:
    return CreateAgentRequest(
        user_request="MCP 도구를 쓰는 에이전트",
        name="MCP 에이전트",
        user_id=str(uuid.uuid4()),
        tool_ids=tool_ids,
        system_prompt=system_prompt,
    )


class TestCreateAgentWithMcpToolIds:
    @pytest.mark.asyncio
    async def test_mcp_tool_id_creates_worker_from_registry_meta(self):
        mcp_repo = MagicMock()
        mcp_repo.find_by_id = AsyncMock(return_value=_mcp_registration())
        use_case, repository, _ = _make_use_case(mcp_server_repo=mcp_repo)

        result = await use_case.execute(_request(["mcp_srv-1"]), "req-1")

        assert result.tool_ids == ["mcp_srv-1"]
        saved_agent = repository.save.call_args[0][0]
        worker = saved_agent.workers[0]
        assert worker.tool_id == "mcp_srv-1"
        assert worker.worker_id == "mcp_srv-1_worker"
        assert "웹 페이지 수집 MCP" in worker.description

    @pytest.mark.asyncio
    async def test_mixed_internal_and_mcp_tool_ids(self):
        mcp_repo = MagicMock()
        mcp_repo.find_by_id = AsyncMock(return_value=_mcp_registration())
        use_case, repository, _ = _make_use_case(mcp_server_repo=mcp_repo)

        result = await use_case.execute(
            _request(["tavily_search", "mcp_srv-1"]), "req-1"
        )

        assert result.tool_ids == ["tavily_search", "mcp_srv-1"]

    @pytest.mark.asyncio
    async def test_unknown_mcp_server_raises(self):
        mcp_repo = MagicMock()
        mcp_repo.find_by_id = AsyncMock(return_value=None)
        use_case, _, _ = _make_use_case(mcp_server_repo=mcp_repo)

        with pytest.raises(ValueError, match="MCP"):
            await use_case.execute(_request(["mcp_ghost"]), "req-1")

    @pytest.mark.asyncio
    async def test_inactive_mcp_server_raises(self):
        mcp_repo = MagicMock()
        mcp_repo.find_by_id = AsyncMock(
            return_value=_mcp_registration(is_active=False)
        )
        use_case, _, _ = _make_use_case(mcp_server_repo=mcp_repo)

        with pytest.raises(ValueError, match="MCP"):
            await use_case.execute(_request(["mcp_srv-1"]), "req-1")

    @pytest.mark.asyncio
    async def test_mcp_tool_id_without_repo_raises(self):
        use_case, _, _ = _make_use_case(mcp_server_repo=None)

        with pytest.raises(ValueError):
            await use_case.execute(_request(["mcp_srv-1"]), "req-1")

    @pytest.mark.asyncio
    async def test_internal_only_path_unchanged(self):
        """내부 도구만 사용하는 기존 경로는 mcp repo 없이 그대로 동작."""
        use_case, repository, _ = _make_use_case(mcp_server_repo=None)

        result = await use_case.execute(
            _request(["tavily_search", "excel_export"]), "req-1"
        )

        assert result.tool_ids == ["tavily_search", "excel_export"]

    @pytest.mark.asyncio
    async def test_catalog_format_mcp_tool_id_normalized_to_server_id(self):
        """compose-tool-instructions D5: mcp:{srv}:{tool} → mcp_{srv} 정규화."""
        mcp_repo = MagicMock()
        mcp_repo.find_by_id = AsyncMock(return_value=_mcp_registration())
        use_case, repository, _ = _make_use_case(mcp_server_repo=mcp_repo)

        result = await use_case.execute(_request(["mcp:srv-1:search"]), "req-1")

        assert result.tool_ids == ["mcp_srv-1"]
        saved_agent = repository.save.call_args[0][0]
        assert saved_agent.workers[0].tool_id == "mcp_srv-1"

    @pytest.mark.asyncio
    async def test_same_server_multiple_catalog_tools_deduplicated(self):
        """compose-tool-instructions D5: 동일 서버 도구 여러 개 → mcp_{srv} 1개."""
        mcp_repo = MagicMock()
        mcp_repo.find_by_id = AsyncMock(return_value=_mcp_registration())
        use_case, repository, _ = _make_use_case(mcp_server_repo=mcp_repo)

        result = await use_case.execute(
            _request(["mcp:srv-1:search", "mcp:srv-1:fetch"]), "req-1"
        )

        assert result.tool_ids == ["mcp_srv-1"]
        saved_agent = repository.save.call_args[0][0]
        assert len(saved_agent.workers) == 1

    def test_normalize_tool_id_formats(self):
        """compose-tool-instructions D5: 4가지 형식 정규화 규칙."""
        norm = CreateAgentUseCase._normalize_tool_id
        assert norm("internal:excel_export") == "excel_export"
        assert norm("excel_export") == "excel_export"
        assert norm("mcp_srv-1") == "mcp_srv-1"
        assert norm("mcp:srv-1:search") == "mcp_srv-1"

    @pytest.mark.asyncio
    async def test_prompt_generation_with_mcp_worker_uses_worker_description(self):
        """프리필 프롬프트 없이 mcp_ 워커만 있어도 생성이 실패하지 않는다."""
        mcp_repo = MagicMock()
        mcp_repo.find_by_id = AsyncMock(return_value=_mcp_registration())
        use_case, _, prompt_generator = _make_use_case(mcp_server_repo=mcp_repo)

        result = await use_case.execute(_request(["mcp_srv-1"]), "req-1")

        prompt_generator.generate.assert_awaited_once()
        tool_metas = prompt_generator.generate.call_args[0][2]
        assert tool_metas[0].tool_id == "mcp_srv-1"
        assert result.system_prompt == "자동 생성된 프롬프트"
