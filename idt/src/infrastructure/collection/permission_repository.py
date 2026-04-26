from typing import Optional

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.collection.permission_interfaces import (
    CollectionPermissionRepositoryInterface,
)
from src.domain.collection.permission_schemas import (
    CollectionPermission,
    CollectionScope,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.collection.permission_models import (
    CollectionPermissionModel,
)


class CollectionPermissionRepository(CollectionPermissionRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(
        self, perm: CollectionPermission, request_id: str
    ) -> CollectionPermission:
        self._logger.info(
            "CollectionPermission save",
            request_id=request_id,
            collection=perm.collection_name,
        )
        model = CollectionPermissionModel(
            collection_name=perm.collection_name,
            owner_id=perm.owner_id,
            scope=perm.scope.value,
            department_id=perm.department_id,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return CollectionPermission(
            id=model.id,
            collection_name=model.collection_name,
            owner_id=model.owner_id,
            scope=CollectionScope(model.scope),
            department_id=model.department_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def find_by_collection_name(
        self, collection_name: str, request_id: str
    ) -> Optional[CollectionPermission]:
        stmt = select(CollectionPermissionModel).where(
            CollectionPermissionModel.collection_name == collection_name
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_accessible(
        self,
        user_id: int,
        user_dept_ids: list[str],
        request_id: str,
    ) -> list[CollectionPermission]:
        conditions = [
            CollectionPermissionModel.scope == "PUBLIC",
            CollectionPermissionModel.owner_id == user_id,
        ]
        if user_dept_ids:
            conditions.append(
                (CollectionPermissionModel.scope == "DEPARTMENT")
                & (CollectionPermissionModel.department_id.in_(user_dept_ids))
            )
        stmt = select(CollectionPermissionModel).where(or_(*conditions))
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def update_scope(
        self,
        collection_name: str,
        scope: CollectionScope,
        department_id: Optional[str],
        request_id: str,
    ) -> None:
        stmt = (
            update(CollectionPermissionModel)
            .where(
                CollectionPermissionModel.collection_name == collection_name
            )
            .values(scope=scope.value, department_id=department_id)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def delete_by_collection_name(
        self, collection_name: str, request_id: str
    ) -> None:
        stmt = delete(CollectionPermissionModel).where(
            CollectionPermissionModel.collection_name == collection_name
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def update_collection_name(
        self, old_name: str, new_name: str, request_id: str
    ) -> None:
        stmt = (
            update(CollectionPermissionModel)
            .where(CollectionPermissionModel.collection_name == old_name)
            .values(collection_name=new_name)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    def _to_domain(
        self, model: CollectionPermissionModel
    ) -> CollectionPermission:
        return CollectionPermission(
            id=model.id,
            collection_name=model.collection_name,
            owner_id=model.owner_id,
            scope=CollectionScope(model.scope),
            department_id=model.department_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
