"""KbDocumentGuard 단위 테스트 — kb-content-browser Design §4.2 D4.

① KnowledgeBaseUseCase.get() 위임 (404/403)
② document_metadata.kb_id 일치 검증 — 불일치/NULL이면 404 (KB 격리)
③ 통과 시 KbDocumentContext(collection_name, filename, chunk_strategy) 반환
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.content_browse_guard import KbDocumentGuard
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.doc_browse.schemas import DocumentMetadata
from src.domain.knowledge_base.entities import KnowledgeBase


def _user(user_id: int = 1) -> User:
    return User(
        email="t@t.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _kb(kb_id: str = "kb-1") -> KnowledgeBase:
    return KnowledgeBase(
        id=kb_id,
        name="여신 규정집",
        owner_id=1,
        scope=CollectionScope.PERSONAL,
        collection_name="shared-col",
    )


def _meta(kb_id: str | None = "kb-1") -> DocumentMetadata:
    return DocumentMetadata(
        document_id="doc-1",
        collection_name="shared-col",
        filename="a.pdf",
        category="kb",
        user_id="1",
        chunk_count=4,
        chunk_strategy="parent_child",
        kb_id=kb_id,
    )


def _make_guard(kb=None, meta="unset"):
    kb_use_case = AsyncMock()
    if kb is not None:
        kb_use_case.get.return_value = kb
    repo = AsyncMock()
    repo.find_by_document_id.return_value = None if meta == "unset" else meta
    guard = KbDocumentGuard(
        kb_use_case=kb_use_case,
        document_metadata_repo=repo,
        logger=MagicMock(),
    )
    return guard, kb_use_case, repo


class TestKbDocumentGuard:
    @pytest.mark.asyncio
    async def test_returns_context_on_success(self):
        guard, _, repo = _make_guard(kb=_kb(), meta=_meta())
        ctx = await guard.ensure("kb-1", "doc-1", _user(), "req-1")
        assert ctx.kb_id == "kb-1"
        assert ctx.document_id == "doc-1"
        assert ctx.collection_name == "shared-col"
        assert ctx.filename == "a.pdf"
        assert ctx.chunk_strategy == "parent_child"

    @pytest.mark.asyncio
    async def test_kb_not_found_propagates(self):
        guard, kb_use_case, repo = _make_guard()
        kb_use_case.get.side_effect = ValueError("Knowledge base 'kb-x' not found")
        with pytest.raises(ValueError, match="not found"):
            await guard.ensure("kb-x", "doc-1", _user(), "req-2")
        repo.find_by_document_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_permission_denied_propagates(self):
        guard, kb_use_case, repo = _make_guard()
        kb_use_case.get.side_effect = PermissionError("No read access")
        with pytest.raises(PermissionError):
            await guard.ensure("kb-1", "doc-1", _user(2), "req-3")
        repo.find_by_document_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_document_missing_raises_not_found(self):
        guard, _, _ = _make_guard(kb=_kb(), meta=None)
        with pytest.raises(ValueError, match="not found"):
            await guard.ensure("kb-1", "doc-x", _user(), "req-4")

    @pytest.mark.asyncio
    async def test_document_of_other_kb_raises_not_found(self):
        """타 KB 문서 ID 접근 → 404 (KB 격리 계약)."""
        guard, _, _ = _make_guard(kb=_kb(), meta=_meta(kb_id="kb-other"))
        with pytest.raises(ValueError, match="not found"):
            await guard.ensure("kb-1", "doc-1", _user(), "req-5")

    @pytest.mark.asyncio
    async def test_legacy_document_null_kb_id_raises_not_found(self):
        """V047 이전 kb_id NULL 문서는 KB API 대상 아님 (Design §9)."""
        guard, _, _ = _make_guard(kb=_kb(), meta=_meta(kb_id=None))
        with pytest.raises(ValueError, match="not found"):
            await guard.ensure("kb-1", "doc-1", _user(), "req-6")
