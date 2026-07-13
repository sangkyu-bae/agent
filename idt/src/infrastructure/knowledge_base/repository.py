"""KnowledgeBaseRepository — MySQL 영속화 (knowledge-base-scoping Design §5.3)."""
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.interfaces import (
    KnowledgeBaseRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.persistence.models.knowledge_base import (
    KnowledgeBaseModel,
)


class KnowledgeBaseRepository(KnowledgeBaseRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, kb: KnowledgeBase, request_id: str) -> KnowledgeBase:
        self._logger.info(
            "KnowledgeBase save",
            request_id=request_id,
            kb_id=kb.id,
            collection_name=kb.collection_name,
        )
        model = KnowledgeBaseModel(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            owner_id=kb.owner_id,
            scope=kb.scope.value,
            department_id=kb.department_id,
            collection_name=kb.collection_name,
            status=kb.status,
            use_clause_chunking=1 if kb.use_clause_chunking else 0,
            chunking_profile_id=kb.chunking_profile_id,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def find_by_id(
        self, kb_id: str, request_id: str
    ) -> KnowledgeBase | None:
        stmt = select(KnowledgeBaseModel).where(
            KnowledgeBaseModel.id == kb_id,
            KnowledgeBaseModel.status == "active",
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_all_active(self, request_id: str) -> list[KnowledgeBase]:
        stmt = select(KnowledgeBaseModel).where(
            KnowledgeBaseModel.status == "active"
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_accessible(
        self, owner_id: int, dept_ids: list[str], request_id: str
    ) -> list[KnowledgeBase]:
        conditions = [
            KnowledgeBaseModel.owner_id == owner_id,
            KnowledgeBaseModel.scope == "PUBLIC",
        ]
        if dept_ids:
            conditions.append(
                (KnowledgeBaseModel.scope == "DEPARTMENT")
                & (KnowledgeBaseModel.department_id.in_(dept_ids))
            )
        stmt = select(KnowledgeBaseModel).where(
            KnowledgeBaseModel.status == "active",
            or_(*conditions),
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def exists_active_name(
        self, owner_id: int, name: str, request_id: str
    ) -> bool:
        stmt = select(KnowledgeBaseModel.id).where(
            KnowledgeBaseModel.owner_id == owner_id,
            KnowledgeBaseModel.name == name,
            KnowledgeBaseModel.status == "active",
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def soft_delete(self, kb_id: str, request_id: str) -> None:
        stmt = (
            update(KnowledgeBaseModel)
            .where(KnowledgeBaseModel.id == kb_id)
            .values(status="deleted")
        )
        await self._session.execute(stmt)
        await self._session.flush()

    def _to_domain(self, model: KnowledgeBaseModel) -> KnowledgeBase:
        return KnowledgeBase(
            id=model.id,
            name=model.name,
            description=model.description,
            owner_id=model.owner_id,
            scope=CollectionScope(model.scope),
            department_id=model.department_id,
            collection_name=model.collection_name,
            status=model.status,
            use_clause_chunking=bool(model.use_clause_chunking),
            chunking_profile_id=model.chunking_profile_id,
            chunk_size=model.chunk_size,
            chunk_overlap=model.chunk_overlap,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
