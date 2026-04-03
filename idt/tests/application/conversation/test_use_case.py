"""ConversationUseCase 단위 테스트 (repo/summarizer/llm 모두 mock)."""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.domain.conversation.entities import ConversationMessage, ConversationSummary
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.conversation.schemas import ConversationChatRequest
from src.domain.conversation.value_objects import MessageRole, SessionId, TurnIndex, UserId


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def _make_message(turn: int, role: str = "user", content: str = "msg") -> ConversationMessage:
    return ConversationMessage(
        id=None,
        user_id=UserId("u-1"),
        session_id=SessionId("s-1"),
        role=MessageRole.USER if role == "user" else MessageRole.ASSISTANT,
        content=content,
        turn_index=TurnIndex(turn),
        created_at=datetime(2026, 1, 1),
    )


def _make_use_case(
    existing_messages: list | None = None,
    llm_answer: str = "LLM 응답",
    summarizer_result: str = "요약 내용",
):
    from src.application.conversation.use_case import ConversationUseCase

    msg_repo = AsyncMock()
    summary_repo = AsyncMock()
    summarizer = AsyncMock()
    llm = AsyncMock()
    logger = MagicMock()
    policy = SummarizationPolicy(threshold=6, keep_recent=3)

    existing = existing_messages or []
    msg_repo.find_by_session.return_value = existing
    msg_repo.save.side_effect = lambda m: m  # 저장 후 원본 반환

    llm.generate.return_value = llm_answer
    summarizer.summarize.return_value = summarizer_result

    summary_repo.save.side_effect = lambda s: s

    uc = ConversationUseCase(
        message_repo=msg_repo,
        summary_repo=summary_repo,
        summarizer=summarizer,
        llm=llm,
        policy=policy,
        logger=logger,
    )
    return uc, msg_repo, summary_repo, summarizer, llm, logger


# ─────────────────────────────────────────────
# 정상 흐름: 요약 불필요 (≤ 6 메시지)
# ─────────────────────────────────────────────

class TestConversationUseCaseNoSummarization:
    @pytest.mark.asyncio
    async def test_saves_user_message(self):
        uc, msg_repo, *_ = _make_use_case(existing_messages=[])
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="안녕")
        await uc.execute(req, "req-1")
        # user 메시지 + assistant 메시지 총 2번 save 호출
        assert msg_repo.save.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_llm_answer(self):
        uc, *_ = _make_use_case(existing_messages=[], llm_answer="반갑습니다!")
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="안녕")
        resp = await uc.execute(req, "req-1")
        assert resp.answer == "반갑습니다!"

    @pytest.mark.asyncio
    async def test_was_summarized_false(self):
        # 6개 이하 메시지 → 요약 없음
        messages = [_make_message(i) for i in range(1, 5)]
        uc, *_ = _make_use_case(existing_messages=messages)
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="질문")
        resp = await uc.execute(req, "req-1")
        assert resp.was_summarized is False

    @pytest.mark.asyncio
    async def test_no_summarizer_called_when_not_needed(self):
        uc, _, _, summarizer, *_ = _make_use_case(existing_messages=[])
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="안녕")
        await uc.execute(req, "req-1")
        summarizer.summarize.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_receives_full_history(self):
        messages = [_make_message(1, role="user", content="첫 질문")]
        uc, _, _, _, llm, _ = _make_use_case(existing_messages=messages)
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="두 번째 질문")
        await uc.execute(req, "req-1")
        call_args = llm.generate.call_args[0][0]  # messages list
        contents = [m["content"] for m in call_args]
        assert "첫 질문" in contents
        assert "두 번째 질문" in contents


# ─────────────────────────────────────────────
# 요약 흐름: > 6 메시지
# ─────────────────────────────────────────────

class TestConversationUseCaseWithSummarization:
    @pytest.mark.asyncio
    async def test_was_summarized_true(self):
        # 7개 메시지 → 요약 필요
        messages = [_make_message(i) for i in range(1, 8)]
        uc, *_ = _make_use_case(existing_messages=messages)
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="질문")
        resp = await uc.execute(req, "req-1")
        assert resp.was_summarized is True

    @pytest.mark.asyncio
    async def test_summarizer_called(self):
        messages = [_make_message(i) for i in range(1, 8)]
        uc, _, _, summarizer, *_ = _make_use_case(existing_messages=messages)
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="질문")
        await uc.execute(req, "req-1")
        summarizer.summarize.assert_called_once()

    @pytest.mark.asyncio
    async def test_summary_saved_to_repo(self):
        messages = [_make_message(i) for i in range(1, 8)]
        uc, _, summary_repo, *_ = _make_use_case(
            existing_messages=messages, summarizer_result="요약 내용"
        )
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="질문")
        await uc.execute(req, "req-1")
        summary_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_receives_summary_in_context(self):
        messages = [_make_message(i) for i in range(1, 8)]
        uc, _, _, _, llm, _ = _make_use_case(
            existing_messages=messages, summarizer_result="요약된 내용입니다"
        )
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="질문")
        await uc.execute(req, "req-1")
        call_args = llm.generate.call_args[0][0]
        # system 메시지에 요약이 포함되어야 함
        system_msgs = [m for m in call_args if m["role"] == "system"]
        assert any("요약된 내용입니다" in m["content"] for m in system_msgs)


# ─────────────────────────────────────────────
# 로깅
# ─────────────────────────────────────────────

class TestConversationUseCaseLogging:
    @pytest.mark.asyncio
    async def test_logs_start_and_complete(self):
        uc, _, _, _, _, logger = _make_use_case()
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="안녕")
        await uc.execute(req, "req-1")
        assert logger.info.call_count >= 2

    @pytest.mark.asyncio
    async def test_logs_error_and_reraises(self):
        uc, msg_repo, _, _, _, logger = _make_use_case()
        msg_repo.find_by_session.side_effect = RuntimeError("DB 오류")
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="안녕")
        with pytest.raises(RuntimeError):
            await uc.execute(req, "req-1")
        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_response_fields(self):
        uc, *_ = _make_use_case(llm_answer="좋은 날씨네요")
        req = ConversationChatRequest(user_id="u-1", session_id="s-1", message="날씨")
        resp = await uc.execute(req, "req-99")
        assert resp.user_id == "u-1"
        assert resp.session_id == "s-1"
        assert resp.request_id == "req-99"
        assert resp.answer == "좋은 날씨네요"
