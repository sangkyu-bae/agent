"""judgment domain VO 검증 — Design §8.2 #1~6."""

import math

import pytest
from src.domain.judgment.exceptions import (
    JudgmentError,
    JudgmentProtocolError,
    JudgmentTimeoutError,
    JudgmentUnavailableError,
)
from src.domain.judgment.value_objects import (
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentBackendKind,
    JudgmentRequest,
    JudgmentResponse,
    NoulAnswer,
    NoulQuestion,
)


class TestBackendKind:
    @pytest.mark.parametrize("raw", ["jev", "JEV", " jev "])
    def test_from_string_normalizes(self, raw):
        assert JudgmentBackendKind.from_string(raw) is JudgmentBackendKind.JEV

    @pytest.mark.parametrize("raw", ["jev2", "", None, "on"])
    def test_from_string_rejects_unknown(self, raw):
        with pytest.raises(ValueError):
            JudgmentBackendKind.from_string(raw)


class TestQuestions:
    def test_noul_requires_instructions(self):
        with pytest.raises(ValueError):
            NoulQuestion(instructions="  ")

    def test_choice_requires_two_labels(self):
        with pytest.raises(ValueError):
            ChoiceQuestion(instructions="q", criteria=(("a", None),))

    def test_choice_rejects_duplicate_labels(self):
        with pytest.raises(ValueError):
            ChoiceQuestion(instructions="q", criteria=(("a", "x"), ("a", "y")))

    def test_choice_labels_preserve_order(self):
        q = ChoiceQuestion(instructions="q", criteria=(("bar", "막대"), ("line", None)))
        assert q.labels == ("bar", "line")


class TestRequest:
    def test_rejects_empty_questions(self):
        with pytest.raises(ValueError):
            JudgmentRequest(state="s", questions={})

    def test_rejects_empty_state(self):
        with pytest.raises(ValueError):
            JudgmentRequest(state="", questions={"q": NoulQuestion("i")})
        with pytest.raises(ValueError):
            JudgmentRequest(state={}, questions={"q": NoulQuestion("i")})

    def test_rejects_non_string_state_values(self):
        with pytest.raises(ValueError):
            JudgmentRequest(state={"a": 1}, questions={"q": NoulQuestion("i")})

    def test_mapping_state_is_frozen_and_ordered(self):
        req = JudgmentRequest(
            state={"question": "q", "analysis_text": "a"},
            questions={"q": NoulQuestion("i")},
        )
        assert list(req.state) == ["question", "analysis_text"]
        with pytest.raises(TypeError):
            req.state["x"] = "y"  # type: ignore[index]
        with pytest.raises(TypeError):
            req.questions["z"] = NoulQuestion("i")  # type: ignore[index]


class TestAnswers:
    @pytest.mark.parametrize("p", [-0.1, 1.1, math.nan, "0.5", True])
    def test_noul_rejects_out_of_range(self, p):
        with pytest.raises(ValueError):
            NoulAnswer(probability=p)

    def test_noul_accepts_bounds(self):
        assert NoulAnswer(0.0).probability == 0.0
        assert NoulAnswer(1.0).probability == 1.0

    def test_choice_rejects_sum_off(self):
        with pytest.raises(ValueError):
            ChoiceAnswer("a", {"a": 0.5, "b": 0.4}, 0.5)

    def test_choice_accepts_small_rounding(self):
        ans = ChoiceAnswer("a", {"a": 0.505, "b": 0.5}, 0.505)
        assert ans.choice == "a"

    def test_choice_requires_choice_among_labels(self):
        with pytest.raises(ValueError):
            ChoiceAnswer("zzz", {"a": 0.5, "b": 0.5}, 0.5)

    def test_choice_rejects_bad_confidence(self):
        with pytest.raises(ValueError):
            ChoiceAnswer("a", {"a": 0.5, "b": 0.5}, 1.5)


class TestResponse:
    def _resp(self, **answers):
        return JudgmentResponse(
            answers=answers,
            model="jev-1.13.0",
            backend=JudgmentBackendKind.JEV,
            latency_ms=12,
        )

    def test_noul_accessor(self):
        resp = self._resp(q=NoulAnswer(0.7))
        assert resp.noul("q").probability == 0.7

    def test_noul_accessor_rejects_choice_answer(self):
        resp = self._resp(q=ChoiceAnswer("a", {"a": 1.0}, 1.0))
        with pytest.raises(JudgmentProtocolError):
            resp.noul("q")

    def test_missing_question_id(self):
        resp = self._resp(q=NoulAnswer(0.7))
        with pytest.raises(JudgmentProtocolError):
            resp.choice("other")

    @pytest.mark.parametrize("latency", [-1, 1.5, True])
    def test_rejects_bad_latency(self, latency):
        with pytest.raises(ValueError):
            JudgmentResponse(
                answers={"q": NoulAnswer(0.5)},
                model="m",
                backend=JudgmentBackendKind.ANYJEV,
                latency_ms=latency,
            )

    def test_rejects_empty_model(self):
        with pytest.raises(ValueError):
            JudgmentResponse(
                answers={"q": NoulAnswer(0.5)},
                model="",
                backend=JudgmentBackendKind.JEV,
                latency_ms=0,
            )


class TestExceptions:
    def test_hierarchy_and_messages(self):
        t = JudgmentTimeoutError(JudgmentBackendKind.JEV, 3.0)
        u = JudgmentUnavailableError(JudgmentBackendKind.ANYJEV, "refused", status=502)
        p = JudgmentProtocolError(JudgmentBackendKind.JEV, "no Yes label")
        assert all(isinstance(e, JudgmentError) for e in (t, u, p))
        assert str(t) == "jev: timed out after 3.0s"
        assert "status=502" in str(u) and u.status == 502
        assert p.detail == "no Yes label" and str(p).startswith("jev: protocol")


class TestActOneDefensiveBranches:
    """Check G12 — domain 방어 분기 100% 커버."""

    def test_request_rejects_non_string_non_mapping_state(self):
        with pytest.raises(ValueError, match="state must be"):
            JudgmentRequest(state=123, questions={"q": NoulQuestion("i")})

    def test_request_rejects_non_question_value(self):
        with pytest.raises(ValueError, match="not a Question"):
            JudgmentRequest(state="s", questions={"q": "not a question"})

    def test_choice_answer_rejects_empty_probabilities(self):
        with pytest.raises(ValueError, match="must not be empty"):
            ChoiceAnswer("a", {}, 1.0)

    def test_response_rejects_empty_answers(self):
        with pytest.raises(ValueError, match="answers must not be empty"):
            JudgmentResponse(
                answers={}, model="m", backend=JudgmentBackendKind.JEV, latency_ms=0
            )

    def test_response_rejects_non_answer_value(self):
        with pytest.raises(ValueError, match="not an Answer"):
            JudgmentResponse(
                answers={"q": "x"},
                model="m",
                backend=JudgmentBackendKind.JEV,
                latency_ms=0,
            )

    def test_response_rejects_non_enum_backend(self):
        with pytest.raises(ValueError, match="JudgmentBackendKind"):
            JudgmentResponse(
                answers={"q": NoulAnswer(0.5)},
                model="m",
                backend="jev",
                latency_ms=0,
            )
