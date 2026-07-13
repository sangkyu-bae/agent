"""ListKbDocumentsUseCase 단위 테스트 — kb-management-ui Design §4.4.

권한/존재 검증은 KnowledgeBaseUseCase.get()에 위임(D3)하고,
본 유스케이스는 kb_id 필터 문서 목록 조회만 담당한다.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.list_documents_use_case import (
    ListKbDocumentsUseCase,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.doc_browse.schemas import KbDocumentSummary
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.mysql.schemas import MySQLPageResult


def _user(user_id: int = 1, role: UserRole = UserRole.USER) -> User:
    return User(
        email="test@test.com",
        password_hash="hash",
        role=role,
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


def _summary(i: int) -> KbDocumentSummary:
    return KbDocumentSummary(
        document_id=f"doc-{i}",
        filename=f"{i}.pdf",
        chunk_count=i + 1,
        chunk_strategy="clause_aware",
        created_at=datetime(2026, 7, 10, 12, 0, i),
    )


def _page(items, total=None) -> MySQLPageResult:
    return MySQLPageResult(
        items=items,
        total=total if total is not None else len(items),
        limit=20,
        offset=0,
    )


def _make_use_case(kb=None, page=None):
    kb_use_case = AsyncMock()
    if kb is not None:
        kb_use_case.get.return_value = kb
    repo = AsyncMock()
    repo.find_by_kb_id.return_value = page if page is not None else _page([])
    logger = MagicMock()
    use_case = ListKbDocumentsUseCase(
        kb_use_case=kb_use_case,
        document_metadata_repo=repo,
        logger=logger,
    )
    return use_case, kb_use_case, repo


class TestListKbDocuments:
    @pytest.mark.asyncio
    async def test_returns_documents_with_kb_name(self):
        page = _page([_summary(0), _summary(1)], total=5)
        use_case, _, _ = _make_use_case(kb=_kb(), page=page)

        result = await use_case.execute("kb-1", _user(), "req-1")

        assert result.kb_id == "kb-1"
        assert result.kb_name == "여신 규정집"
        assert result.total == 5
        assert len(result.documents) == 2
        assert result.documents[0].document_id == "doc-0"
        assert result.documents[0].chunk_strategy == "clause_aware"

    @pytest.mark.asyncio
    async def test_filters_by_kb_id(self):
        """타 KB 문서 미포함 보장 — repo에 kb_id 필터 인자로 조회."""
        use_case, _, repo = _make_use_case(kb=_kb("kb-77"))

        await use_case.execute("kb-77", _user(), "req-2")

        call = repo.find_by_kb_id.await_args
        assert call.args[0] == "kb-77"

    @pytest.mark.asyncio
    async def test_permission_denied_propagates(self):
        """D3: get()의 PermissionError 그대로 전파 (라우터 403)."""
        use_case, kb_use_case, repo = _make_use_case()
        kb_use_case.get.side_effect = PermissionError(
            "No read access to knowledge base 'kb-1'"
        )

        with pytest.raises(PermissionError, match="No read access"):
            await use_case.execute("kb-1", _user(user_id=2), "req-3")
        repo.find_by_kb_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_kb_propagates_not_found(self):
        """D3: get()의 ValueError(not found) 그대로 전파 (라우터 404)."""
        use_case, kb_use_case, repo = _make_use_case()
        kb_use_case.get.side_effect = ValueError(
            "Knowledge base 'kb-gone' not found"
        )

        with pytest.raises(ValueError, match="not found"):
            await use_case.execute("kb-gone", _user(), "req-4")
        repo.find_by_kb_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pagination_params_forwarded(self):
        use_case, _, repo = _make_use_case(kb=_kb())

        await use_case.execute("kb-1", _user(), "req-5", offset=40, limit=10)

        pagination = repo.find_by_kb_id.await_args.kwargs.get(
            "pagination"
        ) or repo.find_by_kb_id.await_args.args[2]
        assert pagination.offset == 40
        assert pagination.limit == 10

    @pytest.mark.asyncio
    async def test_empty_list(self):
        use_case, _, _ = _make_use_case(kb=_kb())

        result = await use_case.execute("kb-1", _user(), "req-6")

        assert result.documents == []
        assert result.total == 0
