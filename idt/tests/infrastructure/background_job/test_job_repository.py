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


class TestSoftDeleteFilterCoverage:
    """Design §10.2 전수 점검 — 조회·집계 쿼리에 deleted_at 필터가 빠지면
    삭제한 작업이 목록·벨 배지에 되살아난다. SQL 문자열로 직접 검증한다."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "call",
        [
            lambda r: r.find_by_id("j1", "req-1"),
            lambda r: r.find_active_by_session("sess-1", "req-1"),
            lambda r: r.count_unseen("u1", "req-1"),
            lambda r: r.mark_seen("j1", "u1", _NOW, "req-1"),
            lambda r: r.mark_all_seen("u1", _NOW, "req-1"),
            lambda r: r.soft_delete("j1", "u1", _NOW, "req-1"),
            lambda r: r.soft_delete_completed("u1", _NOW, "req-1"),
        ],
    )
    async def test_query_filters_deleted_rows(
        self, mock_session, mock_logger, call
    ):
        mock_session.execute = AsyncMock(
            return_value=_exec_result(scalar_one=0, rowcount=0, first=None)
        )
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await call(repo)
        sql = str(mock_session.execute.call_args[0][0])
        assert "agent_background_job.deleted_at IS NULL" in sql

    @pytest.mark.asyncio
    @pytest.mark.parametrize("history_type", ["all", "manual"])
    async def test_history_filters_deleted_rows(
        self, mock_session, mock_logger, history_type
    ):
        mock_session.execute = AsyncMock(return_value=_exec_result())
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.list_history(
            "u1",
            status_group="all",
            history_type=history_type,
            since_utc=None,
            limit=20,
            offset=0,
            request_id="req-1",
        )
        sql = str(mock_session.execute.call_args[0][0])
        assert "agent_background_job.deleted_at IS NULL" in sql


class TestSoftDelete:
    @pytest.mark.asyncio
    async def test_returns_true_when_row_updated(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(return_value=_exec_result(rowcount=1))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        assert await repo.soft_delete("j1", "u1", _NOW, "req-1") is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_owned(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(return_value=_exec_result(rowcount=0))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        assert await repo.soft_delete("j1", "other", _NOW, "req-1") is False

    @pytest.mark.asyncio
    async def test_sets_deleted_at_not_physical_delete(
        self, mock_session, mock_logger
    ):
        mock_session.execute = AsyncMock(return_value=_exec_result(rowcount=1))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.soft_delete("j1", "u1", _NOW, "req-1")
        sql = str(mock_session.execute.call_args[0][0])
        assert sql.startswith("UPDATE agent_background_job")
        assert "deleted_at" in sql

    @pytest.mark.asyncio
    async def test_where_excludes_active_jobs(self, mock_session, mock_logger):
        """TOCTOU 방어 — UseCase 검사 이후 워커가 claim 해도 지워지면 안 된다."""
        mock_session.execute = AsyncMock(return_value=_exec_result(rowcount=0))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.soft_delete("j1", "u1", _NOW, "req-1")
        compiled = mock_session.execute.call_args[0][0].compile()
        assert "agent_background_job.status IN" in str(compiled)
        assert ["success", "failed"] in compiled.params.values()

    @pytest.mark.asyncio
    async def test_cleanup_targets_finished_only(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(return_value=_exec_result(rowcount=3))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        count = await repo.soft_delete_completed("u1", _NOW, "req-1")
        assert count == 3
        sql = str(mock_session.execute.call_args[0][0])
        assert "agent_background_job.status IN" in sql


class TestListHistory:
    @pytest.mark.asyncio
    async def test_union_includes_both_sources(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(return_value=_exec_result())
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.list_history(
            "u1",
            status_group="all",
            history_type="all",
            since_utc=None,
            limit=20,
            offset=0,
            request_id="req-1",
        )
        sql = str(mock_session.execute.call_args[0][0])
        assert "UNION ALL" in sql
        assert "agent_schedule_run" in sql
        assert "agent_background_job" in sql

    @pytest.mark.asyncio
    async def test_schedule_only_skips_union(self, mock_session, mock_logger):
        """유형이 단일값이면 UNION 없이 해당 테이블만 조회한다 (Design §4.3)."""
        mock_session.execute = AsyncMock(return_value=_exec_result())
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.list_history(
            "u1",
            status_group="all",
            history_type="schedule",
            since_utc=None,
            limit=20,
            offset=0,
            request_id="req-1",
        )
        sql = str(mock_session.execute.call_args[0][0])
        assert "UNION ALL" not in sql
        assert "agent_background_job" not in sql
        # 소유자는 agent_schedule 경유로만 판정한다
        assert "agent_schedule.user_id" in sql

    @pytest.mark.asyncio
    async def test_orders_by_occurred_at_then_id(self, mock_session, mock_logger):
        """보조 키(id) 없이는 동시각 항목이 페이지 경계에서 흔들린다."""
        mock_session.execute = AsyncMock(return_value=_exec_result())
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.list_history(
            "u1",
            status_group="all",
            history_type="all",
            since_utc=None,
            limit=20,
            offset=0,
            request_id="req-1",
        )
        sql = str(mock_session.execute.call_args[0][0])
        order = sql[sql.index("ORDER BY"):]
        assert "occurred_at DESC" in order
        assert "id ASC" in order

    @pytest.mark.asyncio
    async def test_status_group_expands_to_statuses(
        self, mock_session, mock_logger
    ):
        mock_session.execute = AsyncMock(return_value=_exec_result())
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.list_history(
            "u1",
            status_group="running",
            history_type="manual",
            since_utc=None,
            limit=20,
            offset=0,
            request_id="req-1",
        )
        compiled = mock_session.execute.call_args[0][0].compile()
        assert ["queued", "running"] in compiled.params.values()

    @pytest.mark.asyncio
    async def test_since_filter_uses_each_sources_time_column(
        self, mock_session, mock_logger
    ):
        mock_session.execute = AsyncMock(return_value=_exec_result())
        repo = BackgroundJobRepository(mock_session, mock_logger)
        await repo.list_history(
            "u1",
            status_group="all",
            history_type="all",
            since_utc=_NOW,
            limit=20,
            offset=0,
            request_id="req-1",
        )
        sql = str(mock_session.execute.call_args[0][0])
        assert "agent_background_job.queued_at >=" in sql
        assert "agent_schedule_run.scheduled_for >=" in sql

    @pytest.mark.asyncio
    async def test_maps_rows_to_history_items(self, mock_session, mock_logger):
        row = MagicMock()
        row.id, row.type = "j1", "manual"
        row.occurred_at = _NOW
        row.title, row.status = "시장 조사해줘", "success"
        row.agent_id, row.agent_name = "a1", "리서치 봇"
        row.session_id, row.error_message = "sess-1", None
        row.seen_at = row.started_at = row.finished_at = None
        mock_session.execute = AsyncMock(return_value=_exec_result(rows=[row]))
        repo = BackgroundJobRepository(mock_session, mock_logger)
        items = await repo.list_history(
            "u1",
            status_group="all",
            history_type="all",
            since_utc=None,
            limit=20,
            offset=0,
            request_id="req-1",
        )
        assert len(items) == 1
        assert items[0].title == "시장 조사해줘"
        assert items[0].deletable is True

    @pytest.mark.asyncio
    async def test_count_history_returns_scalar(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock(
            return_value=_exec_result(scalar_one=7)
        )
        repo = BackgroundJobRepository(mock_session, mock_logger)
        total = await repo.count_history(
            "u1",
            status_group="all",
            history_type="all",
            since_utc=None,
            request_id="req-1",
        )
        assert total == 7
        assert "count(*)" in str(mock_session.execute.call_args[0][0])

    @pytest.mark.asyncio
    async def test_unknown_filters_rejected(self, mock_session, mock_logger):
        repo = BackgroundJobRepository(mock_session, mock_logger)
        with pytest.raises(ValueError):
            await repo.list_history(
                "u1",
                status_group="nope",
                history_type="all",
                since_utc=None,
                limit=20,
                offset=0,
                request_id="req-1",
            )
        with pytest.raises(ValueError):
            await repo.list_history(
                "u1",
                status_group="all",
                history_type="nope",
                since_utc=None,
                limit=20,
                offset=0,
                request_id="req-1",
            )
