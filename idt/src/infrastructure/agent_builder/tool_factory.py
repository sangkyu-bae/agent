"""ToolFactory: tool_id → LangChain BaseTool 인스턴스 생성."""
import dataclasses
from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool

from src.domain.agent_builder.rag_tool_config import RagToolConfig, sanitize_tool_name
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.agent_run.auth_context import AuthContext
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp.exceptions import McpWiringError
from src.domain.tool_catalog.mcp_tool_id import McpToolRef, parse_mcp_tool_id


class ToolFactory:
    """tool_id에 해당하는 BaseTool 인스턴스를 동적으로 생성한다.

    M4: tracker / run_observability_config를 받아 RAG tool에 주입 →
    InternalDocumentSearchTool이 RunContext 기반으로 record_retrieval 호출.
    """

    def __init__(
        self,
        logger: LoggerInterface,
        hybrid_search_use_case: object | None = None,
        hybrid_search_use_case_getter: Callable[[], Any] | None = None,
        tavily_api_key: str | None = None,
        mcp_tool_loader=None,
        mcp_repository: Any = None,                # ★ MCP 서버 조회용 저장소
        tracker: Any = None,                       # ★ M4: RunTracker | None
        run_observability_config: Any = None,      # ★ M4: RunObservabilityConfig | None
        wiki_search: Any = None,                   # ★ LLM-WIKI-001: RunScopedWikiSearch | None
        routed_retrieval_getter: Callable[[], Any] | None = None,  # ★ rag-routed-integration D2
        wiki_session_factory: Any = None,          # ★ wiki-agentic-navigation: wiki_read용
        wiki_repo_builder: Any = None,             # ★ (session) -> WikiArticleRepository
        wiki_folder_repo_builder: Any = None,      # ★ wiki-folder-summaries: (session) -> WikiFolderSummaryRepository
    ) -> None:
        self._logger = logger
        self._hybrid_search = hybrid_search_use_case
        self._hybrid_search_getter = hybrid_search_use_case_getter
        self._tavily_api_key = tavily_api_key
        self._mcp_tool_loader = mcp_tool_loader
        # WorkflowCompiler는 create_async에 mcp_repository를 넘기지 않는다.
        # 팩토리는 앱 싱글톤이므로 per-request 세션을 들 수 없어,
        # 매 호출마다 세션을 여는 SessionScopedMcpServerRepository를 주입받는다.
        self._mcp_repository = mcp_repository
        self._tracker = tracker
        self._obs_config = run_observability_config
        # use_wiki_first=True인 RAG 도구에 주입할 위키 우선 검색 어댑터(없으면 hybrid 폴백).
        self._wiki_search = wiki_search
        # rag-routed-integration D2: use_routed_search=True인 RAG 도구에 주입.
        # None이면 도구가 not_wired 강등 처리(기존 search_mode 경로).
        self._routed_retrieval_getter = routed_retrieval_getter
        # wiki-agentic-navigation: wiki_read 도구용 per-call 세션 의존.
        self._wiki_session_factory = wiki_session_factory
        self._wiki_repo_builder = wiki_repo_builder
        # wiki-folder-summaries D4: wiki_list 도구용 폴더 요약 저장소 빌더.
        self._wiki_folder_repo_builder = wiki_folder_repo_builder
        # agent-user-context Design §7.1:
        # WorkflowCompiler.compile() 시점에 갱신되는 현재 요청의 AuthContext.
        # None이면 Tool은 ContextVar fallback 또는 public_anonymous 동작.
        self._auth_ctx: AuthContext | None = None

    def bind_auth_ctx(self, auth_ctx: AuthContext | None) -> None:
        """compile 시점에 현재 AuthContext 주입.

        주의: ToolFactory가 싱글톤이라면 동시 요청 시 ContextVar fallback이
        더 안전하다. 본 메서드는 compile → create 직선 호출에서만 신뢰.
        """
        self._auth_ctx = auth_ctx

    def _get_hybrid_search(self) -> object | None:
        if self._hybrid_search is not None:
            return self._hybrid_search
        if self._hybrid_search_getter is not None:
            return self._hybrid_search_getter()
        return None

    def _select_search(self, rag_config: RagToolConfig) -> object | None:
        """use_wiki_first=True이고 위키 어댑터가 있으면 위키 우선 검색을, 아니면 hybrid를 반환."""
        if rag_config.use_wiki_first and self._wiki_search is not None:
            return self._wiki_search
        return self._get_hybrid_search()

    def create(
        self, tool_id: str, request_id: str = "", tool_config: dict | None = None
    ) -> BaseTool:
        """내부 tool_id에 해당하는 BaseTool 인스턴스 반환 (동기)."""
        get_tool_meta(tool_id)  # 존재 여부 검증 (Unknown tool_id → ValueError)

        match tool_id:
            case "internal_document_search":
                from src.application.rag_agent.tools import InternalDocumentSearchTool

                rag_config = self._parse_rag_config(tool_config)
                effective_threshold = self._resolve_score_threshold(rag_config)
                search_use_case = self._select_search(rag_config)
                effective_filter = self._merge_kb_filter(rag_config)
                return InternalDocumentSearchTool(
                    hybrid_search_use_case=search_use_case,
                    request_id=request_id,
                    top_k=rag_config.top_k,
                    search_mode=rag_config.search_mode,
                    rrf_k=rag_config.rrf_k,
                    score_threshold=effective_threshold,
                    metadata_filter=effective_filter,
                    collection_name=rag_config.collection_name,
                    es_index=rag_config.es_index,
                    name=sanitize_tool_name(
                        rag_config.tool_name, fallback="internal_document_search"
                    ),
                    description=rag_config.tool_description,
                    # ── M4: retrieval 영속화 wiring (Optional — None이면 영속화 skip) ──
                    tracker=self._tracker,
                    logger=self._logger,
                    config=self._obs_config,
                    # ── agent-user-context Design §7.1: AuthContext 주입 ──
                    auth_ctx=self._auth_ctx,
                    # ── rag-routed-integration D2: 라우팅 opt-in 배선 ──
                    use_routed_search=rag_config.use_routed_search,
                    routed_retrieval_getter=self._routed_retrieval_getter,
                )
            case "tavily_search":
                from src.infrastructure.web_search.tavily_tool import TavilySearchTool

                return TavilySearchTool(
                    api_key=self._tavily_api_key,
                    # ── M5: retrieval 영속화 wiring ──
                    tracker=self._tracker,
                    logger=self._logger,
                    config=self._obs_config,
                )
            case "wiki_read":
                from src.infrastructure.wiki.wiki_read_tool import WikiReadTool

                if self._wiki_session_factory is None or self._wiki_repo_builder is None:
                    raise ValueError(
                        "wiki_read 도구는 wiki_session_factory/wiki_repo_builder "
                        "주입이 필요합니다 (ToolFactory 설정 오류)"
                    )
                return WikiReadTool(
                    session_factory=self._wiki_session_factory,
                    repo_builder=self._wiki_repo_builder,
                    request_id=request_id,
                    logger=self._logger,
                )
            case "wiki_list":
                from src.infrastructure.wiki.wiki_list_tool import WikiListTool

                if (
                    self._wiki_session_factory is None
                    or self._wiki_repo_builder is None
                    or self._wiki_folder_repo_builder is None
                ):
                    raise ValueError(
                        "wiki_list 도구는 wiki_session_factory/wiki_repo_builder/"
                        "wiki_folder_repo_builder 주입이 필요합니다 (ToolFactory 설정 오류)"
                    )
                return WikiListTool(
                    session_factory=self._wiki_session_factory,
                    repo_builder=self._wiki_repo_builder,
                    folder_repo_builder=self._wiki_folder_repo_builder,
                    request_id=request_id,
                    logger=self._logger,
                )
            case "excel_export":
                from src.infrastructure.excel_export.excel_export_tool import ExcelExportTool

                return ExcelExportTool()
            case "python_code_executor":
                from src.application.tools.code_executor_tool import create_code_executor_tool

                return create_code_executor_tool(self._logger)
            case _:
                raise ValueError(f"Unsupported tool_id: {tool_id!r}")

    async def create_async(
        self,
        tool_id: str,
        request_id: str = "",
        mcp_repository=None,
        tool_config: dict | None = None,
        *,
        subject_user_id: str | None = None,
    ) -> BaseTool:
        """
        tool_id에 해당하는 BaseTool 인스턴스 반환 (비동기).

        - MCP 형식(`mcp:{srv}:{tool}` / 레거시 `mcp_{srv}`): MCPToolLoader로 분기
        - 그 외: 동기 create() 위임
        """
        ref = parse_mcp_tool_id(tool_id)
        if ref is not None:
            return await self._create_mcp_tool(
                ref, tool_id, request_id, mcp_repository, subject_user_id
            )

        return self.create(tool_id, request_id, tool_config=tool_config)

    async def create_all_async(
        self,
        tool_id: str,
        request_id: str = "",
        mcp_repository=None,
        tool_config: dict | None = None,
        *,
        subject_user_id: str | None = None,
    ) -> list[BaseTool]:
        """tool_id가 가리키는 도구 '전부'를 반환한다.

        Design Ref: fix-mcp-tool-call-not-reaching-server §6.1 E6 —
        레거시 `mcp_{server}`는 서버 하나를 가리킬 뿐 도구를 특정하지 못한다.
        첫 도구만 바인딩하면 워커 description이 안내한 나머지 도구는 LLM의
        도구 목록에 없어 호출이 성립하지 않고, MCP 서버에는 아무 요청도 가지
        않는다(module-1 실측). 서버 단위 참조는 도구 전체를 워커에 넘긴다.

        - `mcp:{srv}:{tool}` — 지정 도구 1개
        - `mcp_{srv}` — 서버가 노출하는 도구 전체
        - 비-MCP — 기존 동기 create() 결과 1개
        """
        ref = parse_mcp_tool_id(tool_id)
        if ref is None:
            return [self.create(tool_id, request_id, tool_config=tool_config)]

        # Design Ref: mcp-identity-header §1.1 — 주체는 인자로만 흐른다.
        # bind_auth_ctx 같은 싱글톤 가변 필드는 동시 요청에서 섞인다.
        tools = await self._load_mcp_tools(
            ref, tool_id, request_id, mcp_repository, subject_user_id
        )
        if not ref.is_server_level:
            return [self._bind_tool(ref, tool_id, request_id, tools)]

        self._logger.info(
            "MCP tools bound",
            request_id=request_id,
            tool_id=tool_id,
            bound_tools=[getattr(t, "mcp_tool_name", None) for t in tools],
            available=len(tools),
            server_level=True,
        )
        return tools

    async def _create_mcp_tool(
        self,
        ref: McpToolRef,
        tool_id: str,
        request_id: str,
        mcp_repository,
        subject_user_id: str | None = None,
    ) -> BaseTool:
        """MCP 서버에서 도구를 로드해 워커에 바인딩할 단일 도구를 고른다.

        하위호환 경로 — 복수 바인딩이 필요하면 create_all_async를 쓴다.
        """
        tools = await self._load_mcp_tools(
            ref, tool_id, request_id, mcp_repository, subject_user_id
        )
        return self._bind_tool(ref, tool_id, request_id, tools)

    async def _load_mcp_tools(
        self,
        ref: McpToolRef,
        tool_id: str,
        request_id: str,
        mcp_repository,
        subject_user_id: str | None = None,
    ) -> list[BaseTool]:
        """MCP 서버에 접속해 도구 목록을 로드한다 (§2.2 ① 구간)."""
        # Design Ref: fix-mcp-tool-call-not-reaching-server §2.2 —
        # 이 로그가 없으면 compile이 MCP 워커에 도달조차 못한 것이다.
        self._logger.info(
            "MCP tool binding start",
            request_id=request_id,
            tool_id=tool_id,
            server_id=ref.server_id,
            requested_tool=ref.tool_name,
        )
        if self._mcp_tool_loader is None:
            # Design Ref: §6.2 — 배선 오류는 워커 격리 대상이 아니다.
            raise McpWiringError(
                f"MCPToolLoader is required for tool_id={tool_id!r}"
            )
        repository = mcp_repository or self._mcp_repository
        if repository is None:
            raise McpWiringError(
                f"MCP repository is required for tool_id={tool_id!r}"
            )

        tools = await self._mcp_tool_loader.load_by_tool_id(
            tool_id=f"mcp_{ref.server_id}",
            repository=repository,
            request_id=request_id,
            subject_user_id=subject_user_id,
        )
        if not tools:
            raise ValueError(f"MCP tool not found: {tool_id!r}")
        return tools

    def _bind_tool(
        self,
        ref: McpToolRef,
        tool_id: str,
        request_id: str,
        tools: list[BaseTool],
    ) -> BaseTool:
        """로드된 도구 목록에서 워커에 바인딩할 도구 하나를 고르고 결과를 남긴다.

        Design Ref: §2.2 — "MCP tool bound"의 bound_tool이 의도한 도구와 다르면
        레거시 서버 단위 ID의 첫-도구 폴백(D1)이 원인이다.
        """
        if ref.is_server_level:
            # 레거시 서버 단위 워커 — 어떤 도구를 원했는지 알 수 없다.
            # 첫 도구로 폴백하되, 선택이 임의라는 사실을 남긴다.
            self._logger.warning(
                "Legacy server-level MCP worker — binding first tool",
                request_id=request_id,
                tool_id=tool_id,
                bound_tool=getattr(tools[0], "mcp_tool_name", None),
                available=len(tools),
            )
            self._log_bound(request_id, tool_id, tools[0], len(tools), fallback=True)
            return tools[0]

        for tool in tools:
            if getattr(tool, "mcp_tool_name", None) == ref.tool_name:
                self._log_bound(
                    request_id, tool_id, tool, len(tools), fallback=False
                )
                return tool
        # Design Ref: §6.1 E5 — "무엇이 있는지"를 알려줘야 진단이 한 번에 끝난다.
        available = [getattr(t, "mcp_tool_name", None) for t in tools]
        raise ValueError(
            f"MCP tool not found: {ref.tool_name!r} on server {ref.server_id!r} "
            f"(available: {available})"
        )

    def _log_bound(
        self,
        request_id: str,
        tool_id: str,
        tool: BaseTool,
        available: int,
        *,
        fallback: bool,
    ) -> None:
        """바인딩 결과 계측 (FR-01). exposed_name은 LLM에 노출되는 이름이다."""
        self._logger.info(
            "MCP tool bound",
            request_id=request_id,
            tool_id=tool_id,
            bound_tool=getattr(tool, "mcp_tool_name", None),
            exposed_name=getattr(tool, "name", None),
            exposed_name_len=len(getattr(tool, "name", "") or ""),
            available=available,
            fallback=fallback,
        )

    @staticmethod
    def _merge_kb_filter(rag_config: RagToolConfig) -> dict[str, str]:
        """kb-rag-filter D6: kb_id를 metadata_filter에 병합.

        D2: first-class kb_id 필드가 수동 metadata_filter["kb_id"] 키보다 우선.
        """
        if not rag_config.kb_id:
            return rag_config.metadata_filter
        return {**rag_config.metadata_filter, "kb_id": rag_config.kb_id}

    def _parse_rag_config(self, tool_config: dict | None) -> RagToolConfig:
        """tool_config dict → RagToolConfig 변환. None이면 기본값.

        action-category-compose-node GAP-I1: tool_config dict는 도구별 설정을
        공유한다(draft_arg_key 등). RAG 파서는 자기 필드만 취해 다른 도구의
        키가 섞여도 깨지지 않는다.
        """
        if not tool_config:
            return RagToolConfig()
        known = {f.name for f in dataclasses.fields(RagToolConfig)}
        return RagToolConfig(**{k: v for k, v in tool_config.items() if k in known})

    def _resolve_score_threshold(self, rag_config: RagToolConfig) -> float:
        """벡터 코사인 컷오프 임계값 결정.

        에이전트가 명시(score_threshold is not None)하면 그 값을,
        미설정(None)이면 전역 기본값(settings.rag_vector_score_threshold)을 사용한다.
        """
        if rag_config.score_threshold is not None:
            return rag_config.score_threshold
        from src.config import settings

        return settings.rag_vector_score_threshold
