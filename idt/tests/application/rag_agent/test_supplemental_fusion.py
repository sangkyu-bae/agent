"""InternalDocumentSearchTool 보조 검색(그래프) 결합 게이트 테스트.

graph-rag-foundation Design §2.2·§7 / Plan FR-20·FR-14:
- 실행 조건 = use_supplemental AND grant 존재 AND 소스 배선
- 소스 실패·타임아웃은 기존 결과로 응답
- 라우팅 경로가 결과를 내면 보조 검색은 합치지 않는다 (module-1 결정)
"""
import asyncio
from types import SimpleNamespace

import pytest
from src.application.rag_agent.tools import InternalDocumentSearchTool
from src.domain.agent_run.auth_context import AuthContext
from src.domain.extension_hooks import (
    SupplementalGrant,
    SupplementalResult,
    SupplementalRetrievalSource,
)
from src.domain.hybrid_search.schemas import HybridSearchResult
from src.domain.permission.value_objects import PermissionCode


class _Logger:
    def __init__(self):
        self.infos: list[tuple[str, dict]] = []
        self.warnings: list[tuple[str, dict]] = []

    def debug(self, *a, **k): ...
    def info(self, msg, **k):
        self.infos.append((msg, k))
    def warning(self, msg, **k):
        self.warnings.append((msg, k))
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


def _hit(id_: str, source: str = "both") -> HybridSearchResult:
    return HybridSearchResult(
        id=id_, content=f"content-{id_}", score=0.1, bm25_rank=1, bm25_score=1.0,
        vector_rank=1, vector_score=0.9, source=source,
        metadata={"source": f"{id_}.pdf", "document_id": f"doc-{id_}"},
    )


class _Hybrid:
    def __init__(self, results):
        self._results = results

    async def execute(self, request, request_id):
        return SimpleNamespace(results=self._results)


class _Source(SupplementalRetrievalSource):
    def __init__(self, hits=None, *, raise_exc=None, sleep_s=0.0, skip=None):
        self.calls = []
        self._hits = hits or []
        self._raise = raise_exc
        self._sleep = sleep_s
        self._skip = skip

    async def retrieve(self, query):
        self.calls.append(query)
        if self._sleep:
            await asyncio.sleep(self._sleep)
        if self._raise:
            raise self._raise
        if self._skip:
            return SupplementalResult(label="graph", hits=[], skip_reason=self._skip)
        return SupplementalResult(label="graph", hits=list(self._hits), weight=0.5)


def _ctx(dept_read: bool = False) -> AuthContext:
    perms = {PermissionCode.USE_RAG_SEARCH.value}
    if dept_read:
        # visibility 강제가 없어야 라우팅 스코프가 강등되지 않는다
        perms.add(PermissionCode.READ_DEPARTMENT_DOCS.value)
    return AuthContext(
        user_id=1, display_name="u", role="user",
        primary_department_id=None, primary_department_name=None,
        department_ids=(), department_names=(),
        permissions=frozenset(perms),
    )


def _tool(primary, source=None, *, use=True, grant=SupplementalGrant(False),
          dept_read=False, **kw):
    logger = _Logger()
    tool = InternalDocumentSearchTool(
        hybrid_search_use_case=_Hybrid(primary),
        request_id="req-1",
        top_k=5,
        auth_ctx=_ctx(dept_read),
        logger=logger,
        collection_name="col",
        metadata_filter={"kb_id": "kb-1"},
        use_supplemental=use,
        supplemental_source=source,
        supplemental_grant=grant,
        **kw,
    )
    return tool, logger


def _ids(tool) -> list[str]:
    return [s.chunk_id for s in tool.collected_sources]


@pytest.mark.asyncio
async def test_all_conditions_met_fuses_graph_hits():
    src = _Source([_hit("g1", "graph")])
    tool, _ = _tool([_hit("a"), _hit("b")], src)
    out = await tool._arun("질문")
    assert len(src.calls) == 1
    assert "g1" in _ids(tool)
    assert "content-g1" in out


@pytest.mark.asyncio
async def test_query_carries_auth_filters_and_grant():
    src = _Source([])
    grant = SupplementalGrant(caller_is_admin=True)
    tool, _ = _tool([_hit("a")], src, grant=grant)
    await tool._arun("질문")
    q = src.calls[0]
    assert q.grant is grant
    assert q.collection_name == "col"
    assert q.hard_filter.get("kb_id") == "kb-1"
    # USE_RAG_SEARCH 만 있는 사용자 → visibility=public 이 lenient 로
    assert q.lenient_filter.get("visibility") == "public"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "use, grant, wired",
    [
        (False, SupplementalGrant(True), True),
        (True, None, True),
        (True, SupplementalGrant(True), False),
        (False, None, False),
    ],
)
async def test_gate_closed_keeps_primary_only(use, grant, wired):
    src = _Source([_hit("g1", "graph")])
    tool, _ = _tool([_hit("a")], src if wired else None, use=use, grant=grant)
    await tool._arun("질문")
    assert src.calls == [] or not wired
    assert _ids(tool) == ["a"]


@pytest.mark.asyncio
async def test_source_error_falls_back_to_primary():
    src = _Source(raise_exc=RuntimeError("neo4j down"))
    tool, logger = _tool([_hit("a")], src)
    out = await tool._arun("질문")
    assert _ids(tool) == ["a"]
    assert "content-a" in out
    assert any(k.get("reason") == "error" for _, k in logger.warnings)


@pytest.mark.asyncio
async def test_source_timeout_falls_back_to_primary(monkeypatch):
    import src.application.rag_agent.tools as tools_mod

    monkeypatch.setattr(tools_mod, "_SUPPLEMENTAL_HARD_TIMEOUT_S", 0.01)
    src = _Source([_hit("g1", "graph")], sleep_s=0.5)
    tool, logger = _tool([_hit("a")], src)
    await tool._arun("질문")
    assert _ids(tool) == ["a"]
    assert any(k.get("reason") == "timeout" for _, k in logger.warnings)


@pytest.mark.asyncio
async def test_skip_reason_logged_and_primary_kept():
    src = _Source(skip="grant_not_admin")
    tool, logger = _tool([_hit("a")], src)
    await tool._arun("질문")
    assert _ids(tool) == ["a"]
    assert any(
        k.get("reason") == "grant_not_admin" for _, k in logger.infos
    )


@pytest.mark.asyncio
async def test_primary_empty_but_graph_hits_are_returned():
    src = _Source([_hit("g1", "graph")])
    tool, _ = _tool([], src)
    out = await tool._arun("질문")
    assert "찾지 못했습니다" not in out
    assert _ids(tool) == ["g1"]


@pytest.mark.asyncio
async def test_routed_result_skips_supplemental():
    class _Routed:
        async def execute(self, query, scope, params, request_id):
            from src.domain.routed_retrieval.schemas import RoutedChunk

            chunk = RoutedChunk(
                document_id="d", section_ref="s1", content="routed body",
                score=0.5, clause_title="", document=None, section=None,
                from_fallback=True,
            )
            return SimpleNamespace(results=[chunk], fallback_count=1, fallback_used=True)

    src = _Source([_hit("g1", "graph")])
    tool, logger = _tool(
        [_hit("a")], src, dept_read=True,
        use_routed_search=True, routed_retrieval_getter=lambda: _Routed(),
    )
    out = await tool._arun("질문")
    assert "routed body" in out
    assert src.calls == []
    assert any(k.get("reason") == "routed_path" for _, k in logger.infos)


# ── module-5: 보조 검색을 기존 검색과 동시에 시작 (Design §11.9 지연 대응) ─────

class _SlowHybrid(_Hybrid):
    def __init__(self, results, sleep_s=0.0, raise_exc=None):
        super().__init__(results)
        self._sleep, self._raise = sleep_s, raise_exc

    async def execute(self, request, request_id):
        await asyncio.sleep(self._sleep)
        if self._raise:
            raise self._raise
        return SimpleNamespace(results=self._results)


@pytest.mark.asyncio
async def test_supplemental_runs_concurrently_with_primary():
    import time

    src = _Source([_hit("g1", "graph")], sleep_s=0.3)
    tool, _ = _tool([], src)
    tool.hybrid_search_use_case = _SlowHybrid([_hit("a")], sleep_s=0.3)
    started = time.perf_counter()
    await tool._arun("질문")
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5  # 직렬이면 0.6초 이상
    assert {"a", "g1"} <= set(_ids(tool))


@pytest.mark.asyncio
async def test_primary_failure_cancels_supplemental_task():
    src = _Source([_hit("g1", "graph")], sleep_s=5)
    tool, _ = _tool([], src)
    tool.hybrid_search_use_case = _SlowHybrid([], raise_exc=RuntimeError("es down"))
    before = {t for t in asyncio.all_tasks()}
    with pytest.raises(RuntimeError):
        await tool._arun("질문")  # 기존 오류 전파는 그대로
    await asyncio.sleep(0)
    leftover = [t for t in asyncio.all_tasks() - before if not t.done()]
    assert leftover == []
