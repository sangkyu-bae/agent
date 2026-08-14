"""NullSelectionCache — Design Ref: §4.2.

v1 no-op 구현체. 캐시 도입 시 이 클래스만 교체하면 되고 셀렉터는 그대로다.
"""
from collections.abc import Sequence

from src.domain.tool_selection.interfaces.selection_cache_port import (
    SelectionCachePort,
)


class NullSelectionCache(SelectionCachePort):
    """항상 미스. 아무것도 저장하지 않는다 (Plan FR-09)."""

    async def get(self, key: str) -> tuple[str, ...] | None:
        return None

    async def set(self, key: str, tool_ids: Sequence[str]) -> None:
        return None
