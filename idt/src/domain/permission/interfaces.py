"""Permission Repository 추상 인터페이스.

agent-user-context Design §3.5:
- domain 레이어는 인터페이스만 정의, 구현은 infrastructure에서.
- 모든 메서드는 request_id를 받아 구조화 로깅(LOG-001)을 지원한다.
"""
from abc import ABC, abstractmethod


class PermissionRepositoryInterface(ABC):
    @abstractmethod
    async def find_codes_for_role(
        self, role: str, request_id: str
    ) -> list[str]:
        """role(user/admin)에 매핑된 권한 코드 리스트."""

    @abstractmethod
    async def find_codes_for_user(
        self, user_id: int, request_id: str
    ) -> list[str]:
        """user에게 추가 부여된 권한 코드 리스트 (role 기본 권한 제외)."""

    @abstractmethod
    async def grant_to_user(
        self, user_id: int, code: str, granted_by: int, request_id: str
    ) -> None:
        """user에게 권한 추가 부여. 이미 있으면 무시 (idempotent)."""

    @abstractmethod
    async def revoke_from_user(
        self, user_id: int, code: str, request_id: str
    ) -> None:
        """user에게 부여된 권한 회수. 없어도 에러 X (idempotent)."""
