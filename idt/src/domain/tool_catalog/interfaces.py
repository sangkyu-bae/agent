"""ToolCatalogRepositoryInterface: 도구 카탈로그 저장소 추상화."""
from abc import ABC, abstractmethod

from src.domain.tool_catalog.entity import ToolCatalogEntry


class _Unset:
    """'인자 생략'과 '명시적 None'을 구분하는 센티널 (§4.2 부분 갱신)."""

    def __repr__(self) -> str:  # pragma: no cover - 디버깅 표시용
        return "<UNSET>"


UNSET = _Unset()
_UNSET = UNSET


class ToolCatalogRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, entry: ToolCatalogEntry, request_id: str) -> ToolCatalogEntry: ...

    @abstractmethod
    async def upsert_by_tool_id(
        self, entry: ToolCatalogEntry, request_id: str
    ) -> ToolCatalogEntry: ...

    @abstractmethod
    async def find_by_tool_id(
        self, tool_id: str, request_id: str
    ) -> ToolCatalogEntry | None: ...

    @abstractmethod
    async def list_active(self, request_id: str) -> list[ToolCatalogEntry]: ...

    @abstractmethod
    async def deactivate_by_mcp_server(
        self, mcp_server_id: str, request_id: str
    ) -> int: ...

    @abstractmethod
    async def set_builtin(
        self, tool_id: str, is_builtin: bool, request_id: str
    ) -> ToolCatalogEntry | None: ...

    @abstractmethod
    async def list_builtin(self, request_id: str) -> list[ToolCatalogEntry]: ...

    @abstractmethod
    async def update_metadata(
        self,
        tool_id: str,
        request_id: str,
        *,
        category: str | None = _UNSET,
        max_tool_calls: int | None = _UNSET,
        # approval-gate Design §3.3 (FR-02): 승인 필요 여부 관리자 토글.
        # sync(upsert)는 이 컬럼을 건드리지 않으므로 여기가 유일한 쓰기 경로다.
        requires_approval: bool = _UNSET,
    ) -> ToolCatalogEntry | None:
        """Design Ref: mcp-tool-category-routing §4.2 — 분류·호출 상한 부분 갱신.

        인자를 생략하면 해당 컬럼을 건드리지 않는다. 명시적으로 None을 주면
        '미분류로 되돌리기'를 뜻하므로, 생략과 None을 구분하기 위해 _UNSET
        센티널을 쓴다. 대상이 없으면 None을 반환한다.
        """
        ...
