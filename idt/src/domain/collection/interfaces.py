from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.collection.schemas import (
    ActionType,
    ActivityLogEntry,
    CollectionDetail,
    CollectionInfo,
    CreateCollectionRequest,
)


class CollectionRepositoryInterface(ABC):
    @abstractmethod
    async def list_collections(self) -> list[CollectionInfo]: ...

    @abstractmethod
    async def get_collection(self, name: str) -> CollectionDetail | None: ...

    @abstractmethod
    async def create_collection(self, req: CreateCollectionRequest) -> None: ...

    @abstractmethod
    async def delete_collection(self, name: str) -> None: ...

    @abstractmethod
    async def collection_exists(self, name: str) -> bool: ...

    @abstractmethod
    async def update_collection_alias(
        self, old_name: str, new_alias: str
    ) -> None: ...


class ActivityLogRepositoryInterface(ABC):
    @abstractmethod
    async def save(
        self,
        collection_name: str,
        action: ActionType,
        user_id: str | None,
        detail: dict | None,
        request_id: str,
    ) -> None: ...

    @abstractmethod
    async def find_by_collection(
        self,
        collection_name: str,
        request_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLogEntry]: ...

    @abstractmethod
    async def find_all(
        self,
        request_id: str,
        collection_name: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLogEntry]: ...

    @abstractmethod
    async def count(
        self,
        request_id: str,
        collection_name: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> int: ...
