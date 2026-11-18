"""CachedGraphSettingsReader — TTL 캐시·무효화·실패 시 닫힌 기본값 (Design §10.1)."""
import dataclasses
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from src.domain.graph_rag.value_objects import GraphRagSettings, RolloutStage
from src.infrastructure.graph_rag.settings_reader import CachedGraphSettingsReader


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class _Repo:
    def __init__(self, box):
        self._box = box

    async def get(self, request_id):
        self._box["calls"] += 1
        if self._box.get("fail"):
            raise RuntimeError("db down")
        return self._box["settings"]


def _reader(box, clock):
    @asynccontextmanager
    async def _session_scope():
        yield object()

    return CachedGraphSettingsReader(
        session_scope=_session_scope,
        repo_factory=lambda session: _Repo(box),
        logger=MagicMock(), ttl_seconds=30, clock=clock,
    )


def _admin_only():
    return dataclasses.replace(
        GraphRagSettings.defaults(), rollout_stage=RolloutStage.ADMIN_ONLY
    )


@pytest.mark.asyncio
async def test_caches_within_ttl_and_refreshes_after():
    box, clock = {"calls": 0, "settings": _admin_only()}, _Clock()
    reader = _reader(box, clock)
    await reader.get()
    await reader.get()
    assert box["calls"] == 1
    clock.t = 31
    await reader.get()
    assert box["calls"] == 2


@pytest.mark.asyncio
async def test_invalidate_forces_reload():
    box, clock = {"calls": 0, "settings": _admin_only()}, _Clock()
    reader = _reader(box, clock)
    await reader.get()
    reader.invalidate()
    await reader.get()
    assert box["calls"] == 2


@pytest.mark.asyncio
async def test_failure_returns_closed_defaults_and_is_not_cached():
    box, clock = {"calls": 0, "settings": _admin_only(), "fail": True}, _Clock()
    reader = _reader(box, clock)
    got = await reader.get()
    assert got.rollout_stage is RolloutStage.OFF
    box["fail"] = False
    got = await reader.get()  # 실패는 캐시하지 않는다 → 바로 다시 읽음
    assert got.rollout_stage is RolloutStage.ADMIN_ONLY
