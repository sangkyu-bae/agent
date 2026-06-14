"""ToolFactory: tool_id → LangChain BaseTool 인스턴스 생성."""
from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool

from src.domain.agent_builder.rag_tool_config import RagToolConfig, sanitize_tool_name
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.agent_run.auth_context import AuthContext
from src.domain.logging.interfaces.logger_interface import LoggerInterface


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
        tracker: Any = None,                       # ★ M4: RunTracker | None
        run_observability_config: Any = None,      # ★ M4: RunObservabilityConfig | None
    ) -> None:
        self._logger = logger
        self._hybrid_search = hybrid_search_use_case
        self._hybrid_search_getter = hybrid_search_use_case_getter
        self._tavily_api_key = tavily_api_key
        self._mcp_tool_loader = mcp_tool_loader
        self._tracker = tracker
        self._obs_config = run_observability_config
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
                return InternalDocumentSearchTool(
                    hybrid_search_use_case=self._get_hybrid_search(),
                    request_id=request_id,
                    top_k=rag_config.top_k,
                    search_mode=rag_config.search_mode,
                    rrf_k=rag_config.rrf_k,
                    score_threshold=effective_threshold,
                    metadata_filter=rag_config.metadata_filter,
                    collection_name=rag_config.collection_name,
                    es_index=rag_config.es_index,
                    name=sanitize_tool_name(rag_config.tool_name),
                    description=rag_config.tool_description,
                    # ── M4: retrieval 영속화 wiring (Optional — None이면 영속화 skip) ──
                    tracker=self._tracker,
                    logger=self._logger,
                    config=self._obs_config,
                    # ── agent-user-context Design §7.1: AuthContext 주입 ──
                    auth_ctx=self._auth_ctx,
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
    ) -> BaseTool:
        """
        tool_id에 해당하는 BaseTool 인스턴스 반환 (비동기).

        - `mcp_` 접두사: MCPToolLoader로 분기 (DB 조회 + SSE 연결)
        - 그 외: 동기 create() 위임
        """
        if tool_id.startswith("mcp_"):
            if self._mcp_tool_loader is None:
                raise ValueError(
                    f"MCPToolLoader is required for tool_id={tool_id!r}"
                )
            tools = await self._mcp_tool_loader.load_by_tool_id(
                tool_id=tool_id,
                repository=mcp_repository,
                request_id=request_id,
            )
            if not tools:
                raise ValueError(f"MCP tool not found: {tool_id!r}")
            return tools[0]

        return self.create(tool_id, request_id, tool_config=tool_config)

    def _parse_rag_config(self, tool_config: dict | None) -> RagToolConfig:
        """tool_config dict → RagToolConfig 변환. None이면 기본값."""
        if not tool_config:
            return RagToolConfig()
        return RagToolConfig(**tool_config)

    def _resolve_score_threshold(self, rag_config: RagToolConfig) -> float:
        """벡터 코사인 컷오프 임계값 결정.

        에이전트가 명시(score_threshold is not None)하면 그 값을,
        미설정(None)이면 전역 기본값(settings.rag_vector_score_threshold)을 사용한다.
        """
        if rag_config.score_threshold is not None:
            return rag_config.score_threshold
        from src.config import settings

        return settings.rag_vector_score_threshold
