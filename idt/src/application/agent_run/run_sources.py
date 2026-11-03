"""실행 기록에서 표시용 근거를 모은다.

Design Ref: agent-run-source-citations §2.1 — 실시간과 재진입이 공유하는 단일 경로.
Design Ref: §6.1 — 근거는 부가 정보이므로 실패는 여기서 흡수하고 답변을 막지 않는다.
"""
from typing import Iterable

from src.domain.agent_run.entities import RetrievalSource, ToolCall
from src.domain.agent_run.interfaces import AgentRunRepositoryInterface
from src.domain.agent_run.source_policy import (
    WEB_COLLECTION,
    McpToolInfo,
    RunEvidence,
    RunSourceItem,
    RunSourcePolicy,
)
from src.domain.agent_run.value_objects import RunId
from src.domain.doc_browse.interfaces import DocumentMetadataRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp.policy import MCPConnectionPolicy
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface
from src.domain.tool_catalog.mcp_tool_id import parse_mcp_tool_id

_MCP_RUNTIME_PREFIX = "mcp_"


class RunSourcesService:
    def __init__(
        self,
        agent_run_repo: AgentRunRepositoryInterface,
        document_repo: DocumentMetadataRepositoryInterface,
        tool_catalog_repo: ToolCatalogRepositoryInterface,
        logger: LoggerInterface,
        *,
        max_items: int,
    ) -> None:
        self._agent_run_repo = agent_run_repo
        self._document_repo = document_repo
        self._tool_catalog_repo = tool_catalog_repo
        self._logger = logger
        self._max_items = max_items

    async def build_for_runs(
        self, run_ids: list[RunId], request_id: str,
    ) -> dict[str, list[RunSourceItem]]:
        """run_id 문자열 → 근거 목록. 근거가 없는 런은 키가 없다."""
        if not run_ids:
            return {}
        try:
            retrievals = await self._agent_run_repo.find_retrievals_by_runs(run_ids)
            tool_calls = await self._agent_run_repo.find_tool_calls_by_runs(run_ids)
        except Exception as e:
            self._logger.warning(
                "run sources evidence read failed",
                exception=e, request_id=request_id, run_count=len(run_ids),
            )
            return {}
        filenames = await self._filenames(_flatten(retrievals.values()), request_id)
        mcp_tools = await self._mcp_tools(_flatten(tool_calls.values()), request_id)
        built = {}
        for run_id in run_ids:
            evidence = RunEvidence(
                retrievals=retrievals.get(run_id.value, []),
                tool_calls=tool_calls.get(run_id.value, []),
                filenames=filenames,
                mcp_tools=mcp_tools,
            )
            items = RunSourcePolicy.build(evidence, max_items=self._max_items)
            if items:
                built[run_id.value] = items
        return built

    async def _filenames(
        self, retrievals: list[RetrievalSource], request_id: str,
    ) -> dict[str, str]:
        document_ids = sorted({
            r.document_id for r in retrievals
            if r.document_id and r.collection_name != WEB_COLLECTION
            and not (r.metadata_json or {}).get("filename")
        })
        if not document_ids:
            return {}
        try:
            return await self._document_repo.find_filenames(document_ids, request_id)
        except Exception as e:
            # 라벨만 폴백으로 낮추면 되므로 근거 전체를 버리지 않는다.
            self._logger.warning(
                "run sources filename read failed",
                exception=e, request_id=request_id,
            )
            return {}

    async def _mcp_tools(
        self, tool_calls: list[ToolCall], request_id: str,
    ) -> dict[str, McpToolInfo]:
        if not any(c.tool_name.startswith(_MCP_RUNTIME_PREFIX) for c in tool_calls):
            return {}
        try:
            entries = await self._tool_catalog_repo.list_active(request_id)
        except Exception as e:
            # 카탈로그 없이는 부작용 여부를 알 수 없어 MCP 칩만 제외한다 (fail-closed).
            self._logger.warning(
                "run sources tool catalog read failed",
                exception=e, request_id=request_id,
            )
            return {}
        tools: dict[str, McpToolInfo] = {}
        for entry in entries:
            ref = parse_mcp_tool_id(entry.tool_id)
            if ref is None or ref.is_server_level:
                continue
            # 런타임 이름은 해시 접미사가 붙을 수 있어 역파싱 대신 정방향 계산한다.
            runtime_name = MCPConnectionPolicy.build_tool_name(
                f"{_MCP_RUNTIME_PREFIX}{ref.server_id}_{ref.tool_name}"
            )
            tools[runtime_name] = McpToolInfo(
                display_name=entry.name,
                requires_approval=entry.requires_approval,
                category=entry.category,
                tool_id=entry.tool_id,
            )
        return tools


def _flatten(groups: Iterable[list]) -> list:
    return [item for group in groups for item in group]
