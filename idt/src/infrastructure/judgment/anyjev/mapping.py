"""AnyJev(`python -m anyjev.serve`) 요청·응답 ↔ 도메인 VO 변환 — 순수 함수.

Design Ref: judgment-backend §4.2 —
- 요청은 항상 `{"items": [...]}`(D2), item 은 `state/question/kind[/options]`(D3)
- Noul 은 네이티브 `kind: "noul"`, 응답 `probs` 의 "Yes" 키를 대소문자 무시로 읽는다(D1)
- Choice 는 criteria 설명을 질문 본문에 접고 `options` 는 라벨 목록(D5),
  `confidence = max(probs)`(D6)
- dict state 는 "[key]\\n{value}" 블록을 빈 줄로 이어 붙인다(D12)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.domain.judgment.exceptions import JudgmentProtocolError
from src.domain.judgment.value_objects import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentBackendKind,
    JudgmentRequest,
    NoulAnswer,
    NoulQuestion,
)

_BACKEND = JudgmentBackendKind.ANYJEV
_YES = "yes"


def serialize_state(state: str | Mapping[str, str]) -> str:
    if isinstance(state, str):
        return state
    return "\n\n".join(f"[{key}]\n{value}" for key, value in state.items())


def fold_choice_question(question: ChoiceQuestion) -> str:
    lines = [question.instructions, "선택지:"]
    for label, description in question.criteria:
        lines.append(f"- {label}: {description}" if description else f"- {label}")
    return "\n".join(lines)


def to_items(request: JudgmentRequest) -> list[dict]:
    state = serialize_state(request.state)
    items: list[dict] = []
    for question in request.questions.values():
        if isinstance(question, NoulQuestion):
            items.append(
                {"state": state, "question": question.instructions, "kind": "noul"}
            )
        else:
            items.append(
                {
                    "state": state,
                    "question": fold_choice_question(question),
                    "kind": "choice",
                    "options": list(question.labels),
                }
            )
    return items


def from_decisions(
    request: JudgmentRequest, decisions: object
) -> tuple[dict[str, Answer], list[dict]]:
    """decisions → (qid→Answer, qid 순서의 부가 정보).

    부가 정보: margin, route, reasoning_tokens (Design D3).
    """
    if not isinstance(decisions, Sequence) or isinstance(decisions, str):
        raise JudgmentProtocolError(_BACKEND, "decisions is not a list")
    if len(decisions) != len(request.questions):
        raise JudgmentProtocolError(
            _BACKEND,
            f"expected {len(request.questions)} decisions, got {len(decisions)}",
        )
    answers: dict[str, Answer] = {}
    extras: list[dict] = []
    for (qid, question), decision in zip(request.questions.items(), decisions):
        probs = _probs_of(decision, qid)
        try:
            if isinstance(question, NoulQuestion):
                answers[qid] = _noul_answer(probs)
            else:
                answers[qid] = _choice_answer(question, probs, decision.get("answer"))
        except (ValueError, TypeError) as e:
            # Check G1: unhashable answer·타입 혼합 probs 는 TypeError 로 온다
            raise JudgmentProtocolError(_BACKEND, f"{qid}: {e}") from e
        extras.append(
            {
                "qid": qid,
                "margin": decision.get("margin"),
                "route": decision.get("route"),
                "reasoning_tokens": decision.get("reasoning_tokens"),
            }
        )
    return answers, extras


def _probs_of(decision: object, qid: str) -> dict[str, float]:
    if not isinstance(decision, Mapping):
        raise JudgmentProtocolError(_BACKEND, f"{qid}: decision is not an object")
    probs = decision.get("probs")
    if not isinstance(probs, Mapping) or not probs:
        raise JudgmentProtocolError(_BACKEND, f"{qid}: probs missing")
    return {str(k): v for k, v in probs.items()}


def _noul_answer(probs: Mapping[str, float]) -> NoulAnswer:
    for label, prob in probs.items():
        if label.casefold() == _YES:
            return NoulAnswer(probability=prob)
    raise ValueError(f"no Yes label in probs {sorted(probs)}")


def _choice_answer(
    question: ChoiceQuestion, probs: Mapping[str, float], answer: object
) -> ChoiceAnswer:
    expected = set(question.labels)
    if set(probs) != expected:
        raise ValueError(f"probs labels {sorted(probs)} != options {sorted(expected)}")
    choice = answer if answer in expected else max(probs, key=probs.__getitem__)
    return ChoiceAnswer(
        choice=str(choice), probabilities=dict(probs), confidence=max(probs.values())
    )
