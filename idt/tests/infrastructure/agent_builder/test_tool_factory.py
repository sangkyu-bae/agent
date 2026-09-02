"""ToolFactory 단위 테스트 — Mock DI 사용."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import BaseTool

from src.infrastructure.agent_builder.tool_factory import ToolFactory

_SERVER_UUID = "081c6fe7-e0bd-4aad-9a42-29b8bf073167"


def _make_factory(
    tavily_api_key: str = "test-key",
    mcp_tool_loader=None,
    mcp_repository=None,
) -> ToolFactory:
    logger = MagicMock()
    hybrid_search = MagicMock()
    return ToolFactory(
        logger=logger,
        hybrid_search_use_case=hybrid_search,
        tavily_api_key=tavily_api_key,
        mcp_tool_loader=mcp_tool_loader,
        mcp_repository=mcp_repository,
    )


class TestToolFactory:
    def test_create_excel_export_tool(self):
        factory = _make_factory()
        tool = factory.create("excel_export")
        assert isinstance(tool, BaseTool)
        assert tool.name == "excel_export"

    def test_create_python_code_executor_tool(self):
        factory = _make_factory()
        tool = factory.create("python_code_executor")
        assert isinstance(tool, BaseTool)
        assert tool.name == "python_code_executor"

    def test_create_tavily_search_tool(self):
        factory = _make_factory(tavily_api_key="test-key")
        tool = factory.create("tavily_search")
        assert isinstance(tool, BaseTool)
        assert tool.name == "tavily_search"

    def test_create_internal_document_search_tool(self):
        factory = _make_factory()
        tool = factory.create("internal_document_search")
        assert isinstance(tool, BaseTool)
        assert tool.name == "internal_document_search"

    def test_default_uses_plain_hybrid_search(self):
        logger = MagicMock()
        hybrid = MagicMock()
        wiki = MagicMock()
        factory = ToolFactory(
            logger=logger, hybrid_search_use_case=hybrid, wiki_search=wiki
        )
        tool = factory.create("internal_document_search")  # use_wiki_first 기본 False
        assert tool.hybrid_search_use_case is hybrid

    def test_use_wiki_first_selects_wiki_adapter(self):
        logger = MagicMock()
        hybrid = MagicMock()
        wiki = MagicMock()
        factory = ToolFactory(
            logger=logger, hybrid_search_use_case=hybrid, wiki_search=wiki
        )
        tool = factory.create(
            "internal_document_search", tool_config={"use_wiki_first": True}
        )
        assert tool.hybrid_search_use_case is wiki

    def test_use_wiki_first_without_adapter_falls_back_to_hybrid(self):
        logger = MagicMock()
        hybrid = MagicMock()
        factory = ToolFactory(
            logger=logger, hybrid_search_use_case=hybrid, wiki_search=None
        )
        tool = factory.create(
            "internal_document_search", tool_config={"use_wiki_first": True}
        )
        assert tool.hybrid_search_use_case is hybrid

    def test_create_unknown_tool_raises(self):
        factory = _make_factory()
        with pytest.raises(ValueError, match="Unknown tool_id"):
            factory.create("unknown_tool")


class TestToolFactoryWikiRead:
    """wiki-agentic-navigation FR-01: wiki_read 생성 분기."""

    def test_create_wiki_read_with_deps(self):
        factory = ToolFactory(
            logger=MagicMock(),
            wiki_session_factory=MagicMock(),
            wiki_repo_builder=MagicMock(),
        )
        tool = factory.create("wiki_read", request_id="r1")
        assert isinstance(tool, BaseTool)
        assert tool.name == "wiki_read"
        assert tool.request_id == "r1"

    def test_create_wiki_read_without_deps_raises(self):
        """의존 미주입 시 조용한 오동작 대신 설정 오류를 조기 표면화."""
        factory = _make_factory()
        with pytest.raises(ValueError, match="wiki_read"):
            factory.create("wiki_read")


class TestToolFactoryWikiList:
    """wiki-folder-summaries FR-03: wiki_list 생성 분기."""

    def test_create_wiki_list_with_deps(self):
        factory = ToolFactory(
            logger=MagicMock(),
            wiki_session_factory=MagicMock(),
            wiki_repo_builder=MagicMock(),
            wiki_folder_repo_builder=MagicMock(),
        )
        tool = factory.create("wiki_list", request_id="r1")
        assert isinstance(tool, BaseTool)
        assert tool.name == "wiki_list"
        assert tool.request_id == "r1"

    def test_create_wiki_list_without_folder_repo_raises(self):
        """wiki_read 의존만으로는 부족 — 폴더 repo 미주입 시 조기 표면화."""
        factory = ToolFactory(
            logger=MagicMock(),
            wiki_session_factory=MagicMock(),
            wiki_repo_builder=MagicMock(),
        )
        with pytest.raises(ValueError, match="wiki_list"):
            factory.create("wiki_list")


class TestToolFactoryRagConfig:
    def test_create_with_rag_config_applies_settings(self):
        factory = _make_factory()
        config = {
            "top_k": 10,
            "search_mode": "vector_only",
            "metadata_filter": {"department": "finance"},
            "tool_name": "금융 문서 검색",
            "tool_description": "금융 관련 내부 문서를 검색합니다.",
        }
        tool = factory.create("internal_document_search", tool_config=config)
        import re
        assert re.match(r"^[a-zA-Z0-9_-]+$", tool.name)
        assert tool.description == "금융 관련 내부 문서를 검색합니다."
        assert tool.top_k == 10
        assert tool.search_mode == "vector_only"
        assert tool.metadata_filter == {"department": "finance"}

    def test_create_with_ascii_tool_name_preserved(self):
        factory = _make_factory()
        config = {"tool_name": "finance_doc_search"}
        tool = factory.create("internal_document_search", tool_config=config)
        assert tool.name == "finance_doc_search"

    def test_create_without_config_uses_defaults(self):
        factory = _make_factory()
        tool = factory.create("internal_document_search")
        assert tool.top_k == 5
        assert tool.search_mode == "hybrid"
        assert tool.metadata_filter == {}

    def test_create_with_none_config_uses_defaults(self):
        factory = _make_factory()
        tool = factory.create("internal_document_search", tool_config=None)
        assert tool.top_k == 5

    def test_create_with_partial_config_merges_defaults(self):
        factory = _make_factory()
        tool = factory.create(
            "internal_document_search", tool_config={"top_k": 15}
        )
        assert tool.top_k == 15
        assert tool.search_mode == "hybrid"

    def test_parse_rag_config_invalid_raises(self):
        factory = _make_factory()
        with pytest.raises(ValueError):
            factory.create(
                "internal_document_search",
                tool_config={"top_k": 999},
            )

    def test_non_rag_tool_ignores_config(self):
        factory = _make_factory()
        tool = factory.create("excel_export", tool_config={"top_k": 10})
        assert tool.name == "excel_export"


class TestToolFactoryRoutedSearch:
    """rag-routed-integration D2 — routed getter 주입·전달."""

    def test_routed_getter_and_flag_forwarded(self):
        getter = lambda: MagicMock()  # noqa: E731
        factory = ToolFactory(
            logger=MagicMock(),
            hybrid_search_use_case=MagicMock(),
            routed_retrieval_getter=getter,
        )
        tool = factory.create(
            "internal_document_search",
            tool_config={"use_routed_search": True},
        )
        assert tool.use_routed_search is True
        assert tool.routed_retrieval_getter is getter

    def test_default_config_disables_routed(self):
        tool = _make_factory().create("internal_document_search")
        assert tool.use_routed_search is False
        assert tool.routed_retrieval_getter is None

    def test_legacy_config_without_field_restores_false(self):
        """기존 저장 config(필드 부재) 하위호환 (D1)."""
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={"top_k": 7, "search_mode": "vector_only"},
        )
        assert tool.use_routed_search is False
        assert tool.search_mode == "vector_only"


class TestToolFactoryKbFilter:
    """kb-rag-filter D6 — kb_id를 metadata_filter에 병합."""

    def test_kb_id_merged_into_metadata_filter(self):
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={"kb_id": "kb-uuid-001"},
        )
        assert tool.metadata_filter == {"kb_id": "kb-uuid-001"}

    def test_kb_id_merges_with_existing_filters(self):
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={
                "kb_id": "kb-uuid-001",
                "metadata_filter": {"department": "finance"},
            },
        )
        assert tool.metadata_filter == {
            "department": "finance",
            "kb_id": "kb-uuid-001",
        }

    def test_first_class_kb_id_overrides_manual_filter_key(self):
        """D2: metadata_filter의 수동 kb_id 키보다 필드가 우선."""
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={
                "kb_id": "kb-field",
                "metadata_filter": {"kb_id": "kb-manual"},
            },
        )
        assert tool.metadata_filter["kb_id"] == "kb-field"

    def test_without_kb_id_filter_unchanged(self):
        """FR-06: kb_id 미설정 시 기존 동작 그대로."""
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={"metadata_filter": {"department": "finance"}},
        )
        assert tool.metadata_filter == {"department": "finance"}

    def test_legacy_config_without_kb_id_restores_none(self):
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={"top_k": 7},
        )
        assert tool.metadata_filter == {}


class TestToolFactoryScoreThreshold:
    """벡터 코사인 컷오프 임계값 주입 (에이전트값 우선 + 전역 fallback)."""

    def test_uses_agent_threshold_when_set(self, monkeypatch):
        monkeypatch.setattr(
            "src.config.settings.rag_vector_score_threshold", 0.1
        )
        factory = _make_factory()
        tool = factory.create(
            "internal_document_search", tool_config={"score_threshold": 0.4}
        )
        assert tool.score_threshold == 0.4

    def test_falls_back_to_global_when_none(self, monkeypatch):
        monkeypatch.setattr(
            "src.config.settings.rag_vector_score_threshold", 0.25
        )
        factory = _make_factory()
        tool = factory.create("internal_document_search")
        assert tool.score_threshold == 0.25

    def test_explicit_zero_overrides_global(self, monkeypatch):
        monkeypatch.setattr(
            "src.config.settings.rag_vector_score_threshold", 0.25
        )
        factory = _make_factory()
        tool = factory.create(
            "internal_document_search", tool_config={"score_threshold": 0.0}
        )
        assert tool.score_threshold == 0.0

    def test_default_global_zero_is_disabled(self):
        factory = _make_factory()
        tool = factory.create("internal_document_search")
        assert tool.score_threshold == 0.0


class TestToolFactoryMCPRouting:

    @pytest.mark.asyncio
    async def test_create_async_routes_mcp_prefix_to_loader(self):
        mock_tool = MagicMock(spec=BaseTool)
        mock_loader = MagicMock()
        mock_loader.load_by_tool_id = AsyncMock(return_value=[mock_tool])
        mock_repo = MagicMock()

        factory = _make_factory(mcp_tool_loader=mock_loader)
        result = await factory.create_async(
            tool_id="mcp_uuid-001",
            request_id="req-001",
            mcp_repository=mock_repo,
        )

        assert result is mock_tool
        mock_loader.load_by_tool_id.assert_called_once_with(
            tool_id="mcp_uuid-001",
            repository=mock_repo,
            request_id="req-001",
        )

    @pytest.mark.asyncio
    async def test_create_async_falls_back_to_injected_repository(self):
        """WorkflowCompiler는 mcp_repository를 넘기지 않는다.

        컴파일러(workflow_compiler.py)의 create_async 호출부는 tool_id/
        request_id/tool_config만 넘기므로, 팩토리가 생성 시 주입받은
        세션 스코프 저장소로 폴백하지 않으면 MCP 워커가 실행되지 않는다.
        """
        mock_tool = MagicMock(spec=BaseTool)
        mock_loader = MagicMock()
        mock_loader.load_by_tool_id = AsyncMock(return_value=[mock_tool])
        default_repo = MagicMock()

        factory = _make_factory(
            mcp_tool_loader=mock_loader, mcp_repository=default_repo
        )
        result = await factory.create_async(
            tool_id="mcp_uuid-001", request_id="req-001"
        )

        assert result is mock_tool
        mock_loader.load_by_tool_id.assert_called_once_with(
            tool_id="mcp_uuid-001",
            repository=default_repo,
            request_id="req-001",
        )

    @pytest.mark.asyncio
    async def test_create_async_explicit_repository_overrides_injected(self):
        mock_loader = MagicMock()
        mock_loader.load_by_tool_id = AsyncMock(
            return_value=[MagicMock(spec=BaseTool)]
        )
        default_repo = MagicMock()
        explicit_repo = MagicMock()

        factory = _make_factory(
            mcp_tool_loader=mock_loader, mcp_repository=default_repo
        )
        await factory.create_async(
            tool_id="mcp_uuid-001",
            request_id="req-001",
            mcp_repository=explicit_repo,
        )

        assert (
            mock_loader.load_by_tool_id.call_args.kwargs["repository"]
            is explicit_repo
        )

    @pytest.mark.asyncio
    async def test_catalog_id_selects_the_named_tool_not_the_first(self):
        """mcp:{srv}:{tool}은 지정한 도구를 정확히 골라야 한다.

        서버가 돌려주는 순서에 기대어 tools[0]을 반환하면 사용자가 고른
        것과 다른 도구가 바인딩된다(조용한 오작동).
        """
        wanted = MagicMock(spec=["name", "mcp_tool_name", "description"])
        wanted.mcp_tool_name = "create_issue"
        other = MagicMock(spec=["name", "mcp_tool_name", "description"])
        other.mcp_tool_name = "list_issues"

        mock_loader = MagicMock()
        mock_loader.load_by_tool_id = AsyncMock(return_value=[other, wanted])

        factory = _make_factory(
            mcp_tool_loader=mock_loader, mcp_repository=MagicMock()
        )
        result = await factory.create_async(
            tool_id=f"mcp:{_SERVER_UUID}:create_issue", request_id="req-001"
        )

        assert result is wanted
        # 로더에는 서버 단위 id로 조회해야 한다.
        assert (
            mock_loader.load_by_tool_id.call_args.kwargs["tool_id"]
            == f"mcp_{_SERVER_UUID}"
        )

    @pytest.mark.asyncio
    async def test_catalog_id_raises_when_named_tool_absent(self):
        """서버에서 사라진 도구를 조용히 다른 것으로 대체하지 않는다."""
        other = MagicMock(spec=["name", "mcp_tool_name", "description"])
        other.mcp_tool_name = "list_issues"

        mock_loader = MagicMock()
        mock_loader.load_by_tool_id = AsyncMock(return_value=[other])

        factory = _make_factory(
            mcp_tool_loader=mock_loader, mcp_repository=MagicMock()
        )
        with pytest.raises(ValueError, match="MCP tool not found"):
            await factory.create_async(
                tool_id=f"mcp:{_SERVER_UUID}:create_issue", request_id="req-001"
            )

    @pytest.mark.asyncio
    async def test_create_async_raises_when_mcp_tool_not_found(self):
        mock_loader = MagicMock()
        mock_loader.load_by_tool_id = AsyncMock(return_value=[])
        mock_repo = MagicMock()

        factory = _make_factory(mcp_tool_loader=mock_loader)
        with pytest.raises(ValueError, match="mcp_missing"):
            await factory.create_async(
                tool_id="mcp_missing",
                request_id="req-001",
                mcp_repository=mock_repo,
            )

    @pytest.mark.asyncio
    async def test_create_async_raises_when_no_loader_for_mcp(self):
        factory = _make_factory(mcp_tool_loader=None)
        with pytest.raises(ValueError, match="MCPToolLoader"):
            await factory.create_async(
                tool_id="mcp_uuid-001",
                request_id="req-001",
                mcp_repository=MagicMock(),
            )


class TestToolFactoryMCPDiagnostics:
    """바인딩 구간 계측 (Design Ref: fix-mcp-tool-call-not-reaching-server §2.2)."""

    @staticmethod
    def _tool(mcp_name: str, exposed: str):
        t = MagicMock(spec=BaseTool)
        t.mcp_tool_name = mcp_name
        t.name = exposed
        return t

    def _factory_with(self, tools):
        loader = MagicMock()
        loader.load_by_tool_id = AsyncMock(return_value=tools)
        return _make_factory(mcp_tool_loader=loader, mcp_repository=MagicMock())

    @staticmethod
    def _info_calls(factory, message):
        return [
            c for c in factory._logger.info.call_args_list if c.args[0] == message
        ]

    @pytest.mark.asyncio
    async def test_binding_start_logged_before_load(self):
        """이 로그가 없으면 compile이 MCP 워커에 도달조차 못한 것이다."""
        factory = self._factory_with([self._tool("create_issue", "srv_create_issue")])

        await factory.create_async(
            tool_id=f"mcp:{_SERVER_UUID}:create_issue", request_id="req-101"
        )

        started = self._info_calls(factory, "MCP tool binding start")
        assert started
        kwargs = started[0].kwargs
        assert kwargs["request_id"] == "req-101"
        assert kwargs["server_id"] == _SERVER_UUID
        assert kwargs["requested_tool"] == "create_issue"

    @pytest.mark.asyncio
    async def test_binding_start_logged_even_when_loader_missing(self):
        """배선 누락(E1)도 '도달은 했다'는 사실이 로그로 남아야 판별된다."""
        factory = _make_factory(mcp_tool_loader=None)

        with pytest.raises(ValueError):
            await factory.create_async(
                tool_id=f"mcp_{_SERVER_UUID}", request_id="req-102"
            )

        assert self._info_calls(factory, "MCP tool binding start")

    @pytest.mark.asyncio
    async def test_bound_log_reports_exact_tool_for_catalog_id(self):
        """신규 형식은 fallback=False로 지정 도구가 바인딩됐음을 남긴다."""
        factory = self._factory_with([
            self._tool("list_issues", "srv_list_issues"),
            self._tool("create_issue", "srv_create_issue"),
        ])

        await factory.create_async(
            tool_id=f"mcp:{_SERVER_UUID}:create_issue", request_id="req-103"
        )

        bound = self._info_calls(factory, "MCP tool bound")
        assert bound
        kwargs = bound[0].kwargs
        assert kwargs["bound_tool"] == "create_issue"
        assert kwargs["exposed_name"] == "srv_create_issue"
        assert kwargs["fallback"] is False
        assert kwargs["available"] == 2

    @pytest.mark.asyncio
    async def test_bound_log_marks_fallback_for_legacy_id(self):
        """레거시 ID는 fallback=True — D1(첫-도구 임의 바인딩)의 판별 신호."""
        factory = self._factory_with([
            self._tool("list_issues", "srv_list_issues"),
            self._tool("create_issue", "srv_create_issue"),
        ])

        await factory.create_async(
            tool_id=f"mcp_{_SERVER_UUID}", request_id="req-104"
        )

        kwargs = self._info_calls(factory, "MCP tool bound")[0].kwargs
        assert kwargs["fallback"] is True
        assert kwargs["bound_tool"] == "list_issues"  # 첫 도구
        assert kwargs["available"] == 2

    @pytest.mark.asyncio
    async def test_bound_log_carries_exposed_name_length(self):
        """D2(OpenAI 64자 상한) 초과 여부를 로그만으로 판별할 수 있어야 한다."""
        long_name = "mcp_" + "a" * 70
        factory = self._factory_with([self._tool("create_issue", long_name)])

        await factory.create_async(
            tool_id=f"mcp:{_SERVER_UUID}:create_issue", request_id="req-105"
        )

        kwargs = self._info_calls(factory, "MCP tool bound")[0].kwargs
        assert kwargs["exposed_name_len"] == len(long_name)
        assert kwargs["exposed_name_len"] > 64


class TestToolFactoryCreateAllAsync:
    """D1 — 레거시 서버 단위 ID는 서버의 도구 '전체'를 워커에 바인딩한다.

    Design Ref: fix-mcp-tool-call-not-reaching-server §6.1 E6 (module-1 실측으로 변경)
    첫-도구 폴백은 워커 description이 안내한 나머지 도구를 도달 불가로 만든다.
    """

    @staticmethod
    def _tool(mcp_name: str):
        t = MagicMock(spec=BaseTool)
        t.mcp_tool_name = mcp_name
        t.name = f"srv_{mcp_name}"
        return t

    def _factory_with(self, tools):
        loader = MagicMock()
        loader.load_by_tool_id = AsyncMock(return_value=tools)
        return _make_factory(mcp_tool_loader=loader, mcp_repository=MagicMock())

    @pytest.mark.asyncio
    async def test_legacy_id_binds_every_tool_on_server(self):
        factory = self._factory_with([
            self._tool("scrape_url"),
            self._tool("scrape_urls"),
            self._tool("extract_structured"),
        ])

        tools = await factory.create_all_async(
            tool_id=f"mcp_{_SERVER_UUID}", request_id="req-201"
        )

        assert [t.mcp_tool_name for t in tools] == [
            "scrape_url", "scrape_urls", "extract_structured"
        ]

    @pytest.mark.asyncio
    async def test_catalog_id_binds_only_the_named_tool(self):
        """신규 형식은 여전히 지정 도구 하나만 — 범위가 넓어지면 안 된다."""
        factory = self._factory_with([
            self._tool("scrape_url"),
            self._tool("scrape_urls"),
        ])

        tools = await factory.create_all_async(
            tool_id=f"mcp:{_SERVER_UUID}:scrape_urls", request_id="req-202"
        )

        assert len(tools) == 1
        assert tools[0].mcp_tool_name == "scrape_urls"

    @pytest.mark.asyncio
    async def test_catalog_id_raises_when_named_tool_absent(self):
        """G-02: 에러 메시지는 서버가 실제로 제공하는 도구명을 알려줘야 한다.

        Design Ref: §6.1 E5 — 카탈로그 tool_id가 서버 변경으로 낡았을 때
        "무엇이 있는지"를 알려주지 않으면 진단이 한 단계 더 필요해진다.
        """
        factory = self._factory_with([
            self._tool("scrape_url"), self._tool("extract_structured"),
        ])

        with pytest.raises(ValueError, match="MCP tool not found") as exc:
            await factory.create_all_async(
                tool_id=f"mcp:{_SERVER_UUID}:no_such_tool", request_id="req-203"
            )

        message = str(exc.value)
        assert "scrape_url" in message
        assert "extract_structured" in message

    @pytest.mark.asyncio
    async def test_missing_loader_raises_wiring_error(self):
        """G-01: 배선 오류는 전용 예외로 구분돼 컴파일러가 격리하지 않는다."""
        from src.domain.mcp.exceptions import McpWiringError

        factory = _make_factory(mcp_tool_loader=None)

        with pytest.raises(McpWiringError):
            await factory.create_all_async(
                tool_id=f"mcp_{_SERVER_UUID}", request_id="req-207"
            )

    @pytest.mark.asyncio
    async def test_missing_repository_raises_wiring_error(self):
        loader = MagicMock()
        loader.load_by_tool_id = AsyncMock(return_value=[])
        factory = _make_factory(mcp_tool_loader=loader, mcp_repository=None)

        from src.domain.mcp.exceptions import McpWiringError

        with pytest.raises(McpWiringError):
            await factory.create_all_async(
                tool_id=f"mcp_{_SERVER_UUID}", request_id="req-208"
            )

    @pytest.mark.asyncio
    async def test_wiring_error_is_a_value_error(self):
        """기존 ValueError 기반 처리와 호환된다 (하위호환)."""
        from src.domain.mcp.exceptions import McpWiringError

        assert issubclass(McpWiringError, ValueError)

    @pytest.mark.asyncio
    async def test_non_mcp_tool_id_returns_single_tool(self):
        """비-MCP 도구는 기존 동기 create() 경로를 그대로 탄다."""
        factory = _make_factory()

        tools = await factory.create_all_async(
            tool_id="excel_export", request_id="req-204"
        )

        assert len(tools) == 1
        assert tools[0].name == "excel_export"

    @pytest.mark.asyncio
    async def test_legacy_id_logs_full_binding(self):
        factory = self._factory_with([
            self._tool("scrape_url"), self._tool("scrape_urls")
        ])

        await factory.create_all_async(
            tool_id=f"mcp_{_SERVER_UUID}", request_id="req-205"
        )

        bound = [c for c in factory._logger.info.call_args_list
                 if c.args[0] == "MCP tools bound"]
        assert bound
        kwargs = bound[0].kwargs
        assert kwargs["bound_tools"] == ["scrape_url", "scrape_urls"]
        assert kwargs["server_level"] is True

    @pytest.mark.asyncio
    async def test_create_async_still_returns_first_tool_for_legacy(self):
        """기존 단수 API는 하위호환 유지 (run_middleware_agent_use_case 경로)."""
        factory = self._factory_with([
            self._tool("scrape_url"), self._tool("scrape_urls")
        ])

        tool = await factory.create_async(
            tool_id=f"mcp_{_SERVER_UUID}", request_id="req-206"
        )

        assert tool.mcp_tool_name == "scrape_url"
