"""RunAgentUseCase 대화 메시지 turn_index 유일성 — agent-run-turn-index-fix Design §6.1 (T1~T6).

Plan FR-01/FR-02: session_factory 주입 시 user·assistant 저장이 모두 별도 세션에서
최신 commit 기준 len+1 을 계산한다 → user N, assistant N+1.
Plan FR-04: 미주입(legacy)이면 요청 세션(self._message_repo) 경로 그대로.
Plan FR-07: charts·analysis_data 메타 보존.

가짜 session_factory: 호출마다 새 세션 객체를 주되 저장소(list)는 공유해
세션 A 의 commit 이 세션 B 의 조회에 보이는 실제 DB 동작을 흉내 낸다.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.domain.conversation.entities import ConversationMessage, MessageId
from src.domain.conversation.value_objects import MessageRole

_REPO = "src.application.agent_builder.run_agent_use_case.SQLAlchemyConversationMessageRepository"


class _Store:
    """commit 된 행의 공유 저장소 (세션 간 가시성 시뮬레이션)."""

    def __init__(self, seed: list[ConversationMessage] | None = None) -> None:
        self.rows: list[ConversationMessage] = list(seed or [])
        self.begin_count = 0
        self.save_count = 0
        self.in_begin = False
        # Analysis G2: save 시점에 begin() 컨텍스트 안이었는지 기록
        self.saved_inside_begin: list[bool] = []


class _FakeRepo:
    def __init__(self, session) -> None:
        self._store: _Store = session.store

    async def find_by_session(self, user_id, session_id):
        return [
            m for m in self._store.rows
            if m.user_id == user_id and m.session_id == session_id
        ]

    async def save(self, message: ConversationMessage) -> ConversationMessage:
        self._store.save_count += 1
        self._store.saved_inside_begin.append(self._store.in_begin)
        saved = ConversationMessage(
            **{**message.__dict__, "id": MessageId(len(self._store.rows) + 1)}
        )
        self._store.rows.append(saved)
        return saved


def _session_factory(store: _Store):
    class _Session:
        def __init__(self) -> None:
            self.store = store

        @asynccontextmanager
        async def begin(self):
            store.begin_count += 1
            store.in_begin = True
            try:
                yield
            finally:
                store.in_begin = False

    @asynccontextmanager
    async def factory():
        yield _Session()

    return factory


def _uc(store: _Store | None, legacy_repo=None) -> RunAgentUseCase:
    uc = RunAgentUseCase.__new__(RunAgentUseCase)
    uc._tool_access_resolver = None  # tool-access-control: optional 의존성 (None=필터 없음)
    uc._logger = MagicMock()
    uc._session_factory = _session_factory(store) if store is not None else None
    uc._message_repo = legacy_repo or MagicMock()
    return uc


def _row(turn: int, role: MessageRole) -> ConversationMessage:
    from datetime import datetime, timezone

    from src.domain.conversation.entities import AgentId
    from src.domain.conversation.value_objects import SessionId, TurnIndex, UserId

    return ConversationMessage(
        id=MessageId(turn), user_id=UserId("u-7"), session_id=SessionId("s-1"),
        agent_id=AgentId("ag1"), role=role, content=f"{role.value}-{turn}",
        turn_index=TurnIndex(turn), created_at=datetime.now(timezone.utc),
    )


def _turns(store: _Store) -> list[tuple[str, int]]:
    return [(m.role.value, m.turn_index.value) for m in store.rows]


class TestSeparateSessionPath:
    @pytest.mark.asyncio
    async def test_T1_빈_세션에서_user_1_assistant_2(self):
        store = _Store()
        uc = _uc(store)
        with patch(_REPO, _FakeRepo):
            mid = await uc._save_user_message("q", "u-7", "s-1", "ag1")
            await uc._save_assistant_message("a", "u-7", "s-1", "ag1")
        assert mid == 1
        assert _turns(store) == [("user", 1), ("assistant", 2)]

    @pytest.mark.asyncio
    async def test_T2_기존_2턴_뒤에는_5_6(self):
        seed = [_row(1, MessageRole.USER), _row(2, MessageRole.ASSISTANT),
                _row(3, MessageRole.USER), _row(4, MessageRole.ASSISTANT)]
        store = _Store(seed)
        uc = _uc(store)
        with patch(_REPO, _FakeRepo):
            await uc._save_user_message("q", "u-7", "s-1", "ag1")
            await uc._save_assistant_message("a", "u-7", "s-1", "ag1")
        assert _turns(store)[-2:] == [("user", 5), ("assistant", 6)]

    @pytest.mark.asyncio
    async def test_T3_assistant_저장은_begin_컨텍스트_안에서_1회(self):
        store = _Store()
        uc = _uc(store)
        with patch(_REPO, _FakeRepo):
            await uc._save_assistant_message("a", "u-7", "s-1", "ag1")
        assert store.begin_count == 1
        assert store.save_count == 1
        assert store.saved_inside_begin == [True]  # Analysis G2: save 는 begin 안에서
        assert _turns(store) == [("assistant", 1)]

    @pytest.mark.asyncio
    async def test_T4_persist_False면_조회_저장_0회(self):
        store = _Store()
        uc = _uc(store)
        with patch(_REPO, _FakeRepo):
            mid = await uc._save_user_message("q", "u-7", "s-1", "ag1", persist=False)
            await uc._save_assistant_message("a", "u-7", "s-1", "ag1", persist=False)
        assert mid is None
        assert store.begin_count == 0 and store.save_count == 0

    @pytest.mark.asyncio
    async def test_T6_charts_analysis_data_보존(self):
        store = _Store()
        uc = _uc(store)
        with patch(_REPO, _FakeRepo):
            await uc._save_assistant_message(
                "a", "u-7", "s-1", "ag1",
                charts=[{"type": "bar"}], analysis_data={"items": [{"rows": 3}]},
            )
        saved = store.rows[-1]
        assert saved.charts == [{"type": "bar"}]
        assert saved.analysis_data == {"items": [{"rows": 3}]}
        assert saved.role is MessageRole.ASSISTANT


class TestResumePath:
    """Analysis G1 / Plan §5: 승인 재개(_save_resumed_answer → _save_assistant_message)도
    session_factory 주입 시 같은 별도 세션 헬퍼를 타 N+1 을 받는다."""

    @pytest.mark.asyncio
    async def test_T8_승인_재개_답변은_별도_세션에서_user_다음_turn(self):
        from tests.application.approval.test_resume import _NOW, _approval

        store = _Store([_row(1, MessageRole.USER)])
        uc = _uc(store)
        agent = MagicMock(id="ag1", updated_at=_NOW, max_iterations=25)
        agent.to_workflow_definition.return_value = MagicMock(workers=[])
        uc._repository = MagicMock()
        uc._repository.find_by_id = AsyncMock(return_value=agent)

        async def _fake_resume(state, agent_, request_id, **kwargs):
            return "재개 답변"

        uc._resume_graph = _fake_resume
        with patch(_REPO, _FakeRepo):
            answer = await uc.resume_from_snapshot(
                _approval(session_id="s-1", requested_by="u-7"),
                outcome="완료", request_id="req1",
            )
        assert answer == "재개 답변"
        assert _turns(store) == [("user", 1), ("assistant", 2)]
        assert store.saved_inside_begin == [True]


class TestLegacyPath:
    @pytest.mark.asyncio
    async def test_T5_session_factory_없으면_요청_세션_repo_경로(self):
        legacy = MagicMock()
        legacy.find_by_session = AsyncMock(return_value=[_row(1, MessageRole.USER)])
        saved = _row(2, MessageRole.ASSISTANT)
        legacy.save = AsyncMock(return_value=saved)
        uc = _uc(None, legacy_repo=legacy)
        with patch(_REPO) as repo_cls:
            await uc._save_assistant_message("a", "u-7", "s-1", "ag1")
        repo_cls.assert_not_called()
        legacy.find_by_session.assert_awaited_once()
        assert legacy.save.call_args.args[0].turn_index.value == 2
