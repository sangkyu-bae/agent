from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.collection.activity_log_service import ActivityLogService
from src.domain.collection.interfaces import CollectionRepositoryInterface
from src.domain.collection.policy import CollectionPolicy
from src.domain.collection.schemas import (
    ActionType,
    CollectionDetail,
    CollectionInfo,
    CreateCollectionRequest,
)
from src.domain.embedding_model.interfaces import EmbeddingModelRepositoryInterface

if TYPE_CHECKING:
    from src.domain.auth.entities import User
    from src.application.collection.permission_service import CollectionPermissionService
    from src.domain.collection.permission_schemas import CollectionScope


class CollectionManagementUseCase:
    def __init__(
        self,
        repository: CollectionRepositoryInterface,
        policy: CollectionPolicy,
        activity_log: ActivityLogService,
        default_collection: str,
        permission_service: CollectionPermissionService | None = None,
        embedding_model_repo: EmbeddingModelRepositoryInterface | None = None,
    ) -> None:
        self._repo = repository
        self._policy = policy
        self._activity_log = activity_log
        self._default_collection = default_collection
        self._permission_service = permission_service
        self._embedding_model_repo = embedding_model_repo

    async def list_collections(
        self,
        request_id: str,
        user_id: str | None = None,
        user: User | None = None,
    ) -> list[CollectionInfo]:
        result = await self._repo.list_collections()
        if user and self._permission_service:
            accessible = await self._permission_service.get_accessible_collection_names(
                user, request_id
            )
            if accessible:
                result = [c for c in result if c.name in accessible]
        await self._activity_log.log(
            collection_name="*",
            action=ActionType.LIST,
            request_id=request_id,
            user_id=user_id,
            detail={"count": len(result)},
        )
        return result

    async def get_collection(
        self,
        name: str,
        request_id: str,
        user_id: str | None = None,
        user: User | None = None,
    ) -> CollectionDetail:
        if user and self._permission_service:
            await self._permission_service.check_read_access(
                name, user, request_id
            )
        result = await self._repo.get_collection(name)
        if result is None:
            raise ValueError(f"Collection '{name}' not found")
        await self._activity_log.log(
            collection_name=name,
            action=ActionType.DETAIL,
            request_id=request_id,
            user_id=user_id,
        )
        return result

    async def create_collection(
        self,
        req: CreateCollectionRequest,
        request_id: str,
        user_id: str | None = None,
        user: User | None = None,
        scope: CollectionScope | None = None,
        department_id: str | None = None,
    ) -> None:
        self._policy.validate_name(req.name)
        if await self._repo.collection_exists(req.name):
            raise ValueError(f"Collection '{req.name}' already exists")

        vector_size = req.vector_size
        if req.embedding_model and self._embedding_model_repo:
            model = await self._embedding_model_repo.find_by_model_name(
                req.embedding_model, request_id
            )
            if model is None:
                raise ValueError(
                    f"Unknown embedding model: '{req.embedding_model}'"
                )
            vector_size = model.vector_dimension

        actual_req = CreateCollectionRequest(
            name=req.name,
            vector_size=vector_size,
            distance=req.distance,
            embedding_model=req.embedding_model,
        )
        await self._repo.create_collection(actual_req)

        if user and self._permission_service and scope:
            await self._permission_service.create_permission(
                req.name, user, scope, department_id, request_id
            )

        await self._activity_log.log(
            collection_name=req.name,
            action=ActionType.CREATE,
            request_id=request_id,
            user_id=user_id,
            detail={
                "vector_size": vector_size,
                "distance": req.distance.value,
                "embedding_model": req.embedding_model,
            },
        )

    async def delete_collection(
        self,
        name: str,
        request_id: str,
        user_id: str | None = None,
        user: User | None = None,
    ) -> None:
        self._policy.can_delete(name, self._default_collection)
        if user and self._permission_service:
            await self._permission_service.check_delete_access(
                name, user, request_id
            )
        if not await self._repo.collection_exists(name):
            raise ValueError(f"Collection '{name}' not found")
        await self._repo.delete_collection(name)
        if self._permission_service:
            await self._permission_service.on_collection_deleted(
                name, request_id
            )
        await self._activity_log.log(
            collection_name=name,
            action=ActionType.DELETE,
            request_id=request_id,
            user_id=user_id,
        )

    async def get_permissions_map(
        self,
        collection_names: list[str],
        request_id: str,
    ) -> dict[str, tuple[str, int]]:
        if not self._permission_service:
            return {}
        result: dict[str, tuple[str, int]] = {}
        for name in collection_names:
            perm = await self._permission_service.find_permission(
                name, request_id
            )
            if perm:
                result[name] = (perm.scope.value, perm.owner_id)
        return result

    async def change_scope(
        self,
        collection_name: str,
        user: User,
        new_scope: CollectionScope,
        department_id: str | None,
        request_id: str,
    ) -> None:
        if not self._permission_service:
            raise RuntimeError("Permission service not configured")
        await self._permission_service.change_scope(
            collection_name, user, new_scope, department_id, request_id
        )
        await self._activity_log.log(
            collection_name=collection_name,
            action=ActionType.CHANGE_SCOPE,
            request_id=request_id,
            detail={"new_scope": new_scope.value, "department_id": department_id},
        )

    async def rename_collection(
        self,
        old_name: str,
        new_name: str,
        request_id: str,
        user_id: str | None = None,
        user: User | None = None,
    ) -> None:
        self._policy.validate_name(new_name)
        if user and self._permission_service:
            await self._permission_service.check_delete_access(
                old_name, user, request_id
            )
        if not await self._repo.collection_exists(old_name):
            raise ValueError(f"Collection '{old_name}' not found")
        await self._repo.update_collection_alias(old_name, new_name)
        if self._permission_service:
            await self._permission_service.on_collection_renamed(
                old_name, new_name, request_id
            )
        await self._activity_log.log(
            collection_name=old_name,
            action=ActionType.RENAME,
            request_id=request_id,
            user_id=user_id,
            detail={"old_name": old_name, "new_name": new_name},
        )
