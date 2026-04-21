"""ToolCatalogEntry 도메인 엔티티."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ToolCatalogEntry:
    id: str
    tool_id: str
    source: str
    name: str
    description: str
    mcp_server_id: str | None = None
    requires_env: list[str] = field(default_factory=list)
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
