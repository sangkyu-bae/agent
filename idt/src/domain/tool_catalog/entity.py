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
    # builtin-tools D1: 에이전트 생성 시 자동 주입 여부 (관리자 토글, sync 보존)
    is_builtin: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
