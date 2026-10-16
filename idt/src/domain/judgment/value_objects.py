"""judgment 값 객체.

Design Ref: judgment-backend §3.1 — frozen dataclass, 검증은 `__post_init__`에서
`ValueError`(D11). 어댑터는 이를 `JudgmentProtocolError`로 바꾼다(FR-03).
질문 id는 코드용이며 모델에 보내지 않는다 — 의미는 instructions 에 전부 담는다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

_PROB_SUM_TOLERANCE = 0.01


class JudgmentBackendKind(StrEnum):
    JEV = "jev"
    ANYJEV = "anyjev"
    OFF = "off"

    @classmethod
    def from_string(cls, raw: str | None) -> JudgmentBackendKind:
        """대소문자·양끝 공백 무시.

        빈 값·오타는 ValueError — 조용히 off 로 만들지 않는다.
        """
        normalized = (raw or "").strip().casefold()
        for kind in cls:
            if kind.value == normalized:
                return kind
        allowed = ", ".join(k.value for k in cls)
        raise ValueError(f"unknown judgment backend {raw!r} (allowed: {allowed})")


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_unit_interval(value: object, name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    if math.isnan(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be within [0, 1], got {value!r}")


@dataclass(frozen=True)
class NoulQuestion:
    """조건이 참인지 — 답은 예일 확률 하나."""

    instructions: str

    def __post_init__(self) -> None:
        _require_text(self.instructions, "instructions")


@dataclass(frozen=True)
class ChoiceQuestion:
    """정해진 라벨 중 하나 — criteria 는 (라벨, 설명|None) 순서 보존."""

    instructions: str
    criteria: tuple[tuple[str, str | None], ...]

    def __post_init__(self) -> None:
        _require_text(self.instructions, "instructions")
        labels = [label for label, _ in self.criteria]
        if len(labels) < 2:
            raise ValueError("criteria needs at least two labels")
        for label in labels:
            _require_text(label, "criteria label")
        if len(set(labels)) != len(labels):
            raise ValueError("criteria labels must be unique")

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(label for label, _ in self.criteria)


Question = NoulQuestion | ChoiceQuestion


def _freeze(mapping: Mapping) -> Mapping:
    return (
        mapping
        if isinstance(mapping, MappingProxyType)
        else MappingProxyType(dict(mapping))
    )


@dataclass(frozen=True)
class JudgmentRequest:
    """같은 state 에 대한 질문 묶음(FR-02).

    dict state 는 키 순서가 직렬화 순서다(D12).
    """

    state: str | Mapping[str, str]
    questions: Mapping[str, Question]

    def __post_init__(self) -> None:
        if isinstance(self.state, str):
            _require_text(self.state, "state")
        elif isinstance(self.state, Mapping):
            if not self.state:
                raise ValueError("state mapping must not be empty")
            for key, value in self.state.items():
                _require_text(key, "state key")
                if not isinstance(value, str):
                    raise ValueError(f"state[{key!r}] must be a string")
            object.__setattr__(self, "state", _freeze(self.state))
        else:
            raise ValueError("state must be a string or a mapping of strings")
        if not self.questions:
            raise ValueError("questions must not be empty")
        for qid, question in self.questions.items():
            _require_text(qid, "question id")
            if not isinstance(question, (NoulQuestion, ChoiceQuestion)):
                raise ValueError(f"questions[{qid!r}] is not a Question")
        object.__setattr__(self, "questions", _freeze(self.questions))


@dataclass(frozen=True)
class NoulAnswer:
    probability: float

    def __post_init__(self) -> None:
        _require_unit_interval(self.probability, "probability")


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probabilities: Mapping[str, float]
    confidence: float

    def __post_init__(self) -> None:
        if not self.probabilities:
            raise ValueError("probabilities must not be empty")
        for label, prob in self.probabilities.items():
            _require_text(label, "probability label")
            _require_unit_interval(prob, f"probabilities[{label!r}]")
        total = sum(self.probabilities.values())
        if abs(total - 1.0) > _PROB_SUM_TOLERANCE:
            raise ValueError(f"probabilities must sum to 1 (got {total:.4f})")
        if self.choice not in self.probabilities:
            raise ValueError(f"choice {self.choice!r} is not among the labels")
        _require_unit_interval(self.confidence, "confidence")
        object.__setattr__(self, "probabilities", _freeze(self.probabilities))


Answer = NoulAnswer | ChoiceAnswer


@dataclass(frozen=True)
class JudgmentResponse:
    """answers 의 키 집합은 요청 questions 와 같다 — 어댑터가 보장한다."""

    answers: Mapping[str, Answer]
    model: str
    backend: JudgmentBackendKind
    latency_ms: int
    extra: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.answers:
            raise ValueError("answers must not be empty")
        for qid, answer in self.answers.items():
            if not isinstance(answer, (NoulAnswer, ChoiceAnswer)):
                raise ValueError(f"answers[{qid!r}] is not an Answer")
        _require_text(self.model, "model")
        if not isinstance(self.backend, JudgmentBackendKind):
            raise ValueError("backend must be a JudgmentBackendKind")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, int):
            raise ValueError("latency_ms must be an int")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be >= 0")
        object.__setattr__(self, "answers", _freeze(self.answers))
        object.__setattr__(self, "extra", _freeze(self.extra))

    def noul(self, qid: str) -> NoulAnswer:
        return self._typed(qid, NoulAnswer)

    def choice(self, qid: str) -> ChoiceAnswer:
        return self._typed(qid, ChoiceAnswer)

    def _typed(self, qid: str, expected: type):
        # 지연 import — exceptions 가 이 모듈의 enum 을 쓰므로 순환을 끊는다.
        from src.domain.judgment.exceptions import JudgmentProtocolError

        answer = self.answers.get(qid)
        if answer is None:
            raise JudgmentProtocolError(self.backend, f"no answer for question {qid!r}")
        if not isinstance(answer, expected):
            raise JudgmentProtocolError(
                self.backend,
                f"answer {qid!r} is {type(answer).__name__}, "
                f"expected {expected.__name__}",
            )
        return answer
