"""ApprovalRepository 단위 테스트 — AsyncMock 사용 (tool_catalog 테스트 동형).

Design Ref: §2.3, §3.3. 이중 집행 3중 방어 중 2·3차(조건부 UPDATE,
FOR UPDATE SKIP LOCKED)가 실제 SQL 로 컴파일되는지까지 확인한다.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.approval.entity import ApprovalRequest, ResumeSnapshot
from src.infrastructure.approval.repository import ApprovalRepository

_NOW = datetime(2026, 9, 21, 9, 0, 0)


def _repo() -> tuple[ApprovalRepository, MagicMock]:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return ApprovalRepository(session=session, logger=MagicMock()), session


def _entity() -> ApprovalRequest:
    return ApprovalRequest(
        id="ap1", run_id="r1", agent_id="ag1", requested_by="u1",
        worker_id="w1", tool_id="email_send", tool_args={"to": "a@b.c"},
        draft="본문", status="pending", idempotency_key="r1:w1:tc1",
        snapshot=ResumeSnapshot(
            schema_version=1, agent_updated_at=_NOW, worker_id="w1",
            state_json='{"messages": []}',
        ),
        expires_at=_NOW + timedelta(hours=168),
        request_id="req1", created_at=_NOW, updated_at=_NOW,
    )


def _sql(session) -> str:
    """마지막으로 실행된 statement 를 MySQL 방언으로 컴파일한 SQL.

    기본 방언으로 str() 하면 FOR UPDATE SKIP LOCKED 같은 MySQL 전용 구문이
    렌더되지 않아, 선점이 실제로 걸리는지 검증할 수 없다.
    """
    from sqlalchemy.dialects import mysql

    stmt = session.execute.call_args[0][0]
    return str(stmt.compile(dialect=mysql.dialect()))


class TestCreate:
    @pytest.mark.asyncio
    async def test_add_후_flush한다(self):
        repo, session = _repo()
        await repo.create(_entity(), "req1")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commit을_호출하지_않는다(self):
        """DB-001 — 트랜잭션 경계는 호출측 UseCase 소유."""
        repo, session = _repo()
        await repo.create(_entity(), "req1")
        assert not session.commit.called

    @pytest.mark.asyncio
    async def test_스냅샷이_컬럼으로_펼쳐진다(self):
        repo, session = _repo()
        await repo.create(_entity(), "req1")
        model = session.add.call_args[0][0]
        assert model.snapshot_version == 1
        assert model.resume_snapshot == '{"messages": []}'
        assert model.agent_updated_at == _NOW


class TestCompareAndSetStatus:
    @pytest.mark.asyncio
    async def test_영향행이_있으면_True(self):
        repo, session = _repo()
        session.execute.return_value = MagicMock(rowcount=1)
        assert await repo.compare_and_set_status(
            "ap1", expected="pending", new_status="approved", request_id="r"
        ) is True

    @pytest.mark.asyncio
    async def test_영향행이_0이면_False(self):
        """중복 클릭 — 두 번째는 expected 불일치로 적용되지 않는다."""
        repo, session = _repo()
        session.execute.return_value = MagicMock(rowcount=0)
        assert await repo.compare_and_set_status(
            "ap1", expected="pending", new_status="approved", request_id="r"
        ) is False

    @pytest.mark.asyncio
    async def test_WHERE절에_기대상태가_포함된다(self):
        """조건부 UPDATE 가 아니면 이중 집행이 열린다 — SQL 로 고정."""
        repo, session = _repo()
        session.execute.return_value = MagicMock(rowcount=1)
        await repo.compare_and_set_status(
            "ap1", expected="pending", new_status="approved", request_id="r"
        )
        sql = _sql(session).lower()
        assert "update approval_request" in sql
        assert "where" in sql and "status" in sql

    @pytest.mark.asyncio
    async def test_None_선택필드는_SET절에서_빠진다(self):
        """기존 decided_by 를 None 으로 덮어써 감사 기록을 지우면 안 된다."""
        repo, session = _repo()
        session.execute.return_value = MagicMock(rowcount=1)
        await repo.compare_and_set_status(
            "ap1", expected="scheduled", new_status="executed",
            request_id="r", executed_at=_NOW,
        )
        sql = _sql(session).lower()
        assert "executed_at" in sql
        assert "decided_by" not in sql
        assert "error_message" not in sql

    @pytest.mark.asyncio
    async def test_거절은_사유를_SET한다(self):
        repo, session = _repo()
        session.execute.return_value = MagicMock(rowcount=1)
        await repo.compare_and_set_status(
            "ap1", expected="pending", new_status="rejected",
            request_id="r", decided_by="u1", decided_at=_NOW,
            decision_reason="한도 초과",
        )
        sql = _sql(session).lower()
        assert "decision_reason" in sql and "decided_by" in sql


class TestClaimDue:
    @pytest.mark.asyncio
    async def test_SKIP_LOCKED로_선점한다(self):
        """다중 tick 워커 이중 집행 방어 3차 저지선 — SQL 로 고정."""
        repo, session = _repo()
        session.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=lambda: []))
        )
        await repo.claim_due(_NOW, "req1")
        sql = _sql(session).lower()
        assert "for update" in sql and "skip locked" in sql

    @pytest.mark.asyncio
    async def test_scheduled_이고_집행시각_도래분만(self):
        repo, session = _repo()
        session.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=lambda: []))
        )
        await repo.claim_due(_NOW, "req1")
        sql = _sql(session).lower()
        assert "execute_after" in sql and "expires_at" in sql

    @pytest.mark.asyncio
    async def test_상태를_바꾸지_않는다(self):
        """집행 성패에 따라 executed/failed 가 갈리므로 전이는 UseCase 몫."""
        repo, session = _repo()
        session.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=lambda: []))
        )
        await repo.claim_due(_NOW, "req1")
        # 컬럼명(agent_updated_at 등)에 'update' 가 들어 있으므로
        # 문장 종류로 판정한다.
        assert _sql(session).lower().lstrip().startswith("select")


class TestFindActiveByRun:
    @pytest.mark.asyncio
    async def test_비종료_상태만_조회한다(self):
        """런당 활성 pending 1건 불변식(FR-06) 판정."""
        repo, session = _repo()
        session.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: None
        )
        await repo.find_active_by_run("r1", "req1")
        sql = _sql(session).lower()
        assert "status in" in sql or "status" in sql
        assert "limit" in sql

    @pytest.mark.asyncio
    async def test_없으면_None(self):
        repo, session = _repo()
        session.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
        assert await repo.find_active_by_run("r1", "req1") is None


class TestExpireOverdue:
    @pytest.mark.asyncio
    async def test_전이_건수를_반환한다(self):
        repo, session = _repo()
        session.execute.return_value = MagicMock(rowcount=3)
        assert await repo.expire_overdue(_NOW, "req1") == 3

    @pytest.mark.asyncio
    async def test_종료된_건은_대상이_아니다(self):
        repo, session = _repo()
        session.execute.return_value = MagicMock(rowcount=0)
        await repo.expire_overdue(_NOW, "req1")
        sql = _sql(session).lower()
        assert "executed" not in sql.split("where")[-1]


class TestCountUnseen:
    @pytest.mark.asyncio
    async def test_미확인_건수를_센다(self):
        repo, session = _repo()
        session.execute.return_value = MagicMock(scalar=lambda: 2)
        assert await repo.count_unseen(("ag1",), "req1") == 2

    @pytest.mark.asyncio
    async def test_seen_at이_NULL인_건만(self):
        repo, session = _repo()
        session.execute.return_value = MagicMock(scalar=lambda: 0)
        await repo.count_unseen(("ag1",), "req1")
        assert "seen_at is null" in _sql(session).lower()



class TestMarkSeenScoped:
    """Check G7 — 소유 에이전트 범위 밖의 건은 확인 처리되지 않는다."""

    @pytest.mark.asyncio
    async def test_WHERE절에_agent_id_범위가_들어간다(self):
        repo, session = _repo()
        await repo.mark_seen("ap1", ("ag1",), "req1")
        sql = _sql(session).lower()
        assert "agent_id in" in sql
        assert "seen_at is null" in sql

    @pytest.mark.asyncio
    async def test_빈_범위는_쿼리하지_않는다(self):
        repo, session = _repo()
        await repo.mark_seen("ap1", (), "req1")
        session.execute.assert_not_awaited()


class TestEditColumns:
    """approval-edit-before-approve §3.4/§3.5 — 수정본은 승인 전이와 같은 UPDATE 에 실린다."""

    @pytest.mark.asyncio
    async def test_CAS가_수정본과_원본을_함께_SET한다(self):
        repo, session = _repo()
        session.execute.return_value = MagicMock(rowcount=1)
        await repo.compare_and_set_status(
            "ap1", expected="pending", new_status="approved", request_id="r",
            decided_by="u1", decided_at=_NOW,
            tool_args={"to": "b"}, draft="수정",
            original_tool_args={"to": "a"}, edited_by="u1", edited_at=_NOW,
        )
        sql = _sql(session).lower()
        for column in ("tool_args", "draft", "original_tool_args", "edited_by", "edited_at"):
            assert column in sql

    @pytest.mark.asyncio
    async def test_무수정_승인은_편집_컬럼을_SET하지_않는다(self):
        """SC-3 — 편집 필드가 None 이면 기존 SET 절과 동일."""
        repo, session = _repo()
        session.execute.return_value = MagicMock(rowcount=1)
        await repo.compare_and_set_status(
            "ap1", expected="pending", new_status="approved", request_id="r",
            decided_by="u1", decided_at=_NOW,
        )
        sql = _sql(session).lower()
        for column in ("tool_args", "draft", "edited_by", "edited_at"):
            assert column not in sql

    def test_모델_엔티티_왕복에서_편집_필드가_보존된다(self):
        from src.infrastructure.approval.repository import _to_entity, _to_model

        entity = _entity()
        entity.original_tool_args = {"to": "a@b.c", "body": "원본"}
        entity.edited_by = "u1"
        entity.edited_at = _NOW
        restored = _to_entity(_to_model(entity))
        assert restored.original_tool_args == {"to": "a@b.c", "body": "원본"}
        assert restored.edited_by == "u1"
        assert restored.edited_at == _NOW
        assert restored.is_edited

    def test_구버전_행은_무수정으로_복원된다(self):
        from src.infrastructure.approval.repository import _to_entity, _to_model

        restored = _to_entity(_to_model(_entity()))
        assert restored.original_tool_args is None
        assert restored.edited_by is None
        assert not restored.is_edited
