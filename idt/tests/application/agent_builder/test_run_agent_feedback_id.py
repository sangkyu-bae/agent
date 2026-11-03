"""agent-run-feedback-wiring Design §4.3 / §8.2 #1~#5, #9~#11.

- _answer_payload: ANSWER_COMPLETED payload 단일 생성 지점 (D-02)
- _save_assistant_message: 저장 id 반환, persist=False → None
- execute(): RunAgentResponse.assistant_message_id
"""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest, RunAgentResponse
from src.domain.agent_run.value_objects import AgentRunEvent, AgentRunEventType


def _uc() -> RunAgentUseCase:
    uc = RunAgentUseCase.__new__(RunAgentUseCase)
    uc._logger = MagicMock()
    uc._session_factory = None
    uc._message_repo = MagicMock()
    return uc


class TestAnswerPayload:
    def test_includes_message_id_when_present(self) -> None:
        out = RunAgentUseCase._answer_payload("답", ["w1"], 42)
        assert out == {"answer": "답", "tools_used": ["w1"], "assistant_message_id": 42}

    def test_omits_message_id_and_falsy_flags(self) -> None:
        out = RunAgentUseCase._answer_payload(
            "답", [], None, limit_reached=False, charts=[], approval_id=None,
            approval_pending=False,
        )
        assert out == {"answer": "답", "tools_used": []}

    def test_truthy_flags_are_attached(self) -> None:
        out = RunAgentUseCase._answer_payload(
            "답", [], 7, guard_blocked=True, charts=[{"type": "bar"}],
            approval_pending=True, approval_id="ap-1",
        )
        assert out["guard_blocked"] is True
        assert out["charts"] == [{"type": "bar"}]
        assert out["approval_pending"] is True and out["approval_id"] == "ap-1"
        assert out["assistant_message_id"] == 7


class TestSaveAssistantMessageReturnsId:
    @pytest.mark.asyncio
    async def test_returns_saved_id(self) -> None:
        uc = _uc()
        saved = SimpleNamespace(id=SimpleNamespace(value=4821))
        uc._persist_message = AsyncMock(return_value=saved)
        out = await uc._save_assistant_message("답", "u1", "s1", "ag1", persist=True)
        assert out == 4821
        uc._persist_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persist_false_returns_none_without_saving(self) -> None:
        uc = _uc()
        uc._persist_message = AsyncMock()
        out = await uc._save_assistant_message("답", "u1", "s1", "ag1", persist=False)
        assert out is None
        uc._persist_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_int_id_is_treated_as_missing(self) -> None:
        # 테스트 대역(MagicMock)·id 미발급 저장소에서는 키를 싣지 않는다 (§6.1)
        uc = _uc()
        uc._persist_message = AsyncMock(return_value=MagicMock())
        assert await uc._save_assistant_message("답", "u1", "s1", "ag1") is None
        uc._persist_message = AsyncMock(return_value=None)
        assert await uc._save_assistant_message("답", "u1", "s1", "ag1") is None


class TestExecuteExposesMessageId:
    def _events(self, payload: dict) -> list[AgentRunEvent]:
        now = datetime.now(UTC)
        return [
            AgentRunEvent(seq=1, event_type=AgentRunEventType.RUN_STARTED, run_id="r",
                          payload={"run_id": "r", "session_id": "s1"}, timestamp=now),
            AgentRunEvent(seq=2, event_type=AgentRunEventType.ANSWER_COMPLETED,
                          run_id="r", payload=payload, timestamp=now),
            AgentRunEvent(seq=3, event_type=AgentRunEventType.RUN_COMPLETED, run_id="r",
                          payload={"run_id": "r"}, timestamp=now),
        ]

    async def _run(self, uc: RunAgentUseCase, payload: dict) -> RunAgentResponse:
        events = self._events(payload)

        async def _stream(*_a, **_k):
            for e in events:
                yield e

        uc.stream = _stream  # type: ignore[method-assign]
        return await uc.execute("ag1", RunAgentRequest(user_id="u1", query="q"), "req")

    @pytest.mark.asyncio
    async def test_response_carries_assistant_message_id(self) -> None:
        payload = {"answer": "답", "tools_used": [], "assistant_message_id": 99}
        resp = await self._run(_uc(), payload)
        assert resp.assistant_message_id == 99

    @pytest.mark.asyncio
    async def test_response_none_when_payload_lacks_id(self) -> None:
        resp = await self._run(_uc(), {"answer": "답", "tools_used": []})
        assert resp.assistant_message_id is None
