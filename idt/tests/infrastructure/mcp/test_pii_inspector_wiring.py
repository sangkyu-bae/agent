"""MCPToolLoader → MCPToolRegistry → MCPToolAdapter 로 pii_inspector가 전달되는지.

Design §4.6 (FR-11): 카테고리 파이프라인도 같은 어댑터를 거치므로, 생성 경로 전체에
검사기가 실려야 react 워커·파이프라인이 같은 지점에서 검사된다.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.mcp.value_objects import (
    MCPServerConfig,
    MCPTransport,
    StdioServerConfig,
)
from src.infrastructure.mcp.tool_registry import MCPToolRegistry


def _config() -> MCPServerConfig:
    return MCPServerConfig(
        name="srv",
        transport=MCPTransport.STDIO,
        stdio=StdioServerConfig(command="python", args=["s.py"]),
    )


class _Inspector:
    """명시적 fake. 어댑터 필드는 PiiInspectPort isinstance 검증을 거친다
    (Python 3.12 Protocol 검사는 정적 속성 조회라 MagicMock은 통과하지 못한다)."""

    def inspect(self, value):
        return {}

    def find_orphan_argument(self, value):
        return None


async def test_registry_passes_inspector_to_every_adapter():
    inspector = _Inspector()
    tool = MagicMock()
    tool.name = "get_inquiry"
    tool.description = "d"
    tool.inputSchema = {"type": "object"}
    session = AsyncMock()
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[tool, tool]))
    with patch(
        "src.infrastructure.mcp.tool_registry.MCPClientFactory.create_session"
    ) as ctx:
        ctx.return_value.__aenter__ = AsyncMock(return_value=session)
        ctx.return_value.__aexit__ = AsyncMock(return_value=None)
        tools = await MCPToolRegistry([_config()], pii_inspector=inspector).get_tools()
    assert tools and all(t.pii_inspector is inspector for t in tools)


def test_registry_inspector_defaults_to_none():
    assert MCPToolRegistry([_config()])._pii_inspector is None


def test_loader_forwards_inspector_to_registry():
    from src.infrastructure.mcp_registry.mcp_tool_loader import MCPToolLoader

    inspector = MagicMock()
    loader = MCPToolLoader(logger=MagicMock(), pii_inspector=inspector)
    assert loader._pii_inspector is inspector
