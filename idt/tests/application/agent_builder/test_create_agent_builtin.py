"""CreateAgentUseCase 빌트인 도구 주입 테스트 — builtin-tools D5/D6.

빌트인(tool_catalog.is_builtin AND is_active)은 모든 생성 경로에서 자동 주입되며,
명시적 exclude_builtin_tool_ids로만 제외된다(수동 opt-out — 채팅 초안 경로는
이 필드를 쓰지 않으므로 LLM이 빌트인을 뺄 수 없다).
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.schemas import CreateAgentRequest
from src.domain.llm_model.entity import LlmModel
from src.domain.tool_catalog.entity import ToolCatalogEntry

PROMPT = "테스트 지침"
MCP_SERVER_ID = "11111111-2222-3333-4444-555555555555"


def _llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-default", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _builtin_entry(tool_id: str) -> ToolCatalogEntry:
    return ToolCatalogEntry(
        id=f"tc-{tool_id}", tool_id=tool_id,
        source="mcp" if tool_id.startswith("mcp:") else "internal",
        name=tool_id, description=f"desc-{tool_id}",
        mcp_server_id=tool_id.split(":")[1] if tool_id.startswith("mcp:") else None,
        is_active=True, is_builtin=True,
    )


def _wiki_builtins() -> list[ToolCatalogEntry]:
    return [
        _builtin_entry("internal:wiki_read"),
        _builtin_entry("internal:wiki_list"),
    ]


def _make_use_case(
    builtins: list[ToolCatalogEntry] | None = None,
    with_catalog_repo: bool = True,
    mcp_server_active: bool = True,
):
    repository = MagicMock()
    repository.save = AsyncMock(side_effect=lambda agent, rid: agent)
    llm_model_repository = MagicMock()
    model = _llm_model()
    llm_model_repository.find_by_id = AsyncMock(return_value=model)
    llm_model_repository.find_default = AsyncMock(return_value=model)
    perm_repo = MagicMock()
    perm_repo.find_by_collection_name = AsyncMock(return_value=None)

    tool_catalog_repo = None
    if with_catalog_repo:
        tool_catalog_repo = MagicMock()
        tool_catalog_repo.list_builtin = AsyncMock(return_value=builtins or [])

    mcp_server_repo = MagicMock()
    reg = MagicMock()
    reg.is_active = mcp_server_active
    reg.description = "MCP 서버 설명"
    reg.name = "mcp-server"
    mcp_server_repo.find_by_id = AsyncMock(return_value=reg)

    use_case = CreateAgentUseCase(
        repository=repository,
        llm_model_repository=llm_model_repository,
        perm_repo=perm_repo,
        logger=MagicMock(),
        mcp_server_repo=mcp_server_repo,
        tool_catalog_repo=tool_catalog_repo,
    )
    return use_case, repository


def _request(**kw) -> CreateAgentRequest:
    defaults = dict(
        user_request="요청", name="테스트", user_id="user-1",
        system_prompt=PROMPT,
    )
    defaults.update(kw)
    return CreateAgentRequest(**defaults)


class TestBuiltinInjection:
    @pytest.mark.asyncio
    async def test_injects_builtins_when_no_tools_selected(self):
        use_case, _ = _make_use_case(builtins=_wiki_builtins())
        result = await use_case.execute(_request(), "req")
        assert set(result.tool_ids) == {"wiki_read", "wiki_list"}

    @pytest.mark.asyncio
    async def test_no_duplicate_when_user_already_selected(self):
        use_case, _ = _make_use_case(builtins=_wiki_builtins())
        result = await use_case.execute(
            _request(tool_ids=["internal:wiki_read"]), "req"
        )
        assert result.tool_ids.count("wiki_read") == 1
        assert "wiki_list" in result.tool_ids

    @pytest.mark.asyncio
    async def test_exclude_catalog_format(self):
        use_case, _ = _make_use_case(builtins=_wiki_builtins())
        result = await use_case.execute(
            _request(exclude_builtin_tool_ids=["internal:wiki_list"]), "req"
        )
        assert "wiki_list" not in result.tool_ids
        assert "wiki_read" in result.tool_ids

    @pytest.mark.asyncio
    async def test_exclude_storage_format(self):
        use_case, _ = _make_use_case(builtins=_wiki_builtins())
        result = await use_case.execute(
            _request(exclude_builtin_tool_ids=["wiki_read", "wiki_list"]), "req"
        )
        assert result.tool_ids == []

    @pytest.mark.asyncio
    async def test_builtins_exempt_from_max_tools(self):
        """D6: 사용자 5개(상한) + 빌트인 2개 = 7개 저장 허용."""
        use_case, _ = _make_use_case(builtins=_wiki_builtins())
        five = [
            "internal:tavily_search", "internal:excel_export",
            "internal:data_analysis", "internal:internal_document_search",
            "internal:python_code_executor",
        ]
        result = await use_case.execute(_request(tool_ids=five), "req")
        assert len(result.tool_ids) == 7

    @pytest.mark.asyncio
    async def test_inactive_mcp_builtin_skipped_without_failure(self):
        """FR-07: MCP 서버 비활성 → 해당 빌트인만 제외, 생성은 성공."""
        builtins = _wiki_builtins() + [
            _builtin_entry(f"mcp:{MCP_SERVER_ID}:some_tool")
        ]
        use_case, _ = _make_use_case(builtins=builtins, mcp_server_active=False)
        result = await use_case.execute(_request(), "req")
        assert set(result.tool_ids) == {"wiki_read", "wiki_list"}

    @pytest.mark.asyncio
    async def test_active_mcp_builtins_injected_per_tool(self):
        """동일 서버 빌트인 도구 여러 개 → 도구별 워커.

        빌트인도 개별 도구 단위다 — 서버 단위로 접으면 관리자가 켠 도구와
        실제 바인딩되는 도구가 달라진다.
        """
        builtins = [
            _builtin_entry(f"mcp:{MCP_SERVER_ID}:tool_a"),
            _builtin_entry(f"mcp:{MCP_SERVER_ID}:tool_b"),
        ]
        use_case, _ = _make_use_case(builtins=builtins)
        result = await use_case.execute(_request(), "req")
        assert result.tool_ids == [
            f"mcp:{MCP_SERVER_ID}:tool_a",
            f"mcp:{MCP_SERVER_ID}:tool_b",
        ]

    @pytest.mark.asyncio
    async def test_no_catalog_repo_skips_injection(self):
        """optional 의존성 무회귀: tool_catalog_repo 미주입 → 주입 생략."""
        use_case, _ = _make_use_case(with_catalog_repo=False)
        result = await use_case.execute(_request(), "req")
        assert result.tool_ids == []

    @pytest.mark.asyncio
    async def test_flow_hint_excludes_builtins(self):
        """빌트인은 flow_hint 미포함 — 사용자 도구 순서 힌트 불변."""
        use_case, _ = _make_use_case(builtins=_wiki_builtins())
        result = await use_case.execute(
            _request(tool_ids=["internal:tavily_search"]), "req"
        )
        assert result.flow_hint == "tavily_search"

    @pytest.mark.asyncio
    async def test_builtin_worker_sort_order_after_user_tools(self):
        use_case, repository = _make_use_case(builtins=_wiki_builtins())
        await use_case.execute(
            _request(tool_ids=["internal:tavily_search"]), "req"
        )
        saved = repository.save.call_args[0][0]
        orders = {w.tool_id: w.sort_order for w in saved.workers}
        assert orders["tavily_search"] == 0
        assert {orders["wiki_read"], orders["wiki_list"]} == {1, 2}
