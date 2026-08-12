"""Infrastructure 테스트: BackgroundJobRepository (Mock AsyncSession).

claim 의 FOR UPDATE SKIP LOCKED 동시성은 MySQL 전용 — E2E 이월 (Design §6).
여기서는 상태 전환·쿼리 조립·전이 가드를 검증한다.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.background_job.entity import BackgroundJob
from src.infrastructure.background_job.job_repository import (
    BackgroundJobRepository,
    _to_entity,
)
from src.infrastructure.background_job.models import AgentBackgroundJobModel

_NOW = datetime(2026, 8, 11, 3, 0)


@pytest.fixture
def mock_session():
    s = AsyncMock()
    s.add = MagicMock()  # add 는 sync 메서드
    return s


@pytest.fixture
def mock_logger():
    return MagicMock()


def _model(**overrides) -> AgentBackgroundJobModel:
    base = dict(
        id="j1",
        user_id="u1",
        agent_id="a1",
        source="chat",
        query="시장 조사해줘",
        session_id=None,
        run_id=None,
        status="queued",
        error_message=None,
        seen_at=None,
        queued_at=datetime(2026, 8, 11, 2, 0),
        started_at=None,
        finished_at=None,
        request_id="req-0",
        created_at=datetime(2026, 8, 11, 2, 0),
        updated_at=datetime(2026, 8, 11, 2, 0),
    )
    base.update(overrides)
    return AgentBackgroundJobModel(**base)


def _entity(**overrides) -> BackgroundJob:
    return _to_entity(_model(**overrides))


def _exec_result(scalars_all=None, scalar_one=None, rowcount=0, first=None, rows=None):
    result = MagicMock()
    result.scalars.return_value.all.return_value = scalars_all or []
    result.scalars.return_value.first.return_value = first
    result.scalar_one.return_value = scalar_one
    result.rowcount = rowcount
    result.all.return_value = rows or []
    return result


class TestToEntity:
    def test_maps_all_fields(self):
        entity = _to_entity(_model(status="failed", error_message="boom"))
        assert entity.id == "j1"
        assert entity.status == "failed"
        assert entity.error_message == "boom"
        assert entity.queued_at == datetime(2026, 8, 11, 2, 0)


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_adds_model_and_flushes(self, mock_session, mock_logger):
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.enqueue(_entity(), "req-1")
        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert isinstance(added, AgentBackgroundJobModel)
        assert added.status == "queued"
        mock_session.flush.assert_awaited_once()


class TestClaimQueued:
    @pytest.mark.asyncio
    async def test_marks_claimed_as_running(self, mock_session, mock_logger):
        m1, m2 = _model(id="j1"), _model(id="j2")
        mock_session.execute = AsyncMock(
            return_value=_exec_result(scalars_all=[m1, m2])
        )
        repo = BackgroundJobRepository(mock_session, mock_logger)
        claimed = await repo.claim_queued(2, _NOW, "req-1")
        assert [j.id for j in claimed] == ["j1", "j2"]
        assert all(j.status == "running" for j in claimed)
        assert m1.status == "running" and m1.started_at == _NOW
        mock_session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_empty_queue_returns_empty(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(return_value=_exec_result())
        repo = BackgroundJobRepository(mock_session, mock_logger)
        assert await repo.claim_queued(5, _NOW, "req-1") == []

    @pytest.mark.asyncio
    async def test_claim_statement_limit_order_skip_locked(
        self, mock_session, mock_logger
    ):
        """D2 쿼리 조립: LIMIT 인자·queued_at 정렬·FOR UPDATE SKIP LOCKED."""
        from sqlalchemy.dialects import mysql

        mock_session.execute = AsyncMock(return_value=_exec_result())
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.claim_queued(2, _NOW, "req-1")
        stmt = mock_session.execute.call_args[0][0]
        compiled = stmt.compile(dialect=mysql.dialect())
        sql = str(compiled)
        assert "FOR UPDATE SKIP LOCKED" in sql
        assert "ORDER BY agent_background_job.queued_at" in sql
        assert "LIMIT" in sql
        assert 2 in compiled.params.values()


class TestFinish:
    @pytest.mark.asyncio
    async def test_running_to_success_records_session(
        self, mock_session, mock_logger
    ):
        model = _model(status="running", started_at=_NOW)
        mock_session.get = AsyncMock(return_value=model)
        repo = BackgroundJobRepository(mock_session, mock_logger)
        ok = await repo.finish(
            "j1", "success", _NOW, "req-1",
            session_id="sess-1", run_id="run-1",
        )
        assert ok is True
        assert model.status == "success"
        assert model.session_id == "sess-1"
        assert model.run_id == "run-1"
        assert model.finished_at == _NOW

    @pytest.mark.asyncio
    async def test_finished_job_transition_denied_no_change(
        self, mock_session, mock_logger
    ):
        model = _model(status="success", session_id="sess-1")
        mock_session.get = AsyncMock(return_value=model)
        repo = BackgroundJobRepository(mock_session, mock_logger)
        ok = await repo.finish("j1", "failed", _NOW, "req-1", error_message="x")
        assert ok is False
        assert model.status == "success"  # 무변경 (D7 경합 방어)
        assert model.session_id == "sess-1"

    @pytest.mark.asyncio
    async def test_missing_job_raises(self, mock_session, mock_logger):
        mock_session.get = AsyncMock(return_value=None)
        repo = BackgroundJobRepository(mock_session, mock_logger)
        with pytest.raises(ValueError):
            await repo.finish("nope", "success", _NOW, "req-1")

    @pytest.mark.asyncio
    async def test_error_message_truncated(self, mock_session, mock_logger):
        model = _model(status="running")
        mock_session.get = AsyncMock(return_value=model)
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.finish(
            "j1", "failed", _NOW, "req-1", error_message="x" * 5000
        )
        assert len(model.error_message) == 2000


class TestReconcile:
    @pytest.mark.asyncio
    async def test_returns_updated_count(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(return_value=_exec_result(rowcount=3))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        count = await repo.reconcile_orphan_running("서버 재시작", _NOW, "req-1")
        assert count == 3

    @pytest.mark.asyncio
    async def test_zero_orphans(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(return_value=_exec_result(rowcount=0))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        assert await repo.reconcile_orphan_running("x", _NOW, "req-1") == 0


class TestFindActiveBySession:
    @pytest.mark.asyncio
    async def test_returns_entity_when_active_exists(
        self, mock_session, mock_logger
    ):
        mock_session.execute = AsyncMock(
            return_value=_exec_result(first=_model(session_id="sess-1"))
        )
        repo = BackgroundJobRepository(mock_session, mock_logger)
        found = await repo.find_active_by_session("sess-1", "req-1")
        assert found is not None and found.id == "j1"

    @pytest.mark.asyncio
    async def test_returns_none_when_absent(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(return_value=_exec_result(first=None))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        assert await repo.find_active_by_session("sess-1", "req-1") is None


class TestListByUser:
    @pytest.mark.asyncio
    async def test_returns_job_with_agent_name(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(
            return_value=_exec_result(rows=[(_model(), "리서치 봇")])
        )
        repo = BackgroundJobRepository(mock_session, mock_logger)
        rows = await repo.list_by_user("u1", None, 20, 0, "req-1")
        assert len(rows) == 1
        job, agent_name = rows[0]
        assert job.id == "j1"
        assert agent_name == "리서치 봇"

    @pytest.mark.asyncio
    async def test_statement_joins_agent_and_filters(
        self, mock_session, mock_logger
    ):
        mock_session.execute = AsyncMock(return_value=_exec_result())
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.list_by_user("u1", "success", 20, 0, "req-1")
        sql = str(mock_session.execute.call_args[0][0])
        assert "LEFT OUTER JOIN agent_definition" in sql
        assert "agent_background_job.user_id" in sql
        assert "agent_background_job.status" in sql


class TestSeen:
    @pytest.mark.asyncio
    async def test_count_unseen(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(
            return_value=_exec_result(scalar_one=2)
        )
        repo = BackgroundJobRepository(mock_session, mock_logger)
        assert await repo.count_unseen("u1", "req-1") == 2

    @pytest.mark.asyncio
    async def test_mark_seen_owned_true(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(return_value=_exec_result(rowcount=1))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        assert await repo.mark_seen("j1", "u1", _NOW, "req-1") is True

    @pytest.mark.asyncio
    async def test_mark_seen_not_owned_false(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(return_value=_exec_result(rowcount=0))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        assert await repo.mark_seen("j1", "other", _NOW, "req-1") is False

    @pytest.mark.asyncio
    async def test_mark_all_seen_returns_count(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(return_value=_exec_result(rowcount=4))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        assert await repo.mark_all_seen("u1", _NOW, "req-1") == 4
