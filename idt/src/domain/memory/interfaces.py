"""MemoryRepositoryInterface — 메모리 저장소 추상화 (agent-memory Design §3-2).

구현: src.infrastructure.memory.repository.MemoryRepository.
Repository는 flush까지만 수행하고 commit/rollback은 세션 컨텍스트가 담당한다.
"""
from abc import ABC, abstractmethod

from src.domain.memory.entity import Memory, MemoryStatus


class MemoryRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, memory: Memory, request_id: str) -> Memory:
        """신규 메모리 저장 후 id/타임스탬프가 채워진 엔티티 반환."""

    @abstractmethod
    async def find_by_id(self, memory_id: int, request_id: str) -> Memory | None:
        """PK 조회 — 없으면 None."""

    @abstractmethod
    async def find_active_by_user(self, user_id: str, request_id: str) -> list[Memory]:
        """해당 사용자의 status=active 메모리 전체."""

    @abstractmethod
    async def count_active_by_user(self, user_id: str, request_id: str) -> int:
        """해당 사용자의 status=active 개수 — 상한 검증용."""

    @abstractmethod
    async def find_by_user_and_status(
        self, user_id: str, status: "MemoryStatus", request_id: str
    ) -> list[Memory]:
        """해당 사용자의 특정 status 메모리 전체 (Phase 2 — pending 목록·중복 비교)."""

    @abstractmethod
    async def count_by_user_and_status(
        self, user_id: str, status: "MemoryStatus", request_id: str
    ) -> int:
        """해당 사용자의 특정 status 개수 (Phase 2 — pending 상한 검증)."""

    @abstractmethod
    async def update(self, memory: Memory, request_id: str) -> Memory:
        """mem_type/content 갱신 후 최신 엔티티 반환."""

    @abstractmethod
    async def delete(self, memory_id: int, request_id: str) -> bool:
        """물리 삭제 — 삭제됐으면 True."""
