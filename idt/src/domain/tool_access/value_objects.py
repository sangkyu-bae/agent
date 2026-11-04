"""ToolAccessSet — 한 실행 주체가 쓸 수 있는 도구 집합 (불변).

Design Ref: tool-access-control §3.1 — 판정 지점(카탈로그·저장·실행·승인 집행)은
모두 이 값 하나만 받는다. 싱글턴(ToolFactory·WorkflowCompiler)에는 가변 필드가
아니라 인자로만 넘긴다 (§1.2 "주체는 인자로만 흐른다").
"""
from dataclasses import dataclass, field
from typing import Literal

from src.domain.tool_access.tool_ids import to_catalog_tool_id
from src.domain.tool_catalog.mcp_tool_id import parse_mcp_tool_id


@dataclass(frozen=True)
class ToolAccessSet:
    is_admin: bool
    allowed: frozenset[str] = field(default_factory=frozenset)  # 카탈로그 표기

    @staticmethod
    def deny_all() -> "ToolAccessSet":
        """Fail-Closed 기본값 — 실행자를 특정할 수 없을 때."""
        return ToolAccessSet(is_admin=False, allowed=frozenset())

    @staticmethod
    def admin() -> "ToolAccessSet":
        return ToolAccessSet(is_admin=True, allowed=frozenset())

    def allows(self, raw_tool_id: str | None) -> bool:
        if self.is_admin:
            return True
        catalog_id = to_catalog_tool_id(raw_tool_id)
        return catalog_id is not None and catalog_id in self.allowed

    def allows_reference(self, raw_tool_id: str | None) -> bool:
        """워커가 가리키는 참조를 유지할 수 있는가 (저장·포크 판정용).

        개별 도구는 allows 와 같다. 레거시 서버 단위(`mcp_{srv}`)는 그 서버 도구 중
        하나라도 허용이면 True — 실제 바인딩은 실행 시점에 허용 도구만 한다 (FR-12).
        """
        if self.is_admin:
            return True
        ref = parse_mcp_tool_id(raw_tool_id or "")
        if ref is not None and ref.is_server_level:
            return bool(self.allowed_mcp_tool_names(ref.server_id))
        return self.allows(raw_tool_id)

    def allowed_mcp_tool_names(self, server_id: str) -> frozenset[str] | None:
        """서버 단위 참조(`mcp_{srv}`)용 — 그 서버에서 허용된 도구명.

        None 이면 전부 허용(admin). 빈 집합이면 하나도 허용되지 않음.
        """
        if self.is_admin:
            return None
        names: set[str] = set()
        for tool_id in self.allowed:
            ref = parse_mcp_tool_id(tool_id)
            if ref is not None and ref.server_id == server_id and ref.tool_name:
                names.add(ref.tool_name)
        return frozenset(names)


@dataclass(frozen=True)
class ToolGrantSource:
    """관리자 사용자 조회 응답용 — 상속된 허용의 출처."""

    kind: Literal["default", "department"]
    department_id: str | None = None
    department_name: str | None = None
