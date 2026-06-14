"""UserProfile Repository 추상 인터페이스.

agent-user-context Design §3.5.
"""
from abc import ABC, abstractmethod

from src.domain.user_profile.entity import UserProfile


class UserProfileRepositoryInterface(ABC):
    @abstractmethod
    async def find_by_user_id(
        self, user_id: int, request_id: str
    ) -> UserProfile | None:
        """user_id로 프로필 조회. 없으면 None."""

    @abstractmethod
    async def upsert(
        self, profile: UserProfile, request_id: str
    ) -> UserProfile:
        """프로필 생성 또는 업데이트. PK=user_id 기준."""
