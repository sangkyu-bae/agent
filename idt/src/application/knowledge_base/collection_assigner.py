"""UserSelectedCollectionAssigner — 사용자 선택형 물리 컬렉션 배정 (Design D6).

물리 컬렉션 접근 검사는 KB 생성 시 이 1회만 수행한다 (Plan §4-3).
"""
from src.application.collection.permission_service import (
    CollectionPermissionService,
)
from src.domain.auth.entities import User
from src.domain.collection.interfaces import CollectionRepositoryInterface
from src.domain.knowledge_base.interfaces import CollectionAssignerInterface


class UserSelectedCollectionAssigner(CollectionAssignerInterface):
    def __init__(
        self,
        collection_repo: CollectionRepositoryInterface,
        perm_service: CollectionPermissionService,
    ) -> None:
        self._collection_repo = collection_repo
        self._perm_service = perm_service

    async def assign(
        self, user: User, requested_collection: str | None, request_id: str
    ) -> str:
        if not requested_collection:
            raise ValueError("collection_name is required")
        if not await self._collection_repo.collection_exists(
            requested_collection
        ):
            raise ValueError(
                f"Collection '{requested_collection}' not found"
            )
        await self._perm_service.check_read_access(
            requested_collection, user, request_id
        )
        return requested_collection
