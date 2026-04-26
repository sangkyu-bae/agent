from src.domain.auth.entities import User, UserRole
from src.domain.collection.permission_interfaces import (
    CollectionPermissionRepositoryInterface,
)
from src.domain.collection.permission_policy import CollectionPermissionPolicy
from src.domain.collection.permission_schemas import (
    CollectionPermission,
    CollectionScope,
)
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CollectionPermissionService:
    def __init__(
        self,
        perm_repo: CollectionPermissionRepositoryInterface,
        dept_repo: DepartmentRepositoryInterface,
        policy: CollectionPermissionPolicy,
        logger: LoggerInterface,
    ) -> None:
        self._perm_repo = perm_repo
        self._dept_repo = dept_repo
        self._policy = policy
        self._logger = logger

    async def get_user_dept_ids(
        self, user: User, request_id: str
    ) -> list[str]:
        if user.id is None:
            return []
        depts = await self._dept_repo.find_departments_by_user(
            user.id, request_id
        )
        return [d.department_id for d in depts]

    async def create_permission(
        self,
        collection_name: str,
        user: User,
        scope: CollectionScope,
        department_id: str | None,
        request_id: str,
    ) -> CollectionPermission:
        if scope == CollectionScope.DEPARTMENT:
            user_dept_ids = await self.get_user_dept_ids(user, request_id)
            self._policy.validate_scope_change(
                scope, department_id, user_dept_ids
            )
        perm = CollectionPermission(
            collection_name=collection_name,
            owner_id=user.id,
            scope=scope,
            department_id=department_id,
        )
        return await self._perm_repo.save(perm, request_id)

    async def check_read_access(
        self, collection_name: str, user: User, request_id: str
    ) -> None:
        perm = await self._perm_repo.find_by_collection_name(
            collection_name, request_id
        )
        if perm is None:
            return
        user_dept_ids = await self.get_user_dept_ids(user, request_id)
        if not self._policy.can_read(user, perm, user_dept_ids):
            raise PermissionError(
                f"No read access to collection '{collection_name}'"
            )

    async def check_write_access(
        self, collection_name: str, user: User, request_id: str
    ) -> None:
        perm = await self._perm_repo.find_by_collection_name(
            collection_name, request_id
        )
        if perm is None:
            return
        user_dept_ids = await self.get_user_dept_ids(user, request_id)
        if not self._policy.can_write(user, perm, user_dept_ids):
            raise PermissionError(
                f"No write access to collection '{collection_name}'"
            )

    async def check_delete_access(
        self, collection_name: str, user: User, request_id: str
    ) -> None:
        perm = await self._perm_repo.find_by_collection_name(
            collection_name, request_id
        )
        if perm is None:
            return
        if not self._policy.can_delete_collection(user, perm):
            raise PermissionError(
                f"No delete access to collection '{collection_name}'"
            )

    async def get_accessible_collection_names(
        self, user: User, request_id: str
    ) -> set[str]:
        if user.role == UserRole.ADMIN:
            return set()
        user_dept_ids = await self.get_user_dept_ids(user, request_id)
        perms = await self._perm_repo.find_accessible(
            user.id, user_dept_ids, request_id
        )
        return {p.collection_name for p in perms}

    async def change_scope(
        self,
        collection_name: str,
        user: User,
        new_scope: CollectionScope,
        department_id: str | None,
        request_id: str,
    ) -> None:
        perm = await self._perm_repo.find_by_collection_name(
            collection_name, request_id
        )
        if perm is None:
            raise ValueError(
                f"Permission not found for collection '{collection_name}'"
            )
        if not self._policy.can_change_scope(user, perm):
            raise PermissionError("No permission to change scope")
        user_dept_ids = await self.get_user_dept_ids(user, request_id)
        self._policy.validate_scope_change(
            new_scope, department_id, user_dept_ids
        )
        await self._perm_repo.update_scope(
            collection_name, new_scope, department_id, request_id
        )

    async def find_permission(
        self, collection_name: str, request_id: str
    ) -> CollectionPermission | None:
        return await self._perm_repo.find_by_collection_name(
            collection_name, request_id
        )

    async def on_collection_deleted(
        self, collection_name: str, request_id: str
    ) -> None:
        await self._perm_repo.delete_by_collection_name(
            collection_name, request_id
        )

    async def on_collection_renamed(
        self, old_name: str, new_name: str, request_id: str
    ) -> None:
        await self._perm_repo.update_collection_name(
            old_name, new_name, request_id
        )
