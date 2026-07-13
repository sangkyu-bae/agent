"""ChunkingProfile 도메인 인터페이스 (clause-aware-chunking Design §5.3)."""
from abc import ABC, abstractmethod

from src.domain.chunking_profile.entities import ChunkingProfile


class ChunkingProfileRepositoryInterface(ABC):
    @abstractmethod
    async def save(
        self, profile: ChunkingProfile, request_id: str
    ) -> ChunkingProfile:
        ...

    @abstractmethod
    async def find_by_id(
        self, profile_id: str, request_id: str
    ) -> ChunkingProfile | None:
        """status 무관 조회 (soft-deleted 폴백 판정용)."""
        ...

    @abstractmethod
    async def find_all_active(self, request_id: str) -> list[ChunkingProfile]:
        ...

    @abstractmethod
    async def find_default(self, request_id: str) -> ChunkingProfile | None:
        """is_default=True AND active 인 프로파일."""
        ...

    @abstractmethod
    async def exists_active_name(
        self, name: str, exclude_id: str | None, request_id: str
    ) -> bool:
        ...

    @abstractmethod
    async def update(
        self, profile: ChunkingProfile, request_id: str
    ) -> ChunkingProfile:
        ...

    @abstractmethod
    async def clear_default(self, request_id: str) -> None:
        """모든 프로파일의 is_default=False로 설정."""
        ...

    @abstractmethod
    async def soft_delete(self, profile_id: str, request_id: str) -> None:
        ...
