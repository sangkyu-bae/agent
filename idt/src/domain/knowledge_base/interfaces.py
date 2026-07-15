"""Knowledge Base domain interfaces."""
from abc import ABC, abstractmethod

from src.domain.auth.entities import User
from src.domain.knowledge_base.entities import KnowledgeBase


class KnowledgeBaseRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, kb: KnowledgeBase, request_id: str) -> KnowledgeBase:
        ...

    @abstractmethod
    async def find_by_id(
        self, kb_id: str, request_id: str
    ) -> KnowledgeBase | None:
        """active 상태인 지식베이스만 반환한다."""
        ...

    @abstractmethod
    async def find_all_active(self, request_id: str) -> list[KnowledgeBase]:
        ...

    @abstractmethod
    async def find_accessible(
        self, owner_id: int, dept_ids: list[str], request_id: str
    ) -> list[KnowledgeBase]:
        """본인 소유 + 소속 부서 DEPARTMENT + PUBLIC (active만)."""
        ...

    @abstractmethod
    async def exists_active_name(
        self, owner_id: int, name: str, request_id: str
    ) -> bool:
        ...

    @abstractmethod
    async def soft_delete(self, kb_id: str, request_id: str) -> None:
        ...

    @abstractmethod
    async def update_chunking(
        self,
        kb_id: str,
        *,
        use_clause_chunking: bool,
        chunking_profile_id: str | None,
        chunk_size: int | None,
        chunk_overlap: int | None,
        use_custom_chunking: bool,
        custom_chunking_config: dict | None,
        request_id: str,
    ) -> None:
        """청킹 설정 6개 컬럼만 전체 교체 (kb-custom-chunking D7/D8)."""
        ...


class CollectionAssignerInterface(ABC):
    """KB가 사용할 물리 컬렉션 결정 전략 (Design D6).

    현재: 사용자 선택형(UserSelectedCollectionAssigner).
    추후: 관리자 매핑형으로 구현체 교체 가능.
    """

    @abstractmethod
    async def assign(
        self, user: User, requested_collection: str | None, request_id: str
    ) -> str:
        ...
