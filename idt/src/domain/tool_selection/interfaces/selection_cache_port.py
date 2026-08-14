"""SelectionCachePort — Design Ref: §4.2.

v1은 NullSelectionCache(no-op)를 주입한다. 인터페이스를 먼저 뚫어두는 이유는
나중에 TTL 캐시로 교체할 때 셀렉터 코드를 건드리지 않기 위함이다 (Plan FR-09).
"""
from abc import ABC, abstractmethod
from collections.abc import Sequence


class SelectionCachePort(ABC):
    """선별 결과 캐시. 키 생성은 policies.build_cache_key가 담당한다."""

    @abstractmethod
    async def get(self, key: str) -> tuple[str, ...] | None:
        """캐시된 도구 ID 목록. 미스면 None."""

    @abstractmethod
    async def set(self, key: str, tool_ids: Sequence[str]) -> None:
        """선별 결과를 저장한다. 실패해도 예외를 던지지 않는다."""
