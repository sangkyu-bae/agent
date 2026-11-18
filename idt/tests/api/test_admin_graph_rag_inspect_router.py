"""엔티티·검색 테스트·정합성 API L1 — Design §4.1·§4.2 (module-5b)."""
from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.admin_graph_rag_router import (
    get_inspect_use_case,
    get_search_test_use_case,
)
from src.api.routes.admin_graph_rag_router import router as admin_router
from src.application.graph_rag.admin.search_test_use_case import SearchTestResult
from src.domain.auth.entities import UserRole
from src.domain.graph_rag.exceptions import (
    GraphBackendUnavailableError,
    GraphStageOffError,
)
from src.domain.graph_rag.inspection import (
    EntityDetail,
    EntitySummary,
    IntegrityReport,
    MentionView,
    RelationView,
)
from src.domain.graph_rag.retrieval import (
    GraphSearchTrace,
    LinkedEntity,
    PathHit,
    QueryScope,
)
from src.domain.hybrid_search.schemas import HybridSearchResult
from src.interfaces.dependencies.auth import get_current_user

from tests.api.test_admin_graph_rag_router import _user

_BASE = "/api/v1/admin/graph-rag"


def _client(inspect=None, search=None, user=None) -> TestClient:
    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[get_inspect_use_case] = lambda: inspect or AsyncMock()
    app.dependency_overrides[get_search_test_use_case] = lambda: search or AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    return TestClient(app)


def _entity():
    return EntitySummary("e1", "A상품", "상품", "설명", 3, 2)


def _hit(cid, source):
    return HybridSearchResult(id=cid, content="본문", score=0.5, bm25_rank=None,
                              bm25_score=None, vector_rank=None, vector_score=None,
                              source=source,
                              metadata={"document_id": "doc", "filename": "a.pdf"})


def test_entity_list_and_detail():
    uc = AsyncMock()
    uc.entities.return_value = ([_entity()], 1)
    uc.entity.return_value = EntityDetail(
        entity=_entity(), aliases=["에이상품"],
        relations=[RelationView("r1", "out", "RELATES", "적용대상", "e2", "개인사업자",
                                "c1", "근거", "doc")],
        mentions=[MentionView("c1", "doc", "d1", "미리보기")],
    )
    c = _client(inspect=uc)
    r = c.get(f"{_BASE}/entities?q=상품&type=상품&page=2&size=10")
    assert r.status_code == 200
    assert r.json() == {"items": [{"id": "e1", "name": "A상품", "type": "상품",
                                   "description": "설명", "mention_count": 3,
                                   "relation_count": 2}],
                        "total": 1, "page": 2, "size": 10}
    assert uc.entities.call_args.kwargs == {"query": "상품", "type_": "상품",
                                            "page": 2, "size": 10}
    body = c.get(f"{_BASE}/entities/e1").json()
    assert body["aliases"] == ["에이상품"]
    assert body["relations"][0]["other_name"] == "개인사업자"
    assert body["mentions"][0]["preview"] == "미리보기"


def test_entity_not_found_404():
    uc = AsyncMock()
    uc.entity.return_value = None
    r = _client(inspect=uc).get(f"{_BASE}/entities/nope")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "GRAPH_ENTITY_NOT_FOUND"


def test_search_test_response_shape():
    trace = GraphSearchTrace(
        scope=QueryScope(("t1",), ("여신관리",), "llm"),
        linked=[LinkedEntity("e1", "A상품", "상품", "exact", 1.0)],
        paths=[PathHit(("A상품", "개인사업자"), ("적용대상",), ("c1",))],
        hits=[_hit("c1", "graph")],
        timings_ms={"route_link": 10},
    )
    uc = AsyncMock()
    uc.run.return_value = SearchTestResult(
        trace=trace, hybrid_hits=[_hit("c2", "both")],
        fused_hits=[_hit("c1", "graph"), _hit("c2", "both")],
    )
    r = _client(search=uc).post(f"{_BASE}/search-test",
                                json={"query": "A상품 대상", "kb_id": "kb1", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == {"topic_ids": ["t1"], "topic_names": ["여신관리"],
                             "decided_by": "llm", "reason": None}
    assert body["paths"][0]["path"] == ["A상품", "적용대상→", "개인사업자"]
    assert body["graph_hits"][0]["filename"] == "a.pdf"
    assert [h["source"] for h in body["fused_hits"]] == ["graph", "both"]
    assert uc.run.call_args.kwargs["kb_id"] == "kb1"


def test_search_test_validation_and_errors():
    c = _client()
    assert c.post(f"{_BASE}/search-test", json={"query": ""}).status_code == 422
    assert c.post(f"{_BASE}/search-test",
                  json={"query": "q", "max_hops": 4}).status_code == 422
    for exc, code, http in [
        (GraphStageOffError("x"), "GRAPH_STAGE_OFF", 409),
        (GraphBackendUnavailableError("x"), "GRAPH_BACKEND_UNAVAILABLE", 503),
    ]:
        uc = AsyncMock()
        uc.run.side_effect = exc
        r = _client(search=uc).post(f"{_BASE}/search-test", json={"query": "q"})
        assert r.status_code == http and r.json()["detail"]["code"] == code


def test_integrity():
    uc = AsyncMock()
    uc.integrity.return_value = IntegrityReport(3, 1, ("c9",), ("doc-x",))
    r = _client(inspect=uc).get(f"{_BASE}/integrity?kb_id=kb1&sample=100")
    assert r.status_code == 200
    assert r.json() == {"checked": 3, "missing": 1, "missing_chunk_ids": ["c9"],
                        "missing_document_ids": ["doc-x"]}


def test_admin_only():
    c = _client(user=_user(UserRole.USER))
    assert c.get(f"{_BASE}/entities").status_code == 403
    assert c.post(f"{_BASE}/search-test", json={"query": "q"}).status_code == 403
    assert c.get(f"{_BASE}/integrity").status_code == 403
