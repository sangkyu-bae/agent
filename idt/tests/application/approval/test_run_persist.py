"""RunAgentUseCase 의 승인 요청 적재 단위 테스트.

Design Ref: §2.1 ④, §3.1(v0.2 스냅샷 시점).
그래프를 돌리지 않고 `_persist_approval_if_pending` 를 직접 검증한다 —
런 전체를 띄우면 LLM·DB 배선이 필요해 게이트 적재 자체가 흐려진다.
"""
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.run_agent_use_case import (
    RunAgentUseCase,
    _StreamState,
)
from src.infrastructure.approval.snapshot import SnapshotSerializer

_AGENT_UPDATED = datetime(2026, 9, 21, 8, 0, 0)


def _pending(**over) -> dict:
    base = {
        "tool_id": "email_send",
        "tool_args": {"to": "a@b.c"},
        "draft": "본문입니다",
        "tool_call_id": "tc1",
        "worker_id": "w1",
    }
    base.update(over)
    return base


def _session_factory():
    session = MagicMock()

    @asynccontextmanager
    async def _begin():
        yield session

    session.begin = _begin

    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


def _uc(*, repo_factory_set=True):
    created: list = []
    repo = MagicMock()

    async def _create(approval, request_id):
        created.append(approval)

    repo.create = _create

    uc = RunAgentUseCase.__new__(RunAgentUseCase)
    uc._logger = MagicMock()
    uc._session_factory = _session_factory()
    uc._approval_repo_factory = (lambda session: repo) if repo_factory_set else None
    uc._approval_gate_config = {"expires_hours": 24}
    return uc, created


def _args(*, pending=None, final_state=None, session_id="sess-1"):
    state = _StreamState()
    state.approval_pending = pending if pending is not None else _pending()
    state.final_state = final_state if final_state is not None else {
        "messages": [], "iteration_count": 3, "worker_task": "메일 발송",
    }
    agent = MagicMock(id="ag1", updated_at=_AGENT_UPDATED)
    run_id = MagicMock(value="run-1")
    request = MagicMock(user_id="u1")
    return dict(
        agent=agent, state=state, run_id=run_id,
        request=request, request_id="req1", session_id=session_id,
    )


class TestNoOpPaths:
    @pytest.mark.asyncio
    async def test_신호가_없으면_적재하지_않는다(self):
        """게이트 미적용 런은 완전 무회귀여야 한다."""
        uc, created = _uc()
        kwargs = _args(pending={})
        assert await uc._persist_approval_if_pending(**kwargs) is None
        assert created == []

    @pytest.mark.asyncio
    async def test_리포지토리_미배선이면_경고_후_건너뛴다(self):
        uc, created = _uc(repo_factory_set=False)
        assert await uc._persist_approval_if_pending(**_args()) is None
        assert created == []
        assert uc._logger.warning.called


class TestPersist:
    @pytest.mark.asyncio
    async def test_승인_요청이_적재된다(self):
        uc, created = _uc()
        approval_id = await uc._persist_approval_if_pending(**_args())
        assert len(created) == 1
        assert created[0].id == approval_id

    @pytest.mark.asyncio
    async def test_신호_내용이_그대로_담긴다(self):
        uc, created = _uc()
        await uc._persist_approval_if_pending(**_args())
        a = created[0]
        assert a.tool_id == "email_send"
        assert a.tool_args == {"to": "a@b.c"}
        assert a.draft == "본문입니다"
        assert a.worker_id == "w1"
        assert a.status == "pending"

    @pytest.mark.asyncio
    async def test_멱등키가_run_worker_toolcall로_조립된다(self):
        uc, created = _uc()
        await uc._persist_approval_if_pending(**_args())
        assert created[0].idempotency_key == "run-1:w1:tc1"

    @pytest.mark.asyncio
    async def test_요청자는_런_실행_신원이다(self):
        uc, created = _uc()
        await uc._persist_approval_if_pending(**_args())
        assert created[0].requested_by == "u1"

    @pytest.mark.asyncio
    async def test_만료가_게이트_설정을_따른다(self):
        """config expires_hours=24 → 24시간 뒤."""
        uc, created = _uc()
        await uc._persist_approval_if_pending(**_args())
        delta = created[0].expires_at - created[0].created_at
        assert round(delta.total_seconds() / 3600) == 24


class TestSessionPreserved:
    @pytest.mark.asyncio
    async def test_원래_세션이_보존된다(self):
        """Check G1 — 재개 답변을 원래 대화로 되돌리려면 세션이 필요하다."""
        uc, created = _uc()
        await uc._persist_approval_if_pending(**_args(session_id="sess-42"))
        assert created[0].session_id == "sess-42"


class TestSnapshot:
    @pytest.mark.asyncio
    async def test_최종_상태가_스냅샷된다(self):
        """v0.2 정제 — 워커 진입 시점이 아니라 런 최종 상태."""
        uc, created = _uc()
        await uc._persist_approval_if_pending(**_args())
        restored = SnapshotSerializer.loads(created[0].snapshot.state_json)
        assert restored["iteration_count"] == 3
        assert restored["worker_task"] == "메일 발송"

    @pytest.mark.asyncio
    async def test_에이전트_수정시각이_스냅샷에_기록된다(self):
        """FR-14 — 재개 전 대조 기준."""
        uc, created = _uc()
        await uc._persist_approval_if_pending(**_args())
        assert created[0].snapshot.agent_updated_at == _AGENT_UPDATED

    @pytest.mark.asyncio
    async def test_스키마_버전이_기록된다(self):
        uc, created = _uc()
        await uc._persist_approval_if_pending(**_args())
        assert created[0].snapshot.schema_version == SnapshotSerializer.SCHEMA_VERSION

    @pytest.mark.asyncio
    async def test_거대_상태는_절단되고_경고된다(self):
        from langchain_core.messages import HumanMessage

        uc, _ = _uc()
        huge = {"messages": [HumanMessage(content="가" * 40_000) for _ in range(10)]}
        await uc._persist_approval_if_pending(**_args(final_state=huge))
        assert uc._logger.warning.called

    @pytest.mark.asyncio
    async def test_최종_상태가_비면_messages로_폴백한다(self):
        uc, created = _uc()
        kwargs = _args(final_state={})
        kwargs["state"].final_messages = []
        await uc._persist_approval_if_pending(**kwargs)
        assert SnapshotSerializer.loads(created[0].snapshot.state_json)["messages"] == []


class TestGateConfigResolution:
    """Check G4 — 만료는 해당 에이전트의 게이트 설정을 따라야 한다.

    이전에는 생성자 상수(_approval_gate_config)를 읽었는데 main.py 가 이 값을
    넘기지 않아 항상 168h 였고, 에이전트별로 달라질 수도 없었다.
    """

    @pytest.mark.asyncio
    async def test_리졸버가_준_expires_hours를_쓴다(self):
        uc, created = _uc()
        uc._approval_gate_config = None
        seen = {}

        async def _resolver(session, agent_id, request_id):
            seen["agent_id"] = agent_id
            seen["session"] = session
            return {"expires_hours": 6}

        uc._approval_gate_config_resolver = _resolver
        await uc._persist_approval_if_pending(**_args())
        delta = created[0].expires_at - created[0].created_at
        assert round(delta.total_seconds() / 3600) == 6
        assert seen["agent_id"] == "ag1"

    @pytest.mark.asyncio
    async def test_리졸버는_적재와_같은_세션을_쓴다(self):
        """한 UseCase 안에서 저장소마다 다른 세션을 쓰지 않는다 (CLAUDE.md)."""
        uc, _ = _uc()
        sessions = []

        async def _resolver(session, agent_id, request_id):
            sessions.append(session)
            return {}

        captured_repo_sessions = []
        original = uc._approval_repo_factory

        def _factory(session):
            captured_repo_sessions.append(session)
            return original(session)

        uc._approval_repo_factory = _factory
        uc._approval_gate_config_resolver = _resolver
        await uc._persist_approval_if_pending(**_args())
        assert sessions[0] is captured_repo_sessions[0]

    @pytest.mark.asyncio
    async def test_리졸버_미주입이면_생성자_설정으로_폴백(self):
        uc, created = _uc()  # _approval_gate_config = {"expires_hours": 24}
        uc._approval_gate_config_resolver = None
        await uc._persist_approval_if_pending(**_args())
        delta = created[0].expires_at - created[0].created_at
        assert round(delta.total_seconds() / 3600) == 24

    @pytest.mark.asyncio
    async def test_둘_다_없으면_도메인_기본값(self):
        uc, created = _uc()
        uc._approval_gate_config = None
        uc._approval_gate_config_resolver = None
        await uc._persist_approval_if_pending(**_args())
        delta = created[0].expires_at - created[0].created_at
        assert round(delta.total_seconds() / 3600) == 168
