from src.domain.auth.entities import User, UserRole
from src.domain.collection.permission_schemas import (
    CollectionPermission,
    CollectionScope,
)


class CollectionPermissionPolicy:

    @staticmethod
    def can_read(
        user: User, perm: CollectionPermission, user_dept_ids: list[str]
    ) -> bool:
        if user.role == UserRole.ADMIN:
            return True
        if perm.scope == CollectionScope.PUBLIC:
            return True
        if perm.scope == CollectionScope.PERSONAL:
            return perm.owner_id == user.id
        if perm.scope == CollectionScope.DEPARTMENT:
            return perm.department_id in user_dept_ids
        return False

    @staticmethod
    def can_write(
        user: User, perm: CollectionPermission, user_dept_ids: list[str]
    ) -> bool:
        if user.role == UserRole.ADMIN:
            return True
        if perm.scope == CollectionScope.PERSONAL:
            return perm.owner_id == user.id
        if perm.scope == CollectionScope.DEPARTMENT:
            return perm.department_id in user_dept_ids
        if perm.scope == CollectionScope.PUBLIC:
            return False
        return False

    @staticmethod
    def can_delete_collection(user: User, perm: CollectionPermission) -> bool:
        if user.role == UserRole.ADMIN:
            return True
        return perm.owner_id == user.id

    @staticmethod
    def can_change_scope(user: User, perm: CollectionPermission) -> bool:
        if user.role == UserRole.ADMIN:
            return True
        return perm.owner_id == user.id

    @staticmethod
    def validate_scope_change(
        new_scope: CollectionScope,
        department_id: str | None,
        user_dept_ids: list[str],
    ) -> None:
        if new_scope == CollectionScope.DEPARTMENT:
            if not department_id:
                raise ValueError(
                    "department_id is required for DEPARTMENT scope"
                )
            if department_id not in user_dept_ids:
                raise ValueError(
                    "Cannot assign to a department you don't belong to"
                )
