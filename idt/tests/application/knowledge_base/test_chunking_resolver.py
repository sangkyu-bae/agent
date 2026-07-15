from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.chunking_resolver import (
    ChunkingSettingsResolver,
)
from src.domain.chunking_profile.entities import BoundaryRule, ChunkingProfile
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase


def _profile(pid="p1", status="active", chunk_size=500, chunk_overlap=50):
    return ChunkingProfile(
        id=pid,
        name="법령",
        boundary_rules=[
            BoundaryRule(pattern="^제[0-9]+조", priority=1, level="parent"),
            BoundaryRule(pattern="^[ ]*[0-9]+[.]", priority=1, level="child"),
        ],
        parent_chunk_size=2000,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        status=status,
    )


def _kb(**kw):
    defaults = dict(
        id="kb1", name="kb", owner_id=1,
        scope=CollectionScope.PERSONAL, collection_name="col",
        use_clause_chunking=True,
    )
    defaults.update(kw)
    return KnowledgeBase(**defaults)


@pytest.fixture
def repo():
    return AsyncMock()


@pytest.fixture
def resolver(repo):
    return ChunkingSettingsResolver(repo, MagicMock())


class TestResolve:
    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, resolver, repo):
        kb = _kb(use_clause_chunking=False)
        assert await resolver.resolve(kb, "r") is None

    @pytest.mark.asyncio
    async def test_specified_profile_used(self, resolver, repo):
        repo.find_by_id.return_value = _profile("p9")
        kb = _kb(chunking_profile_id="p9")
        cfg = await resolver.resolve(kb, "r")
        assert cfg.strategy == "clause_aware"
        assert cfg.display["profile_id"] == "p9"

    @pytest.mark.asyncio
    async def test_no_profile_id_uses_default(self, resolver, repo):
        repo.find_default.return_value = _profile("default")
        kb = _kb(chunking_profile_id=None)
        cfg = await resolver.resolve(kb, "r")
        assert cfg.display["profile_id"] == "default"
        repo.find_default.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deleted_profile_falls_back_to_default(self, resolver, repo):
        repo.find_by_id.return_value = _profile("p9", status="deleted")
        repo.find_default.return_value = _profile("default")
        kb = _kb(chunking_profile_id="p9")
        cfg = await resolver.resolve(kb, "r")
        assert cfg.display["profile_id"] == "default"

    @pytest.mark.asyncio
    async def test_no_default_returns_none(self, resolver, repo):
        repo.find_by_id.return_value = None
        repo.find_default.return_value = None
        kb = _kb(chunking_profile_id="p9")
        assert await resolver.resolve(kb, "r") is None

    @pytest.mark.asyncio
    async def test_override_size_used(self, resolver, repo):
        repo.find_by_id.return_value = _profile("p9", chunk_size=500)
        kb = _kb(chunking_profile_id="p9", chunk_size=800)
        cfg = await resolver.resolve(kb, "r")
        assert cfg.params["chunk_size"] == 800

    @pytest.mark.asyncio
    async def test_override_zero_overlap_respected(self, resolver, repo):
        repo.find_by_id.return_value = _profile("p9", chunk_overlap=50)
        kb = _kb(chunking_profile_id="p9", chunk_size=500, chunk_overlap=0)
        cfg = await resolver.resolve(kb, "r")
        assert cfg.params["chunk_overlap"] == 0


class TestResolveCustom:
    """kb-custom-chunking D6 — 커스텀 경로 해석 + 손상 시 legacy 폴백."""

    def _custom_kb(self, config, **kw):
        return _kb(
            use_clause_chunking=False,
            use_custom_chunking=True,
            custom_chunking_config=config,
            **kw,
        )

    @pytest.mark.asyncio
    async def test_full_token_resolved(self, resolver, repo):
        kb = self._custom_kb({
            "strategy": "full_token", "chunk_size": 1500,
            "chunk_overlap": 150,
        })
        cfg = await resolver.resolve(kb, "r")
        assert cfg.strategy == "full_token"
        assert cfg.params == {"chunk_size": 1500, "chunk_overlap": 150}
        assert cfg.display["custom"] is True
        repo.find_by_id.assert_not_awaited()
        repo.find_default.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_boundary_pattern_maps_to_clause_aware(
        self, resolver, repo
    ):
        kb = self._custom_kb({
            "strategy": "boundary_pattern",
            "chunk_size": 600,
            "chunk_overlap": 80,
            "parent_chunk_size": 3000,
            "boundary_rules": [
                {"pattern": r"^제\d+장", "priority": 1, "level": "parent"},
            ],
        })
        cfg = await resolver.resolve(kb, "r")
        assert cfg.strategy == "clause_aware"
        assert cfg.params["parent_patterns"] == [r"^제\d+장"]
        assert cfg.params["child_patterns"] == []
        assert cfg.display["strategy"] == "boundary_pattern"

    @pytest.mark.asyncio
    async def test_invalid_config_falls_back_to_legacy(self, repo):
        logger = MagicMock()
        resolver = ChunkingSettingsResolver(repo, logger)
        kb = self._custom_kb({"strategy": "magic"})
        assert await resolver.resolve(kb, "r") is None
        logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_config_falls_back_to_legacy(self, resolver, repo):
        kb = self._custom_kb(None)
        assert await resolver.resolve(kb, "r") is None

    @pytest.mark.asyncio
    async def test_custom_kb_has_no_summary_spec(self, resolver, repo):
        kb = self._custom_kb({
            "strategy": "full_token", "chunk_size": 500,
        })
        assert await resolver.resolve_summary_spec(kb, "r") is None
