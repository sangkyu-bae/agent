"""KnowledgeBaseUseCase — 지식베이스 CRUD (knowledge-base-scoping Design §6.1)."""
from __future__ import annotations

import uuid

from src.domain.auth.entities import User, UserRole
from src.domain.chunking_profile.interfaces import (
    ChunkingProfileRepositoryInterface,
)
from src.domain.chunking_profile.policy import ChunkingProfilePolicy
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.interfaces import (
    CollectionAssignerInterface,
    KnowledgeBaseRepositoryInterface,
)
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class KnowledgeBaseUseCase:
    def __init__(
        self,
        kb_repo: KnowledgeBaseRepositoryInterface,
        policy: KnowledgeBasePolicy,
        assigner: CollectionAssignerInterface,
        dept_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
        profile_repo: ChunkingProfileRepositoryInterface | None = None,
    ) -> None:
        self._kb_repo = kb_repo
        self._policy = policy
        self._assigner = assigner
        self._dept_repo = dept_repo
        self._logger = logger
        self._profile_repo = profile_repo

    async def create(
        self,
        user: User,
        name: str,
        collection_name: str | None,
        scope: CollectionScope,
        department_id: str | None,
        description: str | None,
        request_id: str,
        use_clause_chunking: bool = False,
        chunking_profile_id: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> KnowledgeBase:
        clean_name = self._policy.validate_name(name)
        dept_ids = await self._get_dept_ids(user, request_id)
        self._policy.validate_scope(scope, department_id, dept_ids)
        await self._validate_chunking(
            use_clause_chunking, chunking_profile_id,
            chunk_size, chunk_overlap, request_id,
        )
        if await self._kb_repo.exists_active_name(
            user.id, clean_name, request_id
        ):
            raise ValueError(
                f"Knowledge base '{clean_name}' already exists"
            )
        assigned = await self._assigner.assign(
            user, collection_name, request_id
        )
        kb = KnowledgeBase(
            id=str(uuid.uuid4()),
            name=clean_name,
            description=description,
            owner_id=user.id,
            scope=scope,
            department_id=(
                department_id if scope == CollectionScope.DEPARTMENT else None
            ),
            collection_name=assigned,
            use_clause_chunking=use_clause_chunking,
            chunking_profile_id=chunking_profile_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        saved = await self._kb_repo.save(kb, request_id)
        self._logger.info(
            "KnowledgeBase created",
            request_id=request_id,
            kb_id=kb.id,
            collection_name=assigned,
            scope=scope.value,
        )
        return saved

    async def list(self, user: User, request_id: str) -> list[KnowledgeBase]:
        if user.role == UserRole.ADMIN:
            return await self._kb_repo.find_all_active(request_id)
        dept_ids = await self._get_dept_ids(user, request_id)
        return await self._kb_repo.find_accessible(
            user.id, dept_ids, request_id
        )

    async def get(
        self, kb_id: str, user: User, request_id: str
    ) -> KnowledgeBase:
        kb = await self._find_or_raise(kb_id, request_id)
        dept_ids = await self._get_dept_ids(user, request_id)
        if not self._policy.can_read(user, kb, dept_ids):
            raise PermissionError(
                f"No read access to knowledge base '{kb_id}'"
            )
        return kb

    async def delete(self, kb_id: str, user: User, request_id: str) -> None:
        kb = await self._find_or_raise(kb_id, request_id)
        if not self._policy.can_delete(user, kb):
            raise PermissionError(
                f"No delete access to knowledge base '{kb_id}'"
            )
        await self._kb_repo.soft_delete(kb_id, request_id)
        self._logger.info(
            "KnowledgeBase soft-deleted (vectors remain until cleanup)",
            request_id=request_id,
            kb_id=kb_id,
        )

    async def _validate_chunking(
        self,
        use_clause_chunking: bool,
        chunking_profile_id: str | None,
        chunk_size: int | None,
        chunk_overlap: int | None,
        request_id: str,
    ) -> None:
        """청킹 설정 검증 (clause-aware-chunking Design §7.3)."""
        has_override = (
            chunking_profile_id is not None
            or chunk_size is not None
            or chunk_overlap is not None
        )
        if not use_clause_chunking:
            if has_override:
                raise ValueError(
                    "chunking settings require use_clause_chunking=true"
                )
            return
        ChunkingProfilePolicy.validate_kb_override(chunk_size, chunk_overlap)
        if chunking_profile_id and self._profile_repo is not None:
            profile = await self._profile_repo.find_by_id(
                chunking_profile_id, request_id
            )
            if profile is None or profile.status != "active":
                raise ValueError(
                    f"Chunking profile '{chunking_profile_id}' not found"
                )

    async def _find_or_raise(
        self, kb_id: str, request_id: str
    ) -> KnowledgeBase:
        kb = await self._kb_repo.find_by_id(kb_id, request_id)
        if kb is None:
            raise ValueError(f"Knowledge base '{kb_id}' not found")
        return kb

    async def _get_dept_ids(self, user: User, request_id: str) -> list[str]:
        if user.id is None:
            return []
        depts = await self._dept_repo.find_departments_by_user(
            user.id, request_id
        )
        return [d.department_id for d in depts]
