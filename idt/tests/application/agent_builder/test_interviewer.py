"""Interviewer 단위 테스트."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.interviewer import Interviewer, _EvaluationOutput, _QuestionsOutput
from src.application.agent_builder.interview_session_store import QAPair


def _make_interviewer() -> tuple:
    mock_q_llm = MagicMock()
    mock_e_llm = MagicMock()
    mock_base_llm = MagicMock()
    mock_base_llm.with_structured_output = MagicMock(side_effect=[mock_q_llm, mock_e_llm])
    logger = MagicMock()
    interviewer = Interviewer(llm=mock_base_llm, logger=logger)
    return interviewer, mock_q_llm, mock_e_llm


class TestInterviewer:
    @pytest.mark.asyncio
    async def test_generate_initial_questions_returns_list(self):
        interviewer, mock_q_llm, _ = _make_interviewer()
        mock_q_llm.ainvoke = AsyncMock(
            return_value=_QuestionsOutput(questions=["어떤 주제?", "저장 경로는?", "몇 개?"])
        )
        result = await interviewer.generate_initial_questions("AI 뉴스 수집", "req-1")
        assert isinstance(result, list)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_generate_initial_questions_calls_llm(self):
        interviewer, mock_q_llm, _ = _make_interviewer()
        mock_q_llm.ainvoke = AsyncMock(
            return_value=_QuestionsOutput(questions=["질문1"])
        )
        await interviewer.generate_initial_questions("AI 뉴스 수집", "req-1")
        mock_q_llm.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_sufficient_returns_true_when_done(self):
        interviewer, _, mock_e_llm = _make_interviewer()
        mock_e_llm.ainvoke = AsyncMock(
            return_value=_EvaluationOutput(sufficient=True, questions=[])
        )
        qa_pairs = [QAPair(question="주제?", answer="OpenAI 뉴스")]
        sufficient, questions = await interviewer.evaluate_and_get_followup(
            "AI 뉴스 수집", qa_pairs, "req-1"
        )
        assert sufficient is True
        assert questions == []

    @pytest.mark.asyncio
    async def test_evaluate_insufficient_returns_followup_questions(self):
        interviewer, _, mock_e_llm = _make_interviewer()
        mock_e_llm.ainvoke = AsyncMock(
            return_value=_EvaluationOutput(sufficient=False, questions=["저장 경로는?"])
        )
        qa_pairs = [QAPair(question="주제?", answer="OpenAI 뉴스")]
        sufficient, questions = await interviewer.evaluate_and_get_followup(
            "AI 뉴스 수집", qa_pairs, "req-1"
        )
        assert sufficient is False
        assert len(questions) == 1

    def test_build_enriched_context_includes_qa(self):
        interviewer, _, _ = _make_interviewer()
        qa_pairs = [
            QAPair(question="주제?", answer="OpenAI 뉴스"),
            QAPair(question="저장 경로?", answer="/data/news"),
        ]
        context = interviewer.build_enriched_context("AI 뉴스 수집", qa_pairs)
        assert "AI 뉴스 수집" in context
        assert "OpenAI 뉴스" in context
        assert "/data/news" in context
