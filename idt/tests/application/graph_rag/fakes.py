"""graph_rag 애플리케이션 테스트용 페이크."""
from __future__ import annotations

import dataclasses

from src.domain.graph_rag.exceptions import GraphBackendUnavailableError
from src.domain.graph_rag.interfaces import (
    EvalEvidenceVerifierPort,
    GraphRagSettingsRepositoryPort,
    GraphSettingsReaderPort,
    GraphStorePort,
    StageChangeRepositoryPort,
)
from src.domain.graph_rag.value_objects import GraphRagSettings


class FakeSettingsRepo(GraphRagSettingsRepositoryPort):
    def __init__(self, settings: GraphRagSettings | None = None):
        self.settings = settings or GraphRagSettings.defaults()
        self.updates: list[GraphRagSettings] = []

    async def get(self, request_id):
        return self.settings

    async def update(self, settings, request_id):
        self.updates.append(settings)
        self.settings = settings
        return settings


class FakeStageRepo(StageChangeRepositoryPort):
    def __init__(self):
        self.added = []

    async def add(self, change, request_id):
        self.added.append(change)

    async def list_recent(self, limit, request_id):
        return list(reversed(self.added))[:limit]


class FakeReader(GraphSettingsReaderPort):
    def __init__(self, settings: GraphRagSettings | None = None, *, fail=False):
        self.settings = settings or GraphRagSettings.defaults()
        self.invalidations = 0
        self.fail = fail

    async def get(self):
        if self.fail:
            raise RuntimeError("db down")
        return self.settings

    def invalidate(self):
        self.invalidations += 1

    def with_stage(self, stage):
        self.settings = dataclasses.replace(self.settings, rollout_stage=stage)
        return self


class FakeVerifier(EvalEvidenceVerifierPort):
    def __init__(self, ok: bool):
        self.ok = ok
        self.calls = []

    async def is_valid(self, baseline_run_id, graph_run_id, request_id):
        self.calls.append((baseline_run_id, graph_run_id))
        return self.ok


class FakeStore(GraphStorePort):
    def __init__(self, *, down=False, counts=(10, 20)):
        self.down = down
        self._counts = counts
        self.schema_dims = []
        self.closed = False

    async def ping(self):
        if self.down:
            raise GraphBackendUnavailableError("down")

    async def counts(self):
        if self.down:
            raise GraphBackendUnavailableError("down")
        return self._counts

    async def ensure_schema(self, embedding_dimensions):
        self.schema_dims.append(embedding_dimensions)

    async def aclose(self):
        self.closed = True

    # ── module-3: 메모리 그래프 ─────────────────────────────────────────────
    def _graph(self):
        if not hasattr(self, "entities"):
            self.entities = {}     # id -> EntityWrite
            self.chunks = {}       # chunk_id -> (document_id, version)
            self.mentions = []     # (entity_id, chunk_id, decision_id, document_id)
            self.relations = {}    # id -> (RelationWrite, document_id)
            self.writes = []
            self.fail_chunks = set()
        return self

    async def extracted_chunk_ids(self, document_id, version):
        g = self._graph()
        return {c for c, (d, v) in g.chunks.items() if d == document_id and v == version}

    async def delete_document(self, document_id):
        g = self._graph()
        g.chunks = {c: dv for c, dv in g.chunks.items() if dv[0] != document_id}
        g.mentions = [m for m in g.mentions if m[3] != document_id]
        g.relations = {k: v for k, v in g.relations.items() if v[1] != document_id}
        alive = {m[0] for m in g.mentions}
        g.entities = {k: v for k, v in g.entities.items() if k in alive}

    async def find_entity_id(self, scope_key, normalized_name, type_):
        g = self._graph()
        for e in g.entities.values():
            if (e.scope_key, e.normalized_name, e.type) == (
                scope_key, normalized_name, type_
            ):
                return e.id
        return None

    async def write_chunk_graph(self, write):
        g = self._graph()
        if self.down:
            raise GraphBackendUnavailableError("down")
        if write.unit.chunk_id in g.fail_chunks:
            raise RuntimeError("write failed")
        g.writes.append(write)
        doc = write.unit.document_id
        g.chunks[write.unit.chunk_id] = (doc, write.extractor_version)
        for e in write.new_entities:
            g.entities[e.id] = e
        for m in write.mentions:
            g.mentions.append((m.entity_id, write.unit.chunk_id, m.decision_id, doc))
        for r in write.relations:
            g.relations[r.id] = (r, doc)
