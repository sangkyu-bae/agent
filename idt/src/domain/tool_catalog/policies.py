"""ToolIdFormatPolicy: tool_id 포맷 검증."""
import re


class ToolIdFormatPolicy:
    INTERNAL_PATTERN = re.compile(r"^internal:[a-z_]+$")
    MCP_PATTERN = re.compile(
        r"^mcp:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:.+$"
    )

    @staticmethod
    def validate(tool_id: str, source: str) -> None:
        if source == "internal":
            if not ToolIdFormatPolicy.INTERNAL_PATTERN.match(tool_id):
                raise ValueError(
                    f"Internal tool_id must match 'internal:<snake_case>', got: {tool_id!r}"
                )
        elif source == "mcp":
            if not ToolIdFormatPolicy.MCP_PATTERN.match(tool_id):
                raise ValueError(
                    f"MCP tool_id must match 'mcp:<uuid>:<name>', got: {tool_id!r}"
                )
        else:
            raise ValueError(f"Unknown source: {source!r}")
