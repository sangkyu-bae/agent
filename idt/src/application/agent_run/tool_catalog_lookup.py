"""런타임 도구 이름 → 카탈로그 표시 정보.

Design Ref: agent-run-tool-trace §3.2 — RunSourcesService 의 정방향 이름 계산을
추출해 근거 칩과 도구 실행 내역이 같이 쓴다. 조회 실패는 빈 결과로 흡수하고,
소비자가 각자 폴백한다 (근거: MCP 칩 제외 / 내역: 이름 폴백).
"""
from src.domain.agent_run.entities import ToolCall
from src.domain.agent_run.tool_trace_policy import ToolDisplayInfo, ToolTraceSource
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp.policy import MCPConnectionPolicy
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface
from src.domain.tool_catalog.mcp_tool_id import parse_mcp_tool_id

MCP_RUNTIME_PREFIX = "mcp_"
_INTERNAL_PREFIX = "internal:"


class ToolCatalogLookup:
    def __init__(
        self,
        tool_catalog_repo: ToolCatalogRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._tool_catalog_repo = tool_catalog_repo
        self._logger = logger

    async def resolve(
        self, tool_calls: list[ToolCall], request_id: str,
    ) -> dict[str, ToolDisplayInfo]:
        """호출이 없으면 카탈로그를 읽지 않는다."""
        if not tool_calls:
            return {}
        try:
            entries = await self._tool_catalog_repo.list_active(request_id)
        except Exception as e:
            self._logger.warning(
                "tool catalog lookup failed", exception=e, request_id=request_id,
            )
            return {}
        tools: dict[str, ToolDisplayInfo] = {}
        for entry in entries:
            runtime_name, source = _runtime_name(entry.tool_id)
            if runtime_name is None:
                continue
            tools[runtime_name] = ToolDisplayInfo(
                display_name=entry.name,
                source=source,
                requires_approval=entry.requires_approval,
                category=entry.category,
                tool_id=entry.tool_id,
            )
        return tools


def _runtime_name(tool_id: str) -> tuple[str | None, ToolTraceSource]:
    if tool_id.startswith(_INTERNAL_PREFIX):
        # 실DB 확인(2026-11-03): internal 도구는 tool_id 접미가 런타임 이름과 같다.
        return tool_id[len(_INTERNAL_PREFIX):] or None, ToolTraceSource.INTERNAL
    ref = parse_mcp_tool_id(tool_id)
    if ref is None or ref.is_server_level:
        return None, ToolTraceSource.MCP
    # 런타임 이름은 해시 접미사가 붙을 수 있어 역파싱 대신 정방향 계산한다.
    return (
        MCPConnectionPolicy.build_tool_name(
            f"{MCP_RUNTIME_PREFIX}{ref.server_id}_{ref.tool_name}"
        ),
        ToolTraceSource.MCP,
    )
