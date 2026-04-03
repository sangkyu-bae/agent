"""AutoBuildSessionRepository: Redis 기반 세션 저장소."""
import json
from datetime import datetime

from src.domain.auto_agent_builder.interfaces import AutoBuildSessionRepositoryInterface
from src.domain.auto_agent_builder.policies import AutoAgentBuilderPolicy
from src.domain.auto_agent_builder.schemas import AutoBuildSession, ConversationTurn
from src.domain.redis.interfaces import RedisRepositoryInterface


class AutoBuildSessionRepository(AutoBuildSessionRepositoryInterface):

    _KEY_PREFIX = "auto_build_session:"

    def __init__(self, redis: RedisRepositoryInterface) -> None:
        self._redis = redis

    def _key(self, session_id: str) -> str:
        return f"{self._KEY_PREFIX}{session_id}"

    async def save(self, session: AutoBuildSession) -> None:
        key = self._key(session.session_id)
        value = json.dumps(self._to_dict(session))
        await self._redis.set(key, value, ttl=AutoAgentBuilderPolicy.SESSION_TTL_SECONDS)

    async def find(self, session_id: str) -> AutoBuildSession | None:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        return self._from_dict(json.loads(raw))

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    @staticmethod
    def _to_dict(session: AutoBuildSession) -> dict:
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "user_request": session.user_request,
            "model_name": session.model_name,
            "conversation_turns": [
                {"questions": t.questions, "answers": t.answers}
                for t in session.conversation_turns
            ],
            "attempt_count": session.attempt_count,
            "status": session.status,
            "created_agent_id": session.created_agent_id,
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
        }

    @staticmethod
    def _from_dict(data: dict) -> AutoBuildSession:
        session = AutoBuildSession(
            session_id=data["session_id"],
            user_id=data["user_id"],
            user_request=data["user_request"],
            model_name=data["model_name"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )
        session.conversation_turns = [
            ConversationTurn(questions=t["questions"], answers=t["answers"])
            for t in data.get("conversation_turns", [])
        ]
        session.attempt_count = data.get("attempt_count", 0)
        session.status = data.get("status", "pending")
        session.created_agent_id = data.get("created_agent_id")
        return session
