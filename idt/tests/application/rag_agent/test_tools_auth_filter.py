"""권한 필터 키 3분류 테스트 (rag-auth-filter-fix D1/D2).

- ignored: viewer_department_ids — 검색 인프라에 미적용
- lenient: visibility — lenient_filter로 이동 ("값 일치 OR 필드 부재")
- hard: 나머지 키 — 기존 metadata_filter 유지
- 0건 + 주입 키 존재 시 warning 로그
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.application.rag_agent.tools import InternalDocumentSearchTool
from src.domain.agent_run.auth_context import AuthContext
from src.domain.permission.value_objects import PermissionCode


class _FakeLogger:
    def __init__(self):
        self.warnings = []

    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, msg, **k):
        self.warnings.append((msg, k))
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


class _FakeHybrid:
    def __init__(self, results=None):
        self.calls = []
        self._results = results or []

    async def execute(self, request, request_id):
        self.calls.append(request)
        return SimpleNamespace(results=self._results)


def _auth_ctx(codes: set[str]) -> AuthContext:
    return AuthContext(
        user_id=7,
        display_name="배상규",
        role="admin",
        primary_department_id="dept-1",
        primary_department_name="테스트1",
        department_ids=("dept-1",),
        department_names=("테스트1",),
        permissions=frozenset(codes),
    )


_DEPT_PERMS = {
    PermissionCode.USE_RAG_SEARCH.value,
    PermissionCode.READ_DEPARTMENT_DOCS.value,
}
_PUBLIC_PERMS = {PermissionCode.USE_RAG_SEARCH.value}


def _tool(perms, metadata_filter=None, results=None, **kwargs):
    hybrid = _FakeHybrid(results=results)
    logger = _FakeLogger()
    tool = InternalDocumentSearchTool(
        hybrid_search_use_case=hybrid,
        request_id="req-1",
        top_k=5,
        metadata_filter=metadata_filter or {},
        auth_ctx=_auth_ctx(perms),
        logger=logger,
        collection_name="test10",
        **kwargs,
    )
    return tool, hybrid, logger


def _empty_warnings(logger: _FakeLogger) -> list[dict]:
    return [
        k for msg, k in logger.warnings
        if msg == "Internal search empty with auth-injected filter"
    ]


# ── D1: 키 3분류 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_department_ids_not_applied_to_search():
    """부서 권한 보유 → 주입된 viewer_department_ids는 검색에 미적용 (ignored)."""
    tool, hybrid, _ = _tool(_DEPT_PERMS)

    await tool._arun("나의 휴가")

    req = hybrid.calls[0]
    assert "viewer_department_ids" not in req.metadata_filter
    assert "viewer_department_ids" not in req.lenient_filter
    # effective filter(단일 소스)에는 유지 — 후속 실효화 재사용
    assert "viewer_department_ids" in tool._get_effective_filter()


@pytest.mark.asyncio
async def test_visibility_moved_to_lenient_filter():
    """부서 권한 없음 → visibility=public은 lenient로 이동 (완화 매칭)."""
    tool, hybrid, _ = _tool(_PUBLIC_PERMS)

    await tool._arun("질의")

    req = hybrid.calls[0]
    assert "visibility" not in req.metadata_filter
    assert req.lenient_filter == {"visibility": "public"}


@pytest.mark.asyncio
async def test_base_filter_keys_stay_hard():
    """사용자 지정 metadata_filter 키는 기존대로 hard 유지."""
    tool, hybrid, _ = _tool(_DEPT_PERMS, metadata_filter={"category": "policy"})

    await tool._arun("질의")

    req = hybrid.calls[0]
    assert req.metadata_filter == {"category": "policy"}


@pytest.mark.asyncio
async def test_multi_query_path_receives_split_filters():
    """multi_query 경로에도 hard/lenient 분리 전달."""
    mq = AsyncMock()
    mq.execute.return_value = SimpleNamespace(
        results=[], per_query_hits=[], generated_queries=[],
    )
    tool, _, _ = _tool(
        _PUBLIC_PERMS,
        metadata_filter={"category": "policy"},
        use_multi_query=True,
        multi_query_use_case=mq,
    )

    await tool._arun("질의")

    kwargs = mq.execute.call_args.kwargs
    assert kwargs["metadata_filter"] == {"category": "policy"}
    assert kwargs["lenient_filter"] == {"visibility": "public"}


# ── D2: 0건 강등 경고 로그 ───────────────────────────────────


@pytest.mark.asyncio
async def test_empty_result_with_injected_keys_logs_warning():
    tool, _, logger = _tool(_DEPT_PERMS)

    await tool._arun("나의 휴가")

    warns = _empty_warnings(logger)
    assert len(warns) == 1
    assert warns[0]["injected_keys"] == ["viewer_department_ids"]
    assert warns[0]["request_id"] == "req-1"


@pytest.mark.asyncio
async def test_no_empty_warning_when_results_exist():
    hit = SimpleNamespace(
        id="c1", content="본문", score=1.0, metadata={},
        bm25_rank=1, bm25_score=1.0, vector_rank=None, vector_score=None,
        source="bm25_only",
    )
    tool, _, logger = _tool(_DEPT_PERMS, results=[hit])

    await tool._arun("질의")

    assert _empty_warnings(logger) == []
