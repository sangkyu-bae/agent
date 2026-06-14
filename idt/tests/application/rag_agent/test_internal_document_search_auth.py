"""InternalDocumentSearchTool — agent-user-context 권한 검증 단위 테스트.

Design §7.2 + 테스트 전략 §10.2 검증:
- USE_RAG_SEARCH 없으면 즉시 거부
- READ_DEPARTMENT_DOCS 없으면 visibility=public 강제
- AuthContext 명시 → ContextVar fallback → public_anonymous 우선순위
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.auth_context import (
    reset_current_auth_context,
    set_current_auth_context,
)
from src.application.rag_agent.tools import InternalDocumentSearchTool
from src.domain.agent_run.auth_context import AuthContext
from src.domain.hybrid_search.schemas import HybridSearchResponse, HybridSearchResult


def _empty_response() -> HybridSearchResponse:
    return HybridSearchResponse(query="q", results=[], total_found=0, request_id="r")


def _make_tool(auth_ctx=None, metadata_filter=None) -> InternalDocumentSearchTool:
    mock_uc = MagicMock()
    mock_uc.execute = AsyncMock(return_value=_empty_response())
    return InternalDocumentSearchTool(
        hybrid_search_use_case=mock_uc,
        request_id="r",
        metadata_filter=metadata_filter or {},
        auth_ctx=auth_ctx,
    )


def _ctx(perms: set[str], depts: tuple[str, ...] = ("dept-001",)) -> AuthContext:
    return AuthContext(
        user_id=1,
        display_name="배상규",
        role="user",
        primary_department_id=depts[0] if depts else None,
        primary_department_name="DX팀" if depts else None,
        department_ids=depts,
        department_names=("DX팀",) if depts else (),
        permissions=frozenset(perms),
    )


class TestPermissionDenial:
    @pytest.mark.asyncio
    async def test_rejects_without_use_rag_search(self):
        tool = _make_tool(auth_ctx=_ctx(perms=set()))
        result = await tool._arun("query")
        assert "권한이 없습니다" in result
        tool.hybrid_search_use_case.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_allows_with_use_rag_search(self):
        tool = _make_tool(auth_ctx=_ctx(perms={"USE_RAG_SEARCH"}))
        result = await tool._arun("query")
        # 검색은 실행되지만 결과 없음 메시지
        tool.hybrid_search_use_case.execute.assert_awaited()
        assert "권한이 없습니다" not in result

    @pytest.mark.asyncio
    async def test_anonymous_rejected_by_default(self):
        """auth_ctx 미주입 + ContextVar 미설정 → public_anonymous → 거부."""
        tool = _make_tool(auth_ctx=None)
        result = await tool._arun("query")
        assert "권한이 없습니다" in result


class TestMetadataFilterEnforcement:
    @pytest.mark.asyncio
    async def test_no_dept_permission_forces_public_visibility(self):
        tool = _make_tool(auth_ctx=_ctx(perms={"USE_RAG_SEARCH"}))
        await tool._arun("query")
        # 실제 HybridSearchRequest.metadata_filter에 visibility=public 강제 주입
        sent = tool.hybrid_search_use_case.execute.call_args[0][0]
        assert sent.metadata_filter["visibility"] == "public"

    @pytest.mark.asyncio
    async def test_dept_permission_injects_viewer_departments(self):
        tool = _make_tool(auth_ctx=_ctx(
            perms={"USE_RAG_SEARCH", "READ_DEPARTMENT_DOCS"},
            depts=("dept-001", "dept-002"),
        ))
        await tool._arun("query")
        sent = tool.hybrid_search_use_case.execute.call_args[0][0]
        assert "visibility" not in sent.metadata_filter
        assert sent.metadata_filter["viewer_department_ids"] == "dept-001,dept-002"

    @pytest.mark.asyncio
    async def test_preserves_existing_metadata_filter(self):
        """기존 metadata_filter는 유지하고 visibility만 추가."""
        tool = _make_tool(
            auth_ctx=_ctx(perms={"USE_RAG_SEARCH"}),
            metadata_filter={"doc_type": "policy"},
        )
        await tool._arun("query")
        sent = tool.hybrid_search_use_case.execute.call_args[0][0]
        assert sent.metadata_filter["doc_type"] == "policy"
        assert sent.metadata_filter["visibility"] == "public"


class TestAuthContextResolutionPriority:
    """Defense in Depth — 명시 → ContextVar → anonymous 순."""

    @pytest.mark.asyncio
    async def test_explicit_auth_ctx_wins_over_context_var(self):
        # 명시: 권한 없음 — 거부 예상
        explicit_ctx = _ctx(perms=set())
        # ContextVar: 권한 있음 — 이게 적용되면 거부 안 됨
        cv_ctx = _ctx(perms={"USE_RAG_SEARCH"})
        token = set_current_auth_context(cv_ctx)
        try:
            tool = _make_tool(auth_ctx=explicit_ctx)
            result = await tool._arun("query")
            assert "권한이 없습니다" in result  # 명시가 우선
        finally:
            reset_current_auth_context(token)

    @pytest.mark.asyncio
    async def test_falls_back_to_context_var_when_no_explicit(self):
        cv_ctx = _ctx(perms={"USE_RAG_SEARCH"})
        token = set_current_auth_context(cv_ctx)
        try:
            tool = _make_tool(auth_ctx=None)
            result = await tool._arun("query")
            assert "권한이 없습니다" not in result
        finally:
            reset_current_auth_context(token)
