"""FeedbackWikiDistiller 단위 테스트 (wiki-feedback-loop Design §3-3).

WikiDistiller 동형 — LLM은 ainvoke mock 주입, worthy 판정·JSON 파싱·격리 검증.
"""
import json
from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.wiki.feedback_distiller import FeedbackWikiDistiller


def _make(response_content):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=response_content))
    logger = MagicMock()
    return FeedbackWikiDistiller(llm, logger), llm, logger


class TestDistillFeedback:
    async def test_worthy면_draft_반환_confidence는_100분율_클램프(self):
        distiller, _, _ = _make(json.dumps({
            "worthy": True,
            "title": "여신 한도 산정 기준",
            "content": "여신 한도는 담보가치의 70%를 상한으로 한다.",
            "confidence": 80,
        }))

        draft = await distiller.distill_feedback(
            "질문", "답변", "한도 기준이 틀렸어요", "req-1"
        )

        assert draft is not None
        assert draft.title == "여신 한도 산정 기준"
        assert "70%" in draft.content
        assert draft.confidence == 0.8

    async def test_worthy_false면_None(self):
        distiller, _, _ = _make(json.dumps({"worthy": False}))
        assert await distiller.distill_feedback("질문", "답변", "이유", "req-1") is None

    async def test_불량_JSON은_None과_warning(self):
        distiller, _, logger = _make("승격할 내용이 없습니다.")
        result = await distiller.distill_feedback("질문", "답변", "이유", "req-1")
        assert result is None
        logger.warning.assert_called_once()

    async def test_코드펜스_JSON도_파싱(self):
        distiller, _, _ = _make(
            '```json\n{"worthy": true, "title": "제목", "content": "본문", "confidence": 50}\n```'
        )
        draft = await distiller.distill_feedback("질문", "답변", "이유", "req-1")
        assert draft is not None
        assert draft.confidence == 0.5

    async def test_confidence_비수치면_기본_0_5로_강등(self):
        distiller, _, _ = _make(json.dumps(
            {"worthy": True, "title": "제목", "content": "본문", "confidence": "high"}
        ))
        draft = await distiller.distill_feedback("질문", "답변", "이유", "req-1")
        assert draft is not None  # 초안은 유지 — 점수만 기본값
        assert draft.confidence == 0.5

    async def test_confidence_부재시_기본_0_5(self):
        distiller, _, _ = _make(json.dumps(
            {"worthy": True, "title": "제목", "content": "본문"}
        ))
        draft = await distiller.distill_feedback("질문", "답변", "이유", "req-1")
        assert draft.confidence == 0.5

    async def test_프롬프트에_질문_답변_이유_원문_포함(self):
        distiller, llm, _ = _make(json.dumps({"worthy": False}))

        await distiller.distill_feedback(
            "대출 한도가 얼마죠", "담보의 90%입니다", "70%가 맞습니다", "req-1"
        )

        human_text = llm.ainvoke.call_args.args[0][1].content
        assert "대출 한도가 얼마죠" in human_text
        assert "담보의 90%입니다" in human_text
        assert "70%가 맞습니다" in human_text

    async def test_title_200자_절단(self):
        distiller, _, _ = _make(json.dumps(
            {"worthy": True, "title": "가" * 300, "content": "본문", "confidence": 60}
        ))
        draft = await distiller.distill_feedback("질문", "답변", "이유", "req-1")
        assert len(draft.title) == 200

    async def test_title이나_content_비면_None(self):
        distiller, _, logger = _make(json.dumps(
            {"worthy": True, "title": "", "content": "본문"}
        ))
        assert await distiller.distill_feedback("질문", "답변", "이유", "req-1") is None


class TestMatchCandidates:
    """recurring-feedback-promotion §3-3 — 기존 초안 후보 매칭."""

    async def test_candidates_전달시_프롬프트에_후보와_병합_지시_포함(self):
        distiller, llm, _ = _make(json.dumps({"worthy": False}))

        await distiller.distill_feedback(
            "질문", "답변", "이유", "req-1",
            candidates=[("w1", "여신 한도 산정 기준"), ("w2", "금리 용어 정의")],
        )

        human_text = llm.ainvoke.call_args.args[0][1].content
        assert "[기존 초안 후보" in human_text
        assert "w1: 여신 한도 산정 기준" in human_text
        assert "w2: 금리 용어 정의" in human_text
        assert "match_id" in human_text

    async def test_candidates_없으면_기존_프롬프트와_동일(self):
        distiller, llm, _ = _make(json.dumps({"worthy": False}))

        await distiller.distill_feedback("질문", "답변", "이유", "req-1")

        human_text = llm.ainvoke.call_args.args[0][1].content
        assert "[기존 초안 후보" not in human_text

    async def test_match_id_파싱(self):
        distiller, _, _ = _make(json.dumps({
            "worthy": True, "title": "제목", "content": "본문",
            "confidence": 70, "match_id": "w1",
        }))

        draft = await distiller.distill_feedback(
            "질문", "답변", "이유", "req-1", candidates=[("w1", "제목")],
        )

        assert draft.match_id == "w1"

    async def test_후보에_없는_match_id는_None_강등(self):
        distiller, _, _ = _make(json.dumps({
            "worthy": True, "title": "제목", "content": "본문",
            "confidence": 70, "match_id": "환각-id",
        }))

        draft = await distiller.distill_feedback(
            "질문", "답변", "이유", "req-1", candidates=[("w1", "제목")],
        )

        assert draft is not None
        assert draft.match_id is None  # 환각 id 1차 차단

    async def test_candidates_없이_match_id_응답은_None(self):
        distiller, _, _ = _make(json.dumps({
            "worthy": True, "title": "제목", "content": "본문", "match_id": "w1",
        }))
        draft = await distiller.distill_feedback("질문", "답변", "이유", "req-1")
        assert draft.match_id is None
