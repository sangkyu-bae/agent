"""KnowledgeBasePolicy — 지식베이스 이름 검증 및 스코프 권한 판정.

collection_permissions와 독립된 KB 전용 판정 (knowledge-base-scoping Design D7).
PUBLIC 쓰기는 소유자만 허용 (D8 — CollectionPermissionPolicy.can_write와 동형).
"""
import re

from src.domain.auth.entities import User, UserRole
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class KnowledgeBasePolicy:
    MAX_NAME_LENGTH = 100

    @staticmethod
    def validate_name(name: str) -> str:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Knowledge base name must not be empty")
        if len(cleaned) > KnowledgeBasePolicy.MAX_NAME_LENGTH:
            raise ValueError(
                f"Knowledge base name max {KnowledgeBasePolicy.MAX_NAME_LENGTH} chars"
            )
        if _CONTROL_CHARS.search(cleaned):
            raise ValueError("Knowledge base name must not contain control characters")
        return cleaned

    @staticmethod
    def can_read(
        user: User, kb: KnowledgeBase, user_dept_ids: list[str]
    ) -> bool:
        return KnowledgeBasePolicy.can_read_ref(
            user.id, user.role, kb, user_dept_ids
        )

    @staticmethod
    def can_read_ref(
        user_id: int | None,
        role: UserRole,
        kb: KnowledgeBase,
        user_dept_ids: list[str],
    ) -> bool:
        """User 엔티티 없이 식별자만으로 읽기권한 판정 (kb-rag-filter D3).

        에이전트 빌더 UseCase처럼 user_id/role만 가진 호출자용 —
        can_read와 단일 규칙을 공유한다.
        """
        if role == UserRole.ADMIN:
            return True
        if kb.scope == CollectionScope.PUBLIC:
            return True
        if kb.scope == CollectionScope.PERSONAL:
            return user_id is not None and kb.owner_id == user_id
        if kb.scope == CollectionScope.DEPARTMENT:
            return kb.department_id in user_dept_ids
        return False

    @staticmethod
    def can_write(
        user: User, kb: KnowledgeBase, user_dept_ids: list[str]
    ) -> bool:
        if user.role == UserRole.ADMIN:
            return True
        if kb.scope == CollectionScope.PERSONAL:
            return kb.owner_id == user.id
        if kb.scope == CollectionScope.DEPARTMENT:
            return kb.department_id in user_dept_ids
        if kb.scope == CollectionScope.PUBLIC:
            return kb.owner_id == user.id
        return False

    @staticmethod
    def can_delete(user: User, kb: KnowledgeBase) -> bool:
        if user.role == UserRole.ADMIN:
            return True
        return kb.owner_id == user.id

    @staticmethod
    def can_manage_settings(user: User, kb: KnowledgeBase) -> bool:
        """청킹 등 KB 구조 설정 변경 — 소유자/ADMIN만 (kb-custom-chunking D9)."""
        return KnowledgeBasePolicy.can_delete(user, kb)

    @staticmethod
    def validate_scope(
        scope: CollectionScope,
        department_id: str | None,
        user_dept_ids: list[str],
    ) -> None:
        if scope != CollectionScope.DEPARTMENT:
            return
        if not department_id:
            raise ValueError("department_id is required for DEPARTMENT scope")
        if department_id not in user_dept_ids:
            raise ValueError("Cannot assign to a department you don't belong to")
