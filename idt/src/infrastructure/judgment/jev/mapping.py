"""typesafe-sdk 타입 ↔ 도메인 VO 변환 + 예외 매핑 — 순수 함수.

Design Ref: judgment-backend §4.1 / D10 —
- VO → `Noul(instructions=)`, `Choice(instructions=, criteria={label: desc|None})`
- 응답 `answers[qid]` 의 type 이 질문 종류와 맞는지, Choice 라벨 집합이 같은지 검사
- SDK 예외: Timeout→JudgmentTimeoutError, ResponseValidation→JudgmentProtocolError,
  APIError(4xx/5xx)·Connection→JudgmentUnavailableError. 메시지에 body 를 싣지 않는다.
"""

from __future__ import annotations

from typesafe_sdk import (
    Choice,
    Noul,
    SystemOneResponse,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPIResponseValidationError,
    TypeSafeAPITimeoutError,
    TypeSafeError,
)

from src.domain.judgment.exceptions import (
    JudgmentError,
    JudgmentProtocolError,
    JudgmentTimeoutError,
    JudgmentUnavailableError,
)
from src.domain.judgment.value_objects import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentBackendKind,
    JudgmentRequest,
    NoulAnswer,
    NoulQuestion,
)

_BACKEND = JudgmentBackendKind.JEV


def to_sdk_questions(request: JudgmentRequest) -> dict[str, Noul | Choice]:
    sdk: dict[str, Noul | Choice] = {}
    for qid, question in request.questions.items():
        if isinstance(question, NoulQuestion):
            sdk[qid] = Noul(instructions=question.instructions)
        else:
            sdk[qid] = Choice(
                instructions=question.instructions,
                criteria=dict(question.criteria),
            )
    return sdk


def from_sdk_response(
    request: JudgmentRequest, response: SystemOneResponse
) -> tuple[dict[str, Answer], dict[str, object]]:
    answers: dict[str, Answer] = {}
    for qid, question in request.questions.items():
        raw = response.answers.get(qid)
        if raw is None:
            raise JudgmentProtocolError(_BACKEND, f"no answer for {qid!r}")
        try:
            answers[qid] = _to_answer(question, raw)
        except (ValueError, AttributeError) as e:
            raise JudgmentProtocolError(_BACKEND, f"{qid}: {e}") from e
    usage = getattr(response, "usage", None)
    extra = {
        "usage": {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }
    }
    return answers, extra


def _to_answer(question: NoulQuestion | ChoiceQuestion, raw) -> Answer:
    if isinstance(question, NoulQuestion):
        if raw.type != "noul":
            raise ValueError(f"expected noul answer, got {raw.type!r}")
        return NoulAnswer(probability=raw.noul)
    if raw.type != "choice":
        raise ValueError(f"expected choice answer, got {raw.type!r}")
    probabilities = dict(raw.probabilities)
    if set(probabilities) != set(question.labels):
        raise ValueError(
            f"probabilities labels {sorted(probabilities)} "
            f"!= criteria {sorted(question.labels)}"
        )
    return ChoiceAnswer(
        choice=raw.choice, probabilities=probabilities, confidence=raw.confidence
    )


def map_exception(error: TypeSafeError, timeout_seconds: float) -> JudgmentError:
    if isinstance(error, TypeSafeAPITimeoutError):
        return JudgmentTimeoutError(_BACKEND, timeout_seconds)
    if isinstance(error, TypeSafeAPIResponseValidationError):
        return JudgmentProtocolError(
            _BACKEND, f"response validation failed at {error.field_path}"
        )
    if isinstance(error, TypeSafeAPIError):
        return JudgmentUnavailableError(
            _BACKEND, type(error).__name__, status=error.status
        )
    if isinstance(error, TypeSafeAPIConnectionError):
        return JudgmentUnavailableError(_BACKEND, "connection failed")
    return JudgmentUnavailableError(_BACKEND, type(error).__name__)
