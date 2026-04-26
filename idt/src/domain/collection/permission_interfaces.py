from abc import ABC, abstractmethod
from typing import Optional

from src.domain.collection.permission_schemas import (
    CollectionPermission,
    CollectionScope,
)


class CollectionPermissionRepositoryInterface(ABC):

    @abstractmethod
    async def save(
        self, perm: CollectionPermission, request_id: str
    ) -> CollectionPermission: ...

    @abstractmethod
    async def find_by_collection_name(
        self, collection_name: str, request_id: str
    ) -> Optional[CollectionPermission]: ...

    @abstractmethod
    async def find_accessible(
        self,
        user_id: int,
        user_dept_ids: list[str],
        request_id: str,
    ) -> list[CollectionPermission]: ...

    @abstractmethod
    async def update_scope(
        self,
        collection_name: str,
        scope: CollectionScope,
        department_id: Optional[str],
        request_id: str,
    ) -> None: ...

    @abstractmethod
    async def delete_by_collection_name(
        self, collection_name: str, request_id: str
    ) -> None: ...

    @abstractmethod
    async def update_collection_name(
        self, old_name: str, new_name: str, request_id: str
    ) -> None: ...
