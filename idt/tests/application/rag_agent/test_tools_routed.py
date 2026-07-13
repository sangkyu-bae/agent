"""InternalDocumentSearchTool 라우팅 분기 테스트 (rag-routed-integration D3~D8).

기존 3모드 테스트는 무수정 유지 — false 경로 불변(FR-03)의 증명은 기존 스위트,
본 파일은 routed 분기·강등 4사유·포맷·관측 계약을 검증한다.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.application.rag_agent.tools import InternalDocumentSearchTool
from src.domain.agent_run.auth_context import AuthContext
from src.domain.permission.value_objects import PermissionCode
from src.domain.routed_retrieval.schemas import (
    DocumentCandidate,
    RoutedChunk,
    RoutedRetrievalResult,
    SectionCandidate,
)


class _FakeLogger:
    def __init__(self):
        self.warnings = []

    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, msg, **k):
        self.warnings.append((msg, k))
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


def _auth_ctx(codes: set[str]) -> AuthContext:
    return AuthContext(
        user_id=1,
        display_name="tester",
        role="user",
        primary_department_id="dept-1",
        primary_department_name="여신부",
        department_ids=("dept-1",),
        department_names=("여신부",),
        permissions=frozenset(codes),
    )


_FULL_PERMS = {
    PermissionCode.USE_RAG_SEARCH.value,
    PermissionCode.READ_DEPARTMENT_DOCS.value,
}


def _routed_result(chunks: list[RoutedChunk]) -> RoutedRetrievalResult:
    return RoutedRetrievalResult(
        query="q", results=chunks, fallback_used=False, fallback_count=0,
        document_candidates=1, section_candidates=1, request_id="req-1",
    )


def _chunk(from_fallback: bool = False) -> RoutedChunk:
    document = DocumentCandidate(
        document_id="doc-1", score=0.9, summary="문서 요약",
        keywords=["대출"], filename="여신규정.pdf",
    )
    section = SectionCandidate(
        section_ref="p1", document_id="doc-1", score=0.03,
        summary="첫 줄 요약\n둘째 줄\n셋째 줄", clause_title="제3조 (한도)",
        keywords=["한도"], vector_rank=1, bm25_rank=2, source="both",
    )
    if from_fallback:
        return RoutedChunk(
            section_ref="c9", document_id="doc-2", content="폴백 본문",
            score=0.01, clause_title="", from_fallback=True,
        )
    return RoutedChunk(
        section_ref="p1", document_id="doc-1", content="제3조 조문 본문",
        score=0.03, clause_title="제3조 (한도)",
        document=document, section=section,
    )


class _FakeHybrid:
    def __init__(self):
        self.calls = []

    async def execute(self, request, request_id):
        self.calls.append(request)
        return SimpleNamespace(results=[])


def _tool(
    routed_uc=None,
    use_routed_search=True,
    metadata_filter=None,
    perms=None,
    use_multi_query=False,
    multi_query_use_case=None,
    tracker=None,
):
    hybrid = _FakeHybrid()
    logger = _FakeLogger()
    tool = InternalDocumentSearchTool(
        hybrid_search_use_case=hybrid,
        request_id="req-1",
        top_k=5,
        metadata_filter=metadata_filter or {},
        use_routed_search=use_routed_search,
        routed_retrieval_getter=(lambda: routed_uc) if routed_uc else None,
        auth_ctx=_auth_ctx(perms if perms is not None else _FULL_PERMS),
        logger=logger,
        use_multi_query=use_multi_query,
        multi_query_use_case=multi_query_use_case,
        tracker=tracker,
        collection_name="col",
    )
    return tool, hybrid, logger


def _degrade_reasons(logger: _FakeLogger) -> list[str]:
    return [k.get("reason") for _, k in logger.warnings if "reason" in k]


@pytest.mark.asyncio
async def test_routed_success_returns_formatted_and_skips_legacy():
    routed_uc = AsyncMock()
    routed_uc.execute.return_value = _routed_result([_chunk()])
    tool, hybrid, _ = _tool(routed_uc)

    result = await tool._arun("여신 한도")

    assert "[출처: 여신규정.pdf > 제3조 (한도)]" in result
    assert "요약: 첫 줄 요약" in result
    assert "제3조 조문 본문" in result
    assert hybrid.calls == []  # 기존 검색 미호출


@pytest.mark.asyncio
async def test_disabled_flag_never_enters_routed_branch():
    routed_uc = AsyncMock()
    tool, hybrid, _ = _tool(routed_uc, use_routed_search=False)

    await tool._arun("질의")

    routed_uc.execute.assert_not_awaited()
    assert len(hybrid.calls) == 1  # 기존 경로(기준선)


@pytest.mark.asyncio
async def test_degrade_when_getter_not_wired():
    tool, hybrid, logger = _tool(routed_uc=None)

    await tool._arun("질의")

    assert len(hybrid.calls) == 1
    assert "not_wired" in _degrade_reasons(logger)


@pytest.mark.asyncio
async def test_degrade_on_visibility_forced():
    """부서 권한 없음 → visibility 강제 → filter_incompatible 강등 (누수 0, D4)."""
    routed_uc = AsyncMock()
    tool, hybrid, logger = _tool(
        routed_uc, perms={PermissionCode.USE_RAG_SEARCH.value}
    )

    await tool._arun("질의")

    routed_uc.execute.assert_not_awaited()
    assert len(hybrid.calls) == 1
    assert "filter_incompatible" in _degrade_reasons(logger)
    # 기존 경로에는 visibility 필터가 그대로 적용(권한 필터 보존)
    assert hybrid.calls[0].metadata_filter.get("visibility") == "public"


@pytest.mark.asyncio
async def test_degrade_on_custom_filter_key():
    routed_uc = AsyncMock()
    tool, hybrid, logger = _tool(
        routed_uc, metadata_filter={"category": "policy"}
    )

    await tool._arun("질의")

    routed_uc.execute.assert_not_awaited()
    assert "filter_incompatible" in _degrade_reasons(logger)


@pytest.mark.asyncio
async def test_viewer_department_ids_is_ignored_not_degraded():
    """부서 권한 보유 시 자동 주입되는 viewer_department_ids는 무시 (D4-②)."""
    routed_uc = AsyncMock()
    routed_uc.execute.return_value = _routed_result([_chunk()])
    tool, hybrid, _ = _tool(routed_uc)  # READ_DEPARTMENT_DOCS 보유 → 키 자동 주입

    result = await tool._arun("질의")

    routed_uc.execute.assert_awaited_once()
    assert hybrid.calls == []
    assert "제3조 조문 본문" in result


@pytest.mark.asyncio
async def test_kb_id_mapped_to_scope():
    routed_uc = AsyncMock()
    routed_uc.execute.return_value = _routed_result([_chunk()])
    tool, _, _ = _tool(routed_uc, metadata_filter={"kb_id": "kb-7"})

    await tool._arun("질의")

    _, scope, params, _ = routed_uc.execute.call_args[0]
    assert scope.kb_id == "kb-7"
    assert scope.collection_name == "col"
    assert params.top_k == 5


@pytest.mark.asyncio
async def test_degrade_on_execute_error_and_empty():
    # 예외 → error 강등
    routed_uc = AsyncMock()
    routed_uc.execute.side_effect = RuntimeError("boom")
    tool, hybrid, logger = _tool(routed_uc)
    await tool._arun("질의")
    assert len(hybrid.calls) == 1
    assert "error" in _degrade_reasons(logger)

    # 0건 → empty 강등
    routed_uc2 = AsyncMock()
    routed_uc2.execute.return_value = _routed_result([])
    tool2, hybrid2, logger2 = _tool(routed_uc2)
    await tool2._arun("질의")
    assert len(hybrid2.calls) == 1
    assert "empty" in _degrade_reasons(logger2)


@pytest.mark.asyncio
async def test_fallback_chunk_uses_legacy_format():
    routed_uc = AsyncMock()
    routed_uc.execute.return_value = _routed_result(
        [_chunk(), _chunk(from_fallback=True)]
    )
    tool, _, _ = _tool(routed_uc)

    result = await tool._arun("질의")

    assert "[출처: doc-2]\n폴백 본문" in result
    assert "요약: 첫 줄 요약" in result  # 라우팅 결과에만 요약 헤더


@pytest.mark.asyncio
async def test_collected_sources_and_record_retrieval_contract():
    tracker = AsyncMock()
    routed_uc = AsyncMock()
    routed_uc.execute.return_value = _routed_result([_chunk()])
    tool, _, _ = _tool(routed_uc, tracker=tracker)

    # RunContext 없는 환경 — record_retrieval은 skip되지만 sources는 수집
    await tool._arun("질의")

    assert len(tool.collected_sources) == 1
    src = tool.collected_sources[0]
    assert src.chunk_id == "p1"
    assert src.source == "여신규정.pdf > 제3조 (한도)"


@pytest.mark.asyncio
async def test_multi_query_bypassed_on_routed_success_but_used_on_degrade():
    multi_uc = AsyncMock()
    multi_uc.execute.return_value = SimpleNamespace(results=[])

    # routed 성공 → multi 미호출 (D7)
    routed_uc = AsyncMock()
    routed_uc.execute.return_value = _routed_result([_chunk()])
    tool, _, _ = _tool(
        routed_uc, use_multi_query=True, multi_query_use_case=multi_uc
    )
    await tool._arun("질의")
    multi_uc.execute.assert_not_awaited()

    # 강등 → 원래 규칙(multi 호출)
    tool2, _, _ = _tool(
        routed_uc=None, use_multi_query=True, multi_query_use_case=multi_uc
    )
    await tool2._arun("질의")
    multi_uc.execute.assert_awaited_once()
