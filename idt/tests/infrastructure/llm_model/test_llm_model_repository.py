"""LlmModelRepository 통합 테스트 (SQLite + 실제 세션)."""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.domain.llm_model.entity import LlmModel
from src.infrastructure.llm_model.llm_model_repository import (
    LlmModelRepository,
)
from src.infrastructure.llm_model.models import LlmModelModel  # noqa: F401
from src.infrastructure.llm_model.seed import seed_default_models
from src.infrastructure.persistence.models.base import Base


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    url = f"sqlite+aiosqlite:///{tmp.name}"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            async with s.begin():
                yield s
    finally:
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _make_model(model_id: str = "m1", provider: str = "openai", model_name: str = "gpt-4o") -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id=model_id,
        provider=provider,
        model_name=model_name,
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_save_and_find_by_id(session: AsyncSession) -> None:
    repo = LlmModelRepository(session=session, logger=MagicMock())
    await repo.save(_make_model(), "req-1")

    fetched = await repo.find_by_id("m1", "req-1")
    assert fetched is not None
    assert fetched.provider == "openai"
    assert fetched.model_name == "gpt-4o"


@pytest.mark.asyncio
async def test_find_by_provider_and_name(session: AsyncSession) -> None:
    repo = LlmModelRepository(session=session, logger=MagicMock())
    await repo.save(_make_model(), "req-1")

    found = await repo.find_by_provider_and_name("openai", "gpt-4o", "req-1")
    assert found is not None
    assert found.id == "m1"

    miss = await repo.find_by_provider_and_name("openai", "missing", "req-1")
    assert miss is None


@pytest.mark.asyncio
async def test_unset_all_defaults(session: AsyncSession) -> None:
    repo = LlmModelRepository(session=session, logger=MagicMock())
    m1 = _make_model(model_id="a", model_name="gpt-4o")
    m1.is_default = True
    m2 = _make_model(model_id="b", model_name="gpt-4o-mini")
    m2.is_default = True
    await repo.save(m1, "req-1")
    await repo.save(m2, "req-1")

    await repo.unset_all_defaults("req-1")

    updated_a = await repo.find_by_id("a", "req-1")
    updated_b = await repo.find_by_id("b", "req-1")
    assert updated_a.is_default is False
    assert updated_b.is_default is False


@pytest.mark.asyncio
async def test_list_active_excludes_inactive(session: AsyncSession) -> None:
    repo = LlmModelRepository(session=session, logger=MagicMock())
    active = _make_model(model_id="act", model_name="gpt-4o")
    inactive = _make_model(model_id="in", model_name="gpt-3.5")
    inactive.is_active = False
    await repo.save(active, "req-1")
    await repo.save(inactive, "req-1")

    only_active = await repo.list_active("req-1")
    ids = {m.id for m in only_active}
    assert "act" in ids
    assert "in" not in ids


@pytest.mark.asyncio
async def test_find_default(session: AsyncSession) -> None:
    repo = LlmModelRepository(session=session, logger=MagicMock())
    d = _make_model(model_id="d", model_name="gpt-4o")
    d.is_default = True
    await repo.save(d, "req-1")

    default = await repo.find_default("req-1")
    assert default is not None
    assert default.id == "d"


@pytest.mark.asyncio
async def test_seed_default_models_inserts_three(session: AsyncSession) -> None:
    repo = LlmModelRepository(session=session, logger=MagicMock())
    await seed_default_models(repo, MagicMock(), "req-1")

    models = await repo.list_all("req-1")
    assert len(models) == 3
    providers = {m.provider for m in models}
    assert providers == {"openai", "anthropic"}

    defaults = [m for m in models if m.is_default]
    assert len(defaults) == 1
    assert defaults[0].model_name == "gpt-4o"


@pytest.mark.asyncio
async def test_seed_is_idempotent(session: AsyncSession) -> None:
    repo = LlmModelRepository(session=session, logger=MagicMock())
    await seed_default_models(repo, MagicMock(), "req-1")
    await seed_default_models(repo, MagicMock(), "req-2")  # 재실행

    models = await repo.list_all("req-2")
    assert len(models) == 3  # 중복 삽입 없음
