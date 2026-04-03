"""AutoBuildSessionRepository Redis CRUD 테스트."""
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.domain.auto_agent_builder.schemas import AutoBuildSession, ConversationTurn
from src.infrastructure.auto_agent_builder.auto_build_session_repository import (
    AutoBuildSessionRepository,
)


def _make_session(session_id: str = "sess-1") -> AutoBuildSession:
    now = datetime(2026, 3, 24, 12, 0, 0)
    s = AutoBuildSession(
        session_id=session_id,
        user_id="user-1",
        user_request="에이전트 만들어줘",
        model_name="gpt-4o",
        created_at=now,
        expires_at=now + timedelta(hours=24),
    )
    s.conversation_turns = [
        ConversationTurn(questions=["PII?"], answers=["네"])
    ]
    s.attempt_count = 1
    return s


class TestSave:

    @pytest.mark.asyncio
    async def test_save_calls_redis_set_with_ttl(self):
        redis = AsyncMock()
        redis.set = AsyncMock()
        repo = AutoBuildSessionRepository(redis)
        session = _make_session()

        await repo.save(session)

        redis.set.assert_awaited_once()
        call_kwargs = redis.set.call_args
        key = call_kwargs[0][0]
        assert "sess-1" in key
        assert call_kwargs[1]["ttl"] == 86400

    @pytest.mark.asyncio
    async def test_save_serializes_conversation_turns(self):
        redis = AsyncMock()
        redis.set = AsyncMock()
        repo = AutoBuildSessionRepository(redis)
        session = _make_session()

        await repo.save(session)

        stored_value = redis.set.call_args[0][1]
        data = json.loads(stored_value)
        assert len(data["conversation_turns"]) == 1
        assert data["conversation_turns"][0]["questions"] == ["PII?"]
        assert data["conversation_turns"][0]["answers"] == ["네"]


class TestFind:

    @pytest.mark.asyncio
    async def test_find_returns_session_when_exists(self):
        session = _make_session()
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(
            AutoBuildSessionRepository._to_dict(session)
        ))
        repo = AutoBuildSessionRepository(redis)

        result = await repo.find("sess-1")

        assert result is not None
        assert result.session_id == "sess-1"
        assert result.user_id == "user-1"
        assert len(result.conversation_turns) == 1
        assert result.conversation_turns[0].questions == ["PII?"]

    @pytest.mark.asyncio
    async def test_find_returns_none_when_missing(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        repo = AutoBuildSessionRepository(redis)

        result = await repo.find("no-such-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_find_restores_status_and_agent_id(self):
        session = _make_session()
        session.status = "created"
        session.created_agent_id = "agent-uuid"

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(
            AutoBuildSessionRepository._to_dict(session)
        ))
        repo = AutoBuildSessionRepository(redis)

        result = await repo.find("sess-1")

        assert result.status == "created"
        assert result.created_agent_id == "agent-uuid"


class TestDelete:

    @pytest.mark.asyncio
    async def test_delete_calls_redis_delete(self):
        redis = AsyncMock()
        redis.delete = AsyncMock()
        repo = AutoBuildSessionRepository(redis)

        await repo.delete("sess-1")

        redis.delete.assert_awaited_once()
        key = redis.delete.call_args[0][0]
        assert "sess-1" in key


class TestToDomainRoundtrip:

    def test_to_dict_and_from_dict_roundtrip(self):
        session = _make_session()
        session.attempt_count = 2
        session.status = "pending"

        data = AutoBuildSessionRepository._to_dict(session)
        restored = AutoBuildSessionRepository._from_dict(data)

        assert restored.session_id == session.session_id
        assert restored.user_request == session.user_request
        assert restored.attempt_count == 2
        assert restored.status == "pending"
        assert len(restored.conversation_turns) == 1
        assert restored.conversation_turns[0].questions == ["PII?"]
        assert restored.conversation_turns[0].answers == ["네"]
