"""KnowledgeBaseRepository 단위 테스트 — AsyncMock 사용.

kb-custom-chunking Design §8.1: custom_chunking_config JSON 왕복 +
update_chunking() 화이트리스트(청킹 6개 컬럼만 UPDATE) 검증.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase
from src.infrastructure.knowledge_base.repository import (
    KnowledgeBaseRepository,
)

_CUSTOM_CONFIG = {
    "version": 1,
    "strategy": "boundary_pattern",
    "chunk_size": 600,
    "chunk_overlap": 80,
    "parent_chunk_size": 3000,
    "boundary_rules": [
        {"pattern": "^제\\d+장", "priority": 1, "level": "parent"},
        {"pattern": "^\\d+\\.\\s", "priority": 1, "level": "child"},
    ],
}


def _make_repo() -> tuple[KnowledgeBaseRepository, MagicMock]:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return KnowledgeBaseRepository(session=session, logger=MagicMock()), session


def _kb(**kw) -> KnowledgeBase:
    defaults = dict(
        id="kb-1",
        name="여신 규정집",
        owner_id=1,
        scope=CollectionScope.PERSONAL,
        collection_name="shared-col",
    )
    defaults.update(kw)
    return KnowledgeBase(**defaults)


class TestSaveCustomChunking:
    @pytest.mark.asyncio
    async def test_save_maps_custom_fields_to_model(self):
        repo, session = _make_repo()
        kb = _kb(
            use_custom_chunking=True,
            custom_chunking_config=_CUSTOM_CONFIG,
        )
        await repo.save(kb, "req-1")

        model = session.add.call_args.args[0]
        assert model.use_custom_chunking == 1
        assert model.custom_chunking_config == _CUSTOM_CONFIG

    @pytest.mark.asyncio
    async def test_save_returns_domain_with_config_roundtrip(self):
        """JSON(중첩 boundary_rules 포함)이 save→domain 왕복에서 무손실."""
        repo, session = _make_repo()
        kb = _kb(
            use_custom_chunking=True,
            custom_chunking_config=_CUSTOM_CONFIG,
        )
        saved = await repo.save(kb, "req-1")

        assert saved.use_custom_chunking is True
        assert saved.custom_chunking_config == _CUSTOM_CONFIG
        assert (
            saved.custom_chunking_config["boundary_rules"][0]["pattern"]
            == "^제\\d+장"
        )

    @pytest.mark.asyncio
    async def test_save_defaults_keep_custom_off(self):
        repo, session = _make_repo()
        await repo.save(_kb(), "req-1")
        model = session.add.call_args.args[0]
        assert model.use_custom_chunking == 0
        assert model.custom_chunking_config is None


class TestFindByIdCustomChunking:
    @pytest.mark.asyncio
    async def test_to_domain_maps_custom_fields(self):
        repo, session = _make_repo()
        mock_model = MagicMock()
        mock_model.id = "kb-1"
        mock_model.name = "여신 규정집"
        mock_model.description = None
        mock_model.owner_id = 1
        mock_model.scope = "PERSONAL"
        mock_model.department_id = None
        mock_model.collection_name = "shared-col"
        mock_model.status = "active"
        mock_model.use_clause_chunking = 0
        mock_model.chunking_profile_id = None
        mock_model.chunk_size = None
        mock_model.chunk_overlap = None
        mock_model.use_custom_chunking = 1
        mock_model.custom_chunking_config = _CUSTOM_CONFIG
        mock_model.created_at = None
        mock_model.updated_at = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        session.execute = AsyncMock(return_value=mock_result)

        kb = await repo.find_by_id("kb-1", "req-1")

        assert kb is not None
        assert kb.use_custom_chunking is True
        assert kb.custom_chunking_config == _CUSTOM_CONFIG


class TestUpdateChunkingWhitelist:
    """D8 — 청킹 6개 컬럼 화이트리스트만 UPDATE."""

    _CHUNKING_COLUMNS = {
        "use_clause_chunking",
        "chunking_profile_id",
        "chunk_size",
        "chunk_overlap",
        "use_custom_chunking",
        "custom_chunking_config",
    }

    async def _run_update(self):
        repo, session = _make_repo()
        await repo.update_chunking(
            "kb-1",
            use_clause_chunking=False,
            chunking_profile_id=None,
            chunk_size=None,
            chunk_overlap=None,
            use_custom_chunking=True,
            custom_chunking_config=_CUSTOM_CONFIG,
            request_id="req-1",
        )
        return session

    @pytest.mark.asyncio
    async def test_updates_only_whitelisted_columns(self):
        session = await self._run_update()
        stmt = session.execute.await_args.args[0]
        updated_columns = {c.name for c in stmt._values}
        assert updated_columns == self._CHUNKING_COLUMNS

    @pytest.mark.asyncio
    async def test_values_and_flush(self):
        session = await self._run_update()
        stmt = session.execute.await_args.args[0]
        values = {c.name: v.value for c, v in stmt._values.items()}
        assert values["use_custom_chunking"] == 1
        assert values["use_clause_chunking"] == 0
        assert values["custom_chunking_config"] == _CUSTOM_CONFIG
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_where_targets_kb_id(self):
        session = await self._run_update()
        stmt = session.execute.await_args.args[0]
        compiled = stmt.compile()
        assert compiled.params.get("id_1") == "kb-1"
