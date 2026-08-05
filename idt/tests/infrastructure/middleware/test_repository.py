"""MiddlewareCatalogRepository / AgentMiddlewareRepository 단위 테스트 — AsyncMock."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.middleware.repository import (
    AgentMiddlewareRepository,
    MiddlewareCatalogRepository,
)


def _model(mw_type: str = "model_retry", **overrides):
    now = datetime.now(timezone.utc)
    m = MagicMock()
    m.id = f"mc-{mw_type}"
    m.middleware_type = mw_type
    m.name = "LLM 재시도"
    m.description = "d"
    m.is_builtin = True
    m.is_enforced = False
    m.default_config = {"max_retries": 3}
    m.is_active = True
    m.sort_order = 10
    m.created_at = now
    m.updated_at = now
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


def _repo(cls, execute_result=None):
    session = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)
    return cls(session=session, logger=MagicMock()), session


class TestCatalogRepository:
    @pytest.mark.asyncio
    async def test_list_all_maps_to_domain(self):
        result = MagicMock()
        result.scalars.return_value.all.return_value = [_model()]
        repo, _ = _repo(MiddlewareCatalogRepository, result)
        entries = await repo.list_all("req-1")
        assert len(entries) == 1
        assert entries[0].middleware_type.value == "model_retry"
        assert entries[0].default_config == {"max_retries": 3}

    @pytest.mark.asyncio
    async def test_find_by_type_none_when_missing(self):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        repo, _ = _repo(MiddlewareCatalogRepository, result)
        assert await repo.find_by_type("없는것", "req-1") is None

    @pytest.mark.asyncio
    async def test_update_flags_partial(self):
        model = _model()
        result = MagicMock()
        result.scalar_one_or_none.return_value = model
        repo, session = _repo(MiddlewareCatalogRepository, result)
        updated = await repo.update_flags(
            "model_retry",
            is_builtin=None,
            is_enforced=True,
            default_config=None,
            request_id="req-1",
        )
        assert model.is_enforced is True
        assert model.is_builtin is True  # None = 미변경
        assert updated is not None
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_all_skips_unknown_type_with_warning(self):
        """enum 미등록 타입 행은 skip+warning — 후속 미들웨어 INSERT가 전방 호환 (G3)."""
        result = MagicMock()
        result.scalars.return_value.all.return_value = [
            _model(),
            _model("future_middleware"),
        ]
        repo, _ = _repo(MiddlewareCatalogRepository, result)
        repo._logger = MagicMock()
        entries = await repo.list_all("req-1")
        assert [e.middleware_type.value for e in entries] == ["model_retry"]
        repo._logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_builtin_skips_unknown_type(self):
        result = MagicMock()
        result.scalars.return_value.all.return_value = [_model("future_middleware")]
        repo, _ = _repo(MiddlewareCatalogRepository, result)
        entries = await repo.list_builtin("req-1")
        assert entries == []

    @pytest.mark.asyncio
    async def test_find_by_type_unknown_row_returns_none(self):
        """미지 타입 행이 조회되면 500 대신 None(→404)."""
        result = MagicMock()
        result.scalar_one_or_none.return_value = _model("future_middleware")
        repo, _ = _repo(MiddlewareCatalogRepository, result)
        assert await repo.find_by_type("future_middleware", "req-1") is None

    @pytest.mark.asyncio
    async def test_update_flags_missing_returns_none(self):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        repo, _ = _repo(MiddlewareCatalogRepository, result)
        updated = await repo.update_flags(
            "없는것", is_builtin=True, is_enforced=None,
            default_config=None, request_id="req-1",
        )
        assert updated is None


class TestAgentMiddlewareRepository:
    @pytest.mark.asyncio
    async def test_list_by_agent_maps_records(self):
        row = MagicMock()
        row.agent_id = "agent-1"
        row.middleware_type = "model_retry"
        row.sort_order = 0
        row.config = None
        result = MagicMock()
        result.scalars.return_value.all.return_value = [row]
        repo, _ = _repo(AgentMiddlewareRepository, result)
        records = await repo.list_by_agent("agent-1", "req-1")
        assert len(records) == 1
        assert records[0].middleware_type == "model_retry"
