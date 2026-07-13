from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.chunking_profile.use_case import ChunkingProfileUseCase
from src.domain.chunking_profile.entities import BoundaryRule, ChunkingProfile
from src.domain.chunking_profile.policy import ChunkingProfilePolicy


def _rules():
    return [
        BoundaryRule(pattern="^제[0-9]+조", priority=1, level="parent"),
        BoundaryRule(pattern="^[ ]*[0-9]+[.]", priority=1, level="child"),
    ]


def _profile(pid="p1", is_default=False, status="active"):
    return ChunkingProfile(
        id=pid,
        name="법령",
        boundary_rules=_rules(),
        is_default=is_default,
        status=status,
    )


@pytest.fixture
def repo():
    r = AsyncMock()
    r.exists_active_name.return_value = False
    r.save.side_effect = lambda p, rid: p
    r.update.side_effect = lambda p, rid: p
    return r


@pytest.fixture
def use_case(repo):
    return ChunkingProfileUseCase(repo, ChunkingProfilePolicy(), MagicMock())


class TestSummaryModelValidation:
    """card-section-summary D16 — summary_llm_model_id 존재+활성 검증."""

    def _llm_repo(self, model):
        r = AsyncMock()
        r.find_by_id.return_value = model
        return r

    def _use_case(self, repo, llm_repo):
        return ChunkingProfileUseCase(
            repo, ChunkingProfilePolicy(), MagicMock(), llm_model_repo=llm_repo
        )

    @pytest.mark.asyncio
    async def test_active_model_accepted_and_saved(self, repo):
        llm_repo = self._llm_repo(MagicMock(is_active=True))
        uc = self._use_case(repo, llm_repo)
        result = await uc.create(
            name="법령", boundary_rules=_rules(),
            parent_chunk_size=2000, chunk_size=500, chunk_overlap=50,
            description=None, is_default=False, request_id="r",
            summary_llm_model_id="model-1",
        )
        assert result.summary_llm_model_id == "model-1"
        llm_repo.find_by_id.assert_awaited_once_with("model-1", "r")

    @pytest.mark.asyncio
    async def test_missing_model_rejected(self, repo):
        uc = self._use_case(repo, self._llm_repo(None))
        with pytest.raises(ValueError, match="summary_llm_model_id"):
            await uc.create(
                name="법령", boundary_rules=_rules(),
                parent_chunk_size=2000, chunk_size=500, chunk_overlap=50,
                description=None, is_default=False, request_id="r",
                summary_llm_model_id="ghost",
            )

    @pytest.mark.asyncio
    async def test_inactive_model_rejected_on_update(self, repo):
        repo.find_by_id.return_value = _profile()
        uc = self._use_case(repo, self._llm_repo(MagicMock(is_active=False)))
        with pytest.raises(ValueError, match="summary_llm_model_id"):
            await uc.update(
                profile_id="p1", name="법령", boundary_rules=_rules(),
                parent_chunk_size=2000, chunk_size=500, chunk_overlap=50,
                description=None, is_default=False, request_id="r",
                summary_llm_model_id="model-off",
            )

    @pytest.mark.asyncio
    async def test_none_skips_validation(self, repo):
        llm_repo = self._llm_repo(None)
        uc = self._use_case(repo, llm_repo)
        await uc.create(
            name="법령", boundary_rules=_rules(),
            parent_chunk_size=2000, chunk_size=500, chunk_overlap=50,
            description=None, is_default=False, request_id="r",
        )
        llm_repo.find_by_id.assert_not_awaited()


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_assigns_uuid(self, use_case, repo):
        result = await use_case.create(
            name="법령", boundary_rules=_rules(),
            parent_chunk_size=2000, chunk_size=500, chunk_overlap=50,
            description=None, is_default=False, request_id="r",
        )
        assert result.id is not None
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_name_raises(self, use_case, repo):
        repo.exists_active_name.return_value = True
        with pytest.raises(ValueError, match="already exists"):
            await use_case.create(
                name="법령", boundary_rules=_rules(),
                parent_chunk_size=2000, chunk_size=500, chunk_overlap=50,
                description=None, is_default=False, request_id="r",
            )

    @pytest.mark.asyncio
    async def test_default_clears_previous_default(self, use_case, repo):
        await use_case.create(
            name="법령", boundary_rules=_rules(),
            parent_chunk_size=2000, chunk_size=500, chunk_overlap=50,
            description=None, is_default=True, request_id="r",
        )
        repo.clear_default.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_rules_rejected(self, use_case):
        with pytest.raises(ValueError):
            await use_case.create(
                name="법령",
                boundary_rules=[
                    BoundaryRule(pattern="^(", priority=1, level="parent")
                ],
                parent_chunk_size=2000, chunk_size=500, chunk_overlap=50,
                description=None, is_default=False, request_id="r",
            )


class TestGet:
    @pytest.mark.asyncio
    async def test_not_found_raises(self, use_case, repo):
        repo.find_by_id.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await use_case.get("x", "r")

    @pytest.mark.asyncio
    async def test_deleted_raises(self, use_case, repo):
        repo.find_by_id.return_value = _profile(status="deleted")
        with pytest.raises(ValueError, match="not found"):
            await use_case.get("p1", "r")


class TestSetDefault:
    @pytest.mark.asyncio
    async def test_clears_then_sets(self, use_case, repo):
        repo.find_by_id.return_value = _profile()
        await use_case.set_default("p1", "r")
        repo.clear_default.assert_awaited_once()
        repo.update.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_default_cannot_delete(self, use_case, repo):
        repo.find_by_id.return_value = _profile(is_default=True)
        with pytest.raises(ValueError, match="default"):
            await use_case.delete("p1", "r")
        repo.soft_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_default_deletes(self, use_case, repo):
        repo.find_by_id.return_value = _profile(is_default=False)
        await use_case.delete("p1", "r")
        repo.soft_delete.assert_awaited_once()


class TestUpdate:
    @pytest.mark.asyncio
    async def test_duplicate_name_excludes_self(self, use_case, repo):
        repo.find_by_id.return_value = _profile()
        repo.exists_active_name.return_value = True
        with pytest.raises(ValueError, match="already exists"):
            await use_case.update(
                profile_id="p1", name="법령", boundary_rules=_rules(),
                parent_chunk_size=2000, chunk_size=500, chunk_overlap=50,
                description=None, is_default=False, request_id="r",
            )
