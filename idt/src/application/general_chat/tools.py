"""General Chat 에이전트 도구 빌더.

3종 도구를 통합:
  - TavilySearchTool (SEARCH-001): 실시간 웹 검색
  - InternalDocumentSearchTool (RAG-001): BM25+Vector 내부 문서 검색
  - MCP Tools (MCP-REG-001): DB 등록 MCP 서버 동적 로드 (10분 TTL 캐시)
"""
from __future__ import annotations

import time
from typing import Any

from src.domain.logging.interfaces.logger_interface import LoggerInterface


class MCPToolCache:
    """MCP Tool 목록을 TTL 기반으로 인메모리 캐시.

    만료 시 자동 재로드, 실패 시 WARNING 로그 + 빈 리스트 반환 (서비스 중단 방지).
    """

    _cache: dict[str, tuple[list, float]] = {}  # "__all__" → (tools, expires_at)

    @classmethod
    async def get_or_load(
        cls,
        load_mcp_use_case: Any,
        request_id: str,
        ttl: int = 600,
        logger: LoggerInterface | None = None,
    ) -> list:
        """캐시 유효 시 캐시 반환, 만료·미스 시 DB에서 재로드."""
        key = "__all__"
        cached = cls._cache.get(key)
        if cached is not None:
            tools, expires_at = cached
            if time.time() < expires_at:
                return tools

        try:
            tools = await load_mcp_use_case.execute(request_id)
            cls._cache[key] = (tools, time.time() + ttl)
            return tools
        except Exception as e:
            if logger is not None:
                logger.warning(
                    "MCP tools load failed, returning empty list",
                    request_id=request_id,
                    exception=str(e),
                )
            return []


class ChatToolBuilder:
    """ReAct 에이전트용 도구 빌더.

    TavilySearchTool, InternalDocumentSearchTool, MCP Tools를 조합하여
    [Tavily, InternalDoc, *MCP] 순서의 도구 목록을 반환한다.
    """

    def __init__(
        self,
        tavily_tool: Any,
        internal_doc_tool: Any,
        mcp_cache: type[MCPToolCache],
        load_mcp_use_case: Any,
        logger: LoggerInterface | None = None,
    ) -> None:
        self._tavily = tavily_tool
        self._internal_doc = internal_doc_tool
        self._mcp_cache = mcp_cache
        self._load_mcp = load_mcp_use_case
        self._logger = logger

    async def build(self, top_k: int, request_id: str) -> list:
        """[TavilyTool, InternalDocTool(top_k), *MCPTools] 반환.

        Args:
            top_k: 내부 문서 검색 결과 수.
            request_id: 요청 추적 ID.
        """
        self._internal_doc.top_k = top_k

        mcp_tools = await self._mcp_cache.get_or_load(
            self._load_mcp,
            request_id=request_id,
            logger=self._logger,
        )

        return [self._tavily, self._internal_doc, *mcp_tools]
