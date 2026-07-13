"""ConversationMessageMapper analysis_data 왕복 테스트 (analysis-data-continuity T3)."""
from datetime import datetime

from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.value_objects import (
    AgentId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)
from src.infrastructure.persistence.mappers.conversation_mapper import (
    ConversationMessageMapper,
)

_SNAPSHOT = {
    "version": 1,
    "question": "나의 휴가데이터",
    "items": [
        {"origin": "w1", "kind": "search", "content": "휴가 15일", "truncated": False}
    ],
}


def _entity(analysis_data: dict | None) -> ConversationMessage:
    return ConversationMessage(
        id=None,
        user_id=UserId("u1"),
        session_id=SessionId("s1"),
        agent_id=AgentId.super(),
        role=MessageRole.ASSISTANT,
        content="답변",
        turn_index=TurnIndex(2),
        created_at=datetime(2026, 7, 6),
        analysis_data=analysis_data,
    )


class TestAnalysisDataRoundtrip:
    def test_스냅샷_왕복_보존(self):
        model = ConversationMessageMapper.to_model(_entity(_SNAPSHOT))
        assert model.analysis_data == _SNAPSHOT
        model.id = 1
        restored = ConversationMessageMapper.to_entity(model)
        assert restored.analysis_data == _SNAPSHOT

    def test_None_왕복_보존(self):
        model = ConversationMessageMapper.to_model(_entity(None))
        assert model.analysis_data is None
        model.id = 1
        restored = ConversationMessageMapper.to_entity(model)
        assert restored.analysis_data is None
