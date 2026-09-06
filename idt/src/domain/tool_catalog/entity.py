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
    # Design Ref: mcp-tool-category-routing §3.1 (FR-01/FR-02) —
    # 워커 노드 종류를 결정하는 분류(search/collect/analysis/action).
    # None = 미분류 → 이 사이클 이전과 동일한 react 경로 (FR-14).
    # is_builtin과 동일하게 관리자 지정값이며 sync가 덮어쓰지 않는다 (D-02).
    category: str | None = None
    # 워커 1회 실행당 도구 호출 상한. None = ToolCallBudgetPolicy 기본값.
    max_tool_calls: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
