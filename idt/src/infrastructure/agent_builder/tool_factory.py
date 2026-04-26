"""ToolFactory: tool_id → LangChain BaseTool 인스턴스 생성."""
from langchain_core.tools import BaseTool

from src.domain.agent_builder.rag_tool_config import RagToolConfig
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ToolFactory:
    """tool_id에 해당하는 BaseTool 인스턴스를 동적으로 생성한다."""

    def __init__(
        self,
        logger: LoggerInterface,
        hybrid_search_use_case: object | None = None,
        tavily_api_key: str | None = None,
        mcp_tool_loader=None,
    ) -> None:
        self._logger = logger
        self._hybrid_search = hybrid_search_use_case
        self._tavily_api_key = tavily_api_key
        self._mcp_tool_loader = mcp_tool_loader

    def create(
        self, tool_id: str, request_id: str = "", tool_config: dict | None = None
    ) -> BaseTool:
        """내부 tool_id에 해당하는 BaseTool 인스턴스 반환 (동기)."""
        get_tool_meta(tool_id)  # 존재 여부 검증 (Unknown tool_id → ValueError)

        match tool_id:
            case "internal_document_search":
                from src.application.rag_agent.tools import InternalDocumentSearchTool

                rag_config = self._parse_rag_config(tool_config)
                return InternalDocumentSearchTool(
                    hybrid_search_use_case=self._hybrid_search,
                    request_id=request_id,
                    top_k=rag_config.top_k,
                    search_mode=rag_config.search_mode,
                    rrf_k=rag_config.rrf_k,
                    metadata_filter=rag_config.metadata_filter,
                    collection_name=rag_config.collection_name,
                    es_index=rag_config.es_index,
                    name=rag_config.tool_name,
                    description=rag_config.tool_description,
                )
            case "tavily_search":
                from src.infrastructure.web_search.tavily_tool import TavilySearchTool

                return TavilySearchTool(api_key=self._tavily_api_key)
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
