"""ToolAccessRepositoryInterface — 도구 허용 규칙 저장소 포트.

Design Ref: tool-access-control §3.3 — 기본 세트·부서·사용자 3테이블.
모든 tool_id 는 카탈로그 표기다 (정규화는 호출자 책임).

replace_* 의 `scope`: 이번 교체가 삭제·삽입할 수 있는 tool_id 범위(활성 카탈로그).
범위 밖 행(비활성 도구 규칙)은 건드리지 않는다 — 재활성화 시 권한 복원.
"""
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import Protocol


class ToolAccessCheckerPort(Protocol):
    """세션 없는 싱글턴(승인 집행기 등)용 단건 판정 포트 (Design §0 F4).

    구현은 호출마다 자기 세션을 연다. 예외를 던지지 않고 판정 실패는 False(Fail-Closed).
    """

    async def is_allowed(
        self, subject_user_id: str | None, tool_id: str, request_id: str
    ) -> bool: ...


class ToolAccessRepositoryInterface(ABC):
    @abstractmethod
    async def find_grants_for(
        self, user_id: int, department_ids: Sequence[str], request_id: str
    ) -> frozenset[str]:
        """기본 세트 ∪ 부서 허용(department_ids 중 하나라도) ∪ 사용자 허용."""

    @abstractmethod
    async def list_default(self, request_id: str) -> list[str]: ...

    @abstractmethod
    async def list_for_department(
        self, department_id: str, request_id: str
    ) -> list[str]: ...

    @abstractmethod
    async def list_for_user(self, user_id: int, request_id: str) -> list[str]: ...

    @abstractmethod
    async def list_department_grants(
        self, department_ids: Sequence[str], request_id: str
    ) -> dict[str, list[str]]:
        """tool_id → 허용한 부서 id 목록 (department_ids 로 한정)."""

    @abstractmethod
    async def replace_default(
        self, tool_ids: Iterable[str], *, scope: frozenset[str],
        granted_by: int | None, request_id: str,
    ) -> None: ...

    @abstractmethod
    async def replace_for_department(
        self, department_id: str, tool_ids: Iterable[str], *,
        scope: frozenset[str], granted_by: int | None, request_id: str,
    ) -> None: ...

    @abstractmethod
    async def replace_for_user(
        self, user_id: int, tool_ids: Iterable[str], *,
        scope: frozenset[str], granted_by: int | None, request_id: str,
    ) -> None: ...
