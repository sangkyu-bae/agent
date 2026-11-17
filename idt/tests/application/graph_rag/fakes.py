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
