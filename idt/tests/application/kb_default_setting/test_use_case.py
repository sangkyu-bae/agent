"""KbDefaultSettingUseCase — agent-kb-quick-setup Design §4.2 admin / FR-01, FR-03."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.kb_default_setting.use_case import KbDefaultSettingUseCase
from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.kb_default_setting.entities import KbDefaultSetting
from src.domain.kb_default_setting.errors import (
    EmbeddingModelInactiveError,
    EmbeddingModelNotFoundError,
    KbDefaultsNotConfiguredError,
)


def _model(model_id: int = 2, active: bool = True) -> EmbeddingModel:
    now = datetime.now(UTC)
    return EmbeddingModel(
        id=model_id,
        provider="openai",
        model_name="text-embedding-3-small",
        display_name="OpenAI small",
        vector_dimension=1536,
        is_active=active,
        description=None,
        created_at=now,
        updated_at=now,
    )


def _setting(model_id: int | None) -> KbDefaultSetting:
    return KbDefaultSetting(
        default_embedding_model_id=model_id,
        updated_at=datetime(2026, 11, 5, tzinfo=UTC),
    )


@pytest.fixture
def settings_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get.return_value = _setting(None)
    repo.update.side_effect = lambda s, request_id: s
    return repo


@pytest.fixture
def model_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id.return_value = _model()
    return repo


@pytest.fixture
def use_case(settings_repo, model_repo) -> KbDefaultSettingUseCase:
    return KbDefaultSettingUseCase(
        settings_repo=settings_repo,
        embedding_model_repo=model_repo,
        logger=MagicMock(),
    )


class TestGet:
    async def test_unconfigured_view(self, use_case):
        view = await use_case.get("req")
        assert view.configured is False
        assert view.model is None
        assert view.warnings == ()

    async def test_configured_view_loads_model(self, use_case, settings_repo):
        settings_repo.get.return_value = _setting(2)
        view = await use_case.get("req")
        assert view.configured is True
        assert view.model is not None and view.model.id == 2

    async def test_broken_reference_warns_and_unconfigured(
        self, use_case, settings_repo, model_repo
    ):
        settings_repo.get.return_value = _setting(9)
        model_repo.find_by_id.return_value = None
        view = await use_case.get("req")
        assert view.configured is False
        assert view.warnings and "9" in view.warnings[0]

    async def test_inactive_model_warns_and_unconfigured(
        self, use_case, settings_repo, model_repo
    ):
        settings_repo.get.return_value = _setting(2)
        model_repo.find_by_id.return_value = _model(active=False)
        view = await use_case.get("req")
        assert view.configured is False
        assert view.warnings


class TestUpdate:
    async def test_sets_model_and_returns_view(self, use_case, settings_repo):
        view = await use_case.update(2, "req")
        assert view.configured is True
        saved = settings_repo.update.await_args.args[0]
        assert saved.default_embedding_model_id == 2

    async def test_unknown_model_raises(self, use_case, model_repo):
        model_repo.find_by_id.return_value = None
        with pytest.raises(EmbeddingModelNotFoundError):
            await use_case.update(77, "req")

    async def test_inactive_model_raises(self, use_case, model_repo):
        model_repo.find_by_id.return_value = _model(active=False)
        with pytest.raises(EmbeddingModelInactiveError):
            await use_case.update(2, "req")


class TestResolveDefaultModel:
    async def test_returns_active_model(self, use_case, settings_repo):
        settings_repo.get.return_value = _setting(2)
        model = await use_case.resolve_default_model("req")
        assert model.model_name == "text-embedding-3-small"

    async def test_unconfigured_raises(self, use_case):
        with pytest.raises(KbDefaultsNotConfiguredError):
            await use_case.resolve_default_model("req")

    async def test_broken_or_inactive_raises_not_configured(
        self, use_case, settings_repo, model_repo
    ):
        settings_repo.get.return_value = _setting(2)
        model_repo.find_by_id.return_value = _model(active=False)
        with pytest.raises(KbDefaultsNotConfiguredError):
            await use_case.resolve_default_model("req")
