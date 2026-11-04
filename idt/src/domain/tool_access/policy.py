"""ToolAccessPolicy — 도구 허용 판정의 단일 규칙.

Design Ref: tool-access-control §3.5
  role == admin                         → 전부 허용
  role == user                          → 기본 세트 ∪ 소속 부서 허용 ∪ 사용자 허용
  그 외(anonymous·미상)                 → 전부 차단 (Fail-Closed)

grants(합집합)를 모으는 일은 Repository/Resolver 가, 판정 규칙은 여기만 가진다.
차단(deny) 규칙은 범위 밖(Plan §2.2) — 필요해지면 이 메서드에서 확장한다.
"""
from src.domain.tool_access.tool_ids import to_catalog_tool_id
from src.domain.tool_access.value_objects import ToolAccessSet

_ADMIN = "admin"
_USER = "user"


class ToolAccessPolicy:
    @staticmethod
    def build(*, role: str, grants: frozenset[str]) -> ToolAccessSet:
        if role == _ADMIN:
            return ToolAccessSet.admin()
        if role != _USER:
            return ToolAccessSet.deny_all()
        normalized = {to_catalog_tool_id(g) for g in grants}
        normalized.discard(None)
        return ToolAccessSet(is_admin=False, allowed=frozenset(normalized))  # type: ignore[arg-type]
