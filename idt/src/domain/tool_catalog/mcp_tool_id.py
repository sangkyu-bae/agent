"""MCP tool_id 파싱 — 카탈로그·에이전트 저장·실행의 단일 해석 지점.

두 가지 형식을 해석한다.

- ``mcp:{server_id}:{tool_name}`` — 카탈로그 형식(정상). 개별 도구를 가리킨다.
- ``mcp_{server_id}`` — 레거시 서버 단위 형식. 어떤 도구인지 특정하지 못한다.

레거시 형식은 개별 도구 단위로 전환하기 전에 저장된 에이전트를 위해 남겨둔다.
"""
from dataclasses import dataclass

_CATALOG_PREFIX = "mcp:"
_LEGACY_PREFIX = "mcp_"


@dataclass(frozen=True)
class McpToolRef:
    """MCP 도구 참조. tool_name이 None이면 서버만 특정된 상태다."""

    server_id: str
    tool_name: str | None

    @property
    def is_server_level(self) -> bool:
        return self.tool_name is None


def parse_mcp_tool_id(tool_id: str) -> McpToolRef | None:
    """MCP tool_id를 해석한다. MCP 형식이 아니면 None."""
    if not tool_id:
        return None

    if tool_id.startswith(_CATALOG_PREFIX):
        # 도구명에 콜론이 들어갈 수 있으므로 앞의 두 조각만 분리한다.
        _, _, rest = tool_id.partition(_CATALOG_PREFIX)
        server_id, sep, tool_name = rest.partition(":")
        if not server_id or not sep or not tool_name:
            return None
        return McpToolRef(server_id=server_id, tool_name=tool_name)

    if tool_id.startswith(_LEGACY_PREFIX):
        server_id = tool_id[len(_LEGACY_PREFIX):]
        if not server_id:
            return None
        return McpToolRef(server_id=server_id, tool_name=None)

    return None
