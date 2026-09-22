"""builtin-middleware D1: 미들웨어 저장소 인터페이스."""
from abc import ABC, abstractmethod

from src.domain.middleware.entities import (
    AgentMiddlewareRecord,
    MiddlewareCatalogEntry,
)


class MiddlewareCatalogRepositoryInterface(ABC):
    @abstractmethod
    async def list_all(self, request_id: str) -> list[MiddlewareCatalogEntry]:
        """전체 카탈로그 (관리자 화면·실행 병합 공용)."""

    @abstractmethod
    async def find_by_type(
        self, middleware_type: str, request_id: str
    ) -> MiddlewareCatalogEntry | None:
        """단건 조회 — 미존재 시 None."""

    @abstractmethod
    async def update_flags(
        self,
        middleware_type: str,
        *,
        is_builtin: bool | None,
        is_enforced: bool | None,
        default_config: dict | None,
        request_id: str,
    ) -> MiddlewareCatalogEntry | None:
        """부분 갱신 (None = 미변경) — 미존재 시 None."""

    @abstractmethod
    async def list_builtin(self, request_id: str) -> list[MiddlewareCatalogEntry]:
        """is_builtin AND is_active — 생성 시 스냅샷 주입 대상."""


class AgentMiddlewareRepositoryInterface(ABC):
    @abstractmethod
    async def list_by_agent(
        self, agent_id: str, request_id: str
    ) -> list[AgentMiddlewareRecord]:
        """에이전트 적용 스냅샷 (sort_order ASC)."""

    @abstractmethod
    async def upsert_config(
        self, *, agent_id: str, middleware_type: str, config: dict,
        request_id: str,
    ) -> None:
        """에이전트별 config 저장 — 행이 없으면 만든다(행 존재 = 적용).

        approval-gate Check G3: 이전에는 config 를 쓸 입구가 없었다.
        commit 은 호출측 트랜잭션이 소유한다 (DB-001).
        """
