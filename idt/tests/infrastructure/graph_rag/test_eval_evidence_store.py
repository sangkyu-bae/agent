"""RagasEvalEvidence — evaluation_run 에서 근거 2건을 읽어 규칙 적용 (SQLite 실세션)."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.infrastructure.graph_rag.eval_evidence import RagasEvalEvidence
from src.infrastructure.persistence.models.base import Base
from src.infrastructure.ragas.models import EvaluationRunModel


@pytest.fixture
async def factory():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _row(id_, *, on, status="completed", agent="agent-1"):
    return EvaluationRunModel(
        id=id_,
        eval_type="batch",
        target_type="agent",
        target_id=agent,
        status=status,
        total_cases=3,
        created_at=datetime(2026, 11, 18),
        config={"testset_id": "ts-1", "allow_supplemental": on},
    )


@pytest.mark.asyncio
async def test_completed_off_on_pair_is_valid(factory):
    async with factory() as s:
        s.add_all(
            [
                _row("b", on=False),
                _row("g", on=True),
                _row("x", on=True, status="running"),
            ]
        )
        await s.commit()
        ev = RagasEvalEvidence(s, MagicMock())
        assert await ev.is_valid("b", "g", "r") is True
        assert await ev.is_valid("g", "b", "r") is False  # 순서 뒤바뀜
        assert await ev.is_valid("b", "x", "r") is False  # 미완료
        assert await ev.is_valid("b", "nope", "r") is False
        assert await ev.is_valid(None, "g", "r") is False


@pytest.mark.asyncio
async def test_legacy_config_without_flag_counts_as_off(factory):
    async with factory() as s:
        legacy = _row("old", on=False)
        legacy.config = {"testset_id": "ts-1"}
        s.add_all([legacy, _row("g", on=True)])
        await s.commit()
        assert await RagasEvalEvidence(s, MagicMock()).is_valid("old", "g", "r") is True
