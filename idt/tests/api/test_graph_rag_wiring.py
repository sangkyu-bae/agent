"""wire_graph_rag 조립 (Design §2.1 / D11, Plan SC-9).

- backend off: 노출 판단 등록·라우터 등록, Neo4j 드라이버는 만들지 않는다
- backend 오타·접속 정보 누락: 경고 후 off 와 같이 동작(앱 기동 유지)
- start/close 는 wire 하지 않아도 no-op
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from src.api import graph_rag_di
from src.domain.extension_hooks import ExtensionHooks


def _settings(**over):
    base = dict(
        graph_backend="off", neo4j_uri=None, neo4j_user="neo4j",
        neo4j_password=None, neo4j_database="neo4j", neo4j_max_pool_size=10,
        neo4j_connect_timeout_s=5.0, graph_entity_embedding_dimensions=512,
        graph_aura_free_node_limit=200000, graph_aura_free_rel_limit=400000,
        es_host="localhost", es_port=9200, es_scheme="http", es_index="documents",
        graph_entity_embedding_model=None, openai_embedding_model="text-embedding-3-small",
        openai_api_key="test-key", judgment_timeout_seconds=3.0,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _wire(**over):
    app, hooks, logger = FastAPI(), ExtensionHooks(), MagicMock()
    runtime = graph_rag_di.wire_graph_rag(
        app, get_session=lambda: None, session_factory=MagicMock(),
        hooks=hooks, logger=logger, settings=_settings(**over),
    )
    return app, hooks, logger, runtime


def _paths(app):
    # app.routes 순회는 _IncludedRouter 로 깨진다(위키 router-map) — openapi 로 확인.
    return set(app.openapi()["paths"])


def test_off_registers_exposure_and_routes_without_store():
    app, hooks, _, runtime = _wire()
    assert hooks.exposure is not None
    assert hooks.post_ingest is not None          # module-3 추출 훅
    assert hooks.supplemental is None and hooks.deletion is None  # module-5
    assert runtime.store is None and runtime.backend == "off"
    paths = _paths(app)
    assert "/api/v1/admin/graph-rag/settings" in paths
    assert "/api/v1/graph-rag/capabilities" in paths
    assert "/api/v1/admin/graph-rag/documents/{document_id}/extract" in paths
    assert "/api/v1/admin/graph-rag/kbs/{kb_id}/documents" in paths
    assert "/api/v1/admin/graph-rag/jobs/{job_id}" in paths
    assert "/api/v1/admin/graph-rag/review" in paths
    assert "/api/v1/admin/graph-rag/review/{decision_id}/reject" in paths
    assert "/api/v1/admin/graph-rag/topics" in paths
    assert "/api/v1/admin/graph-rag/topics/{topic_id}" in paths


def test_wire_accepts_judgment_backend():
    app, hooks, logger = FastAPI(), ExtensionHooks(), MagicMock()
    runtime = graph_rag_di.wire_graph_rag(
        app, get_session=lambda: None, session_factory=MagicMock(),
        hooks=hooks, logger=logger, settings=_settings(), judgment_backend=MagicMock(),
    )
    assert runtime is not None and hooks.post_ingest is not None


@pytest.mark.asyncio
async def test_start_marks_interrupted_jobs_even_without_store(monkeypatch):
    calls = []

    class _JobStore:
        async def fail_interrupted(self, request_id):
            calls.append(request_id)
            return 2

    runtime = graph_rag_di.GraphRagRuntime(
        backend="off", store=None, reader=MagicMock(), logger=MagicMock(),
        embedding_dimensions=512, job_store=_JobStore(),
    )
    monkeypatch.setattr(graph_rag_di, "_runtime", runtime)
    await graph_rag_di.start_graph_rag()
    assert calls == ["graph-rag-startup"]


@pytest.mark.parametrize("over", [
    {"graph_backend": "neo4jj"},
    {"graph_backend": "neo4j", "neo4j_uri": None, "neo4j_password": "x"},
    {"graph_backend": "neo4j", "neo4j_uri": "bolt://h:7687", "neo4j_password": None},
])
def test_bad_backend_config_falls_back_to_off_with_warning(over):
    _, hooks, logger, runtime = _wire(**over)
    assert runtime.store is None
    assert hooks.exposure is not None
    assert logger.warning.called


def test_neo4j_builds_store(monkeypatch):
    built = {}

    def _fake_driver(uri, user, password, **kw):
        built.update(uri=uri, user=user, **kw)
        return MagicMock()

    monkeypatch.setattr(graph_rag_di, "build_driver", _fake_driver)
    _, _, _, runtime = _wire(
        graph_backend="neo4j", neo4j_uri="neo4j+s://x.databases.neo4j.io",
        neo4j_password="pw",
    )
    assert runtime.store is not None and runtime.backend == "neo4j"
    assert built["uri"] == "neo4j+s://x.databases.neo4j.io"


@pytest.mark.asyncio
async def test_start_and_close_are_noop_when_not_wired(monkeypatch):
    monkeypatch.setattr(graph_rag_di, "_runtime", None)
    await graph_rag_di.start_graph_rag()
    await graph_rag_di.close_graph_rag()


@pytest.mark.asyncio
async def test_start_disables_store_on_dim_mismatch(monkeypatch):
    from src.domain.graph_rag.exceptions import GraphEmbeddingDimMismatchError

    from tests.application.graph_rag.fakes import FakeStore

    class _Mismatch(FakeStore):
        async def ensure_schema(self, embedding_dimensions):
            raise GraphEmbeddingDimMismatchError("1536 != 512")

    logger = MagicMock()
    runtime = graph_rag_di.GraphRagRuntime(
        backend="neo4j", store=_Mismatch(), reader=MagicMock(), logger=logger,
        embedding_dimensions=512,
    )
    monkeypatch.setattr(graph_rag_di, "_runtime", runtime)
    await graph_rag_di.start_graph_rag()
    assert runtime.store is None and runtime.disabled_reason
    assert logger.error.called


@pytest.mark.asyncio
async def test_start_keeps_store_when_backend_temporarily_down(monkeypatch):
    from tests.application.graph_rag.fakes import FakeStore

    class _Down(FakeStore):
        async def ensure_schema(self, embedding_dimensions):
            from src.domain.graph_rag.exceptions import GraphBackendUnavailableError
            raise GraphBackendUnavailableError("aura paused")

    logger = MagicMock()
    store = _Down()
    runtime = graph_rag_di.GraphRagRuntime(
        backend="neo4j", store=store, reader=MagicMock(), logger=logger,
        embedding_dimensions=512,
    )
    monkeypatch.setattr(graph_rag_di, "_runtime", runtime)
    await graph_rag_di.start_graph_rag()
    assert runtime.store is store  # Aura 정지는 일시적 — 다음 요청에서 재시도
    assert logger.warning.called
    await graph_rag_di.close_graph_rag()
    assert store.closed
