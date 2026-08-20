"""의도 판정 결과 검증·정규화 정책.

Design Ref: §2.2 / §3.2 — 판정 자체는 LLM 이 하되(Plan D2), 신뢰할 수 없는 출력을
도메인 계약에 맞추는 일은 순수 함수가 맡는다. LLM·IO 의존이 없으므로 분기를
100% 테스트할 수 있다.

이 모듈이 보장하는 불변식 (Design §3.2):
  I1  filled_slots 의 키는 spec.slots 의 부분집합이다
  I2  missing_slots = spec.slots − filled_slots   (LLM 이 아니라 여기서 계산)
  I3  questions 의 slot_key 는 전부 missing_slots 에 있다
  I4  complete == required 축이 모두 filled_slots 에 있음
  I5  round_ >= max_rounds  →  questions == []    (무한 되묻기 차단)
  I6  degraded  →  확장 필드 전부 빈 값, complete=False
  I7  빈 값(공백 포함)은 채워진 것이 아니다
"""
from src.domain.intent.schemas import (
    IntentDraft,
    IntentResult,
    IntentSpec,
    SlotAnswer,
    SlotLimits,
    SlotQuestion,
    SlotQuestionDraft,
    SlotSpec,
    SlotSuggestion,
    SlotValue,
)

_MIN_CONFIDENCE = 0.0
_MAX_CONFIDENCE = 1.0


class IntentResultPolicy:
    """LLM 초안(IntentDraft) → 도메인 계약을 만족하는 IntentResult."""

    @staticmethod
    def degraded() -> IntentResult:
        """판정을 시도조차 못 한 경우의 결과 (Plan D6 / Design E1~E3).

        '의도 모름'을 뜻하며, 호출자는 기존 로직을 그대로 진행하면 된다.
        확장 필드는 전부 기본값(빈 값)이고 complete 는 False 다 (I6).
        """
        return IntentResult(degraded=True)

    @staticmethod
    def normalize(
        draft: IntentDraft,
        spec: IntentSpec,
        *,
        answers: list[SlotAnswer] | None = None,
        round_: int = 0,
        limits: SlotLimits | None = None,
        degraded: bool = False,
    ) -> IntentResult:
        """LLM 초안을 spec 기준으로 검증·정규화·병합한다.

        `degraded` 는 인자로만 받는다 — IntentDraft 에 그 필드가 없으므로
        LLM 이 오염시킬 경로 자체가 존재하지 않는다 (Design §2.4).
        """
        limits = limits or SlotLimits()
        label = _resolve_label(draft.label, spec)
        filled = _merge_answers(_filter_filled(draft.filled_slots, spec), answers, spec)
        missing = _resolve_missing(spec, filled)
        suggestions = _filter_suggestions(draft.suggestions, missing, limits)
        questions = _resolve_questions(
            draft.questions, spec, missing, round_, limits, suggestions
        )
        return IntentResult(
            label=label,
            confidence=_resolve_confidence(draft.confidence, label),
            ambiguous=_resolve_ambiguous(draft, label),
            reason=draft.reason,
            filled_slots=filled,
            suggestions=suggestions,
            questions=questions,
            missing_slots=missing,
            complete=_resolve_complete(spec, filled),
            degraded=degraded,
        )


# --- 라벨 판정 (선행 사이클 계약 유지) --------------------------------------


def _resolve_label(raw_label: str | None, spec: IntentSpec) -> str | None:
    """spec 에 없는 label 은 None 으로 강등한다 (Design E4)."""
    if not raw_label:
        return None
    known = {label.name for label in spec.labels}
    return raw_label if raw_label in known else None


def _resolve_confidence(raw_confidence: float, label: str | None) -> float:
    """label 이 없으면 0.0, 있으면 0.0~1.0 으로 clamp 한다."""
    if label is None:
        return _MIN_CONFIDENCE
    return max(_MIN_CONFIDENCE, min(_MAX_CONFIDENCE, raw_confidence))


def _resolve_ambiguous(draft: IntentDraft, label: str | None) -> bool:
    """강등된 경우에만 ambiguous 를 세운다.

    빈 label 은 '해당 없음' 탈출구(Design §4.3)이지 후보가 갈린 것이 아니므로
    ambiguous 로 승격하지 않는다.
    """
    demoted = bool(draft.label) and label is None
    return draft.ambiguous or demoted


# --- 슬롯 채우기 (I1 / I7) --------------------------------------------------


def _filter_filled(raw: list[SlotValue], spec: IntentSpec) -> dict[str, str]:
    """spec 밖 키를 버리고 빈 값을 제외하며, 도메인 표현인 dict 로 접는다 (I1 / I7).

    LLM 스키마는 배열이지만(strict 호환, Act-1) 도메인 계약은 dict 다.
    같은 key 가 두 번 오면 뒤엣것이 이긴다.
    """
    keys = _slot_keys(spec)
    return {
        item.key: item.value.strip()
        for item in raw
        if item.key in keys and item.value.strip()
    }


def _merge_answers(
    filled: dict[str, str],
    answers: list[SlotAnswer] | None,
    spec: IntentSpec,
) -> dict[str, str]:
    """사용자 답변을 병합한다. 충돌 시 **답변이 이긴다** (Plan D6).

    되묻기의 존재 이유가 사람의 결정을 받는 것이므로, LLM 이 이를 뒤집으면
    HITL 이 무의미해진다.
    """
    keys = _slot_keys(spec)
    merged = dict(filled)
    for answer in answers or []:
        value = answer.value.strip()
        if answer.slot_key in keys and value:
            merged[answer.slot_key] = value
    return merged


def _resolve_missing(spec: IntentSpec, filled: dict[str, str]) -> list[str]:
    """I2: 못 채운 축을 spec 선언 순서대로 계산한다."""
    return [slot.key for slot in spec.slots if slot.key not in filled]


def _resolve_complete(spec: IntentSpec, filled: dict[str, str]) -> bool:
    """I4: required 축이 모두 채워졌는가. required 가 없으면 공집합 조건이 참이다."""
    return all(slot.key in filled for slot in spec.slots if slot.required)


# --- 되묻기 (I3 / I5) -------------------------------------------------------


def _filter_suggestions(
    raw: list[SlotSuggestion], missing: list[str], limits: SlotLimits
) -> dict[str, list[str]]:
    """못 채운 축의 선택지만 남기고 축당 상한으로 clamp 한 뒤 dict 로 접는다.

    이미 채워진 축에 선택지를 주는 것은 잡음이므로 버린다.
    """
    allowed = set(missing)
    return {
        item.key: item.options[: limits.max_options_per_slot]
        for item in raw
        if item.key in allowed and item.options
    }


def _resolve_questions(
    drafts: list[SlotQuestionDraft],
    spec: IntentSpec,
    missing: list[str],
    round_: int,
    limits: SlotLimits,
    suggestions: dict[str, list[str]],
) -> list[SlotQuestion]:
    """미충족 축에 대한 질문만 남긴다 (I3), 라운드 상한이면 전부 버린다 (I5).

    I5 는 프롬프트의 소프트 신호와 **별개로** 여기서 하드 강제한다 — 프롬프트만
    믿지 않는다 (규약 C5).
    """
    if round_ >= limits.max_rounds:
        return []
    by_key = {slot.key: slot for slot in spec.slots}
    allowed = set(missing)
    questions: list[SlotQuestion] = []
    seen: set[str] = set()
    for draft in drafts:
        slot = by_key.get(draft.slot_key)
        if slot is None or draft.slot_key not in allowed or draft.slot_key in seen:
            continue
        seen.add(draft.slot_key)
        questions.append(_to_question(draft, slot, limits, suggestions))
    return questions[: limits.max_questions]


def _to_question(
    draft: SlotQuestionDraft,
    slot: SlotSpec,
    limits: SlotLimits,
    suggestions: dict[str, list[str]],
) -> SlotQuestion:
    """allow_free_text 는 SlotSpec 이 진실이다 — LLM 이 정하지 않는다.

    options 는 LLM 이 비워 두는 일이 잦다(선택지를 질문 문장 안에 녹여 버린다).
    같은 정보가 suggestions 에 있으면 그것으로 채운다 — 화면이 선택 버튼을
    만들 수 있어야 하기 때문이다 (Act-2 D1).
    """
    options = draft.options or suggestions.get(draft.slot_key, [])
    return SlotQuestion(
        slot_key=draft.slot_key,
        question=draft.question,
        options=options[: limits.max_options_per_slot],
        allow_free_text=slot.allow_free_text,
    )


def _slot_keys(spec: IntentSpec) -> set[str]:
    return {slot.key for slot in spec.slots}
