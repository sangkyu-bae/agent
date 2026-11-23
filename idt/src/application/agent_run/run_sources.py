"""실행 기록에서 표시용 근거를 모은다.

Design Ref: agent-run-source-citations §2.1 — 실시간과 재진입이 공유하는 단일 경로.
Design Ref: §6.1 — 근거는 부가 정보이므로 실패는 여기서 흡수하고 답변을 막지 않는다.
"""
from typing import Any, Iterable

from src.application.agent_run.tool_catalog_lookup import (
    MCP_RUNTIME_PREFIX,
    ToolCatalogLookup,
)
from src.domain.agent_run.entities import RetrievalSource, ToolCall
from src.domain.agent_run.interfaces import AgentRunRepositoryInterface
from src.domain.agent_run.source_policy import (
    WEB_COLLECTION,
    McpToolInfo,
    RunEvidence,
    RunSourceItem,
    RunSourcePolicy,
)
from src.domain.agent_run.tool_trace_policy import ToolTraceSource
from src.domain.agent_run.value_objects import RunId
from src.domain.doc_browse.interfaces import DocumentMetadataRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface


class RunSourcesService:
    def __init__(
        self,
        agent_run_repo: AgentRunRepositoryInterface,
        document_repo: DocumentMetadataRepositoryInterface,
        tool_catalog_repo: ToolCatalogRepositoryInterface,
        logger: LoggerInterface,
        *,
        max_items: int,
        viewer_enricher: Any | None = None,
        citation_enricher: Any | None = None,
    ) -> None:
        self._agent_run_repo = agent_run_repo
        self._document_repo = document_repo
        # agent-run-tool-trace §3.2 — 이름 계산은 도구 실행 내역과 공유한다.
        self._catalog = ToolCatalogLookup(tool_catalog_repo, logger)
        self._logger = logger
        self._max_items = max_items
        # source-passage-viewer §11.2 #2 — duck typing(enrich). None = 원문 뷰어 없음.
        self._viewer_enricher = viewer_enricher
        # answer-citation-verification S9 — duck typing(load·apply). None = 인용 없음.
        self._citation_enricher = citation_enricher

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
        version_labels = await self._version_labels(
            _flatten(retrievals.values()), request_id
        )
        mcp_tools = await self._mcp_tools(_flatten(tool_calls.values()), request_id)
        citations = await self._load_citations(run_ids, request_id)
        built = {}
        for run_id in run_ids:
            evidence = RunEvidence(
                retrievals=retrievals.get(run_id.value, []),
                tool_calls=tool_calls.get(run_id.value, []),
                filenames=filenames,
                mcp_tools=mcp_tools,
                version_labels=version_labels,
            )
            items = RunSourcePolicy.build(evidence, max_items=self._max_items)
            # Analysis G-1: 인용을 먼저 적용해야 보충된 칩도 원문 뷰어를 받는다.
            if citations is not None:
                items = self._cite(
                    items, citations.get(run_id.value), evidence, request_id
                )
            items = await self._enrich(items, evidence, request_id)
            if items:
                built[run_id.value] = items
        return built

    async def _load_citations(
        self, run_ids: list[RunId], request_id: str
    ) -> dict | None:
        """저장된 인용을 실행 묶음당 1회 읽는다.

        미주입·실패면 None — 인용 단계를 건너뛴다(§6).
        """
        if self._citation_enricher is None:
            return None
        try:
            return await self._citation_enricher.load(
                [r.value for r in run_ids], request_id
            )
        except Exception as e:
            self._logger.warning(
                "run sources citation load failed (sources unaffected)",
                exception=e, request_id=request_id,
            )
            return None

    def _cite(
        self, items: list[RunSourceItem], stored: Any, evidence: RunEvidence,
        request_id: str,
    ) -> list[RunSourceItem]:
        try:
            return self._citation_enricher.apply(items, stored, evidence)
        except Exception as e:
            self._logger.warning(
                "run sources citation apply failed (sources unaffected)",
                exception=e, request_id=request_id,
            )
            return items

    async def _enrich(
        self, items: list[RunSourceItem], evidence: RunEvidence, request_id: str,
    ) -> list[RunSourceItem]:
        """원문 뷰어 정보를 덧붙인다 — 실패하면 덧붙이기 전 목록 (source-passage-viewer §6)."""
        if self._viewer_enricher is None or not items:
            return items
        try:
            return await self._viewer_enricher.enrich(items, evidence, request_id)
        except Exception as e:
            self._logger.warning(
                "run sources viewer enrich failed (sources unaffected)",
                exception=e, request_id=request_id,
            )
            return items

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

    async def _version_labels(
        self, retrievals: list[RetrievalSource], request_id: str,
    ) -> dict[str, str]:
        """document-revision module-6: 근거 칩 버전 라벨. 실패해도 라벨만 생략한다."""
        document_ids = sorted({
            r.document_id for r in retrievals
            if r.document_id and r.collection_name != WEB_COLLECTION
        })
        if not document_ids:
            return {}
        try:
            return await self._document_repo.find_version_labels(
                document_ids, request_id
            )
        except Exception as e:
            self._logger.warning(
                "run sources version label read failed",
                exception=e, request_id=request_id,
            )
            return {}

    async def _mcp_tools(
        self, tool_calls: list[ToolCall], request_id: str,
    ) -> dict[str, McpToolInfo]:
        if not any(c.tool_name.startswith(MCP_RUNTIME_PREFIX) for c in tool_calls):
            return {}
        # 카탈로그 없이는 부작용 여부를 알 수 없어 MCP 칩만 제외된다 (fail-closed).
        # 조회 실패는 lookup 이 warning 을 남기고 빈 결과로 흡수한다.
        tools = await self._catalog.resolve(tool_calls, request_id)
        return {
            runtime_name: McpToolInfo(
                display_name=info.display_name,
                requires_approval=info.requires_approval,
                category=info.category,
                tool_id=info.tool_id,
            )
            for runtime_name, info in tools.items()
            if info.source == ToolTraceSource.MCP
        }


def _flatten(groups: Iterable[list]) -> list:
    return [item for group in groups for item in group]
