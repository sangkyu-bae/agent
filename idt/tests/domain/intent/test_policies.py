"""IntentResultPolicy 단위 테스트.

Design §8.2 시나리오 S1~S17 + 라벨 판정(선행 사이클 시나리오 1~9).
순수 함수이므로 LLM·IO 없이 분기 100% 커버한다.

불변식 I1~I7 이 이 파일에서 전부 잠긴다 (Design §3.2).
"""
import pytest
from src.domain.intent.policies import IntentResultPolicy
from src.domain.intent.schemas import (
    IntentDraft,
    IntentLabel,
    IntentSpec,
    SlotAnswer,
    SlotLimits,
    SlotQuestionDraft,
    SlotSpec,
    SlotSuggestion,
)


def _spec(slots: list[SlotSpec] | None = None) -> IntentSpec:
    return IntentSpec(
        labels=[
            IntentLabel(name="search", description="근거 문서를 찾아야 하는 질문"),
            IntentLabel(name="analysis", description="데이터를 계산·비교하는 질문"),
        ],
        slots=slots or [],
    )


def _slot(key: str, *, required: bool = False, free: bool = True) -> SlotSpec:
    return SlotSpec(
        key=key, description=f"{key} 설명", required=required, allow_free_text=free
    )


def _normalize(draft: IntentDraft, spec: IntentSpec, **kwargs):
    return IntentResultPolicy.normalize(draft, spec, **kwargs)


# ===========================================================================
# 라벨 판정 (선행 사이클 계약 — 회귀 방지)
# ===========================================================================


def test_label_in_spec_passes_through() -> None:
    draft = IntentDraft(label="search", confidence=0.82, reason="근거 필요")

    result = _normalize(draft, _spec())

    assert result.label == "search"
    assert result.confidence == pytest.approx(0.82)
    assert result.ambiguous is False
    assert result.degraded is False
    assert result.reason == "근거 필요"


def test_label_outside_spec_is_demoted_not_degraded() -> None:
    draft = IntentDraft(label="weather", confidence=0.9)

    result = _normalize(draft, _spec())

    assert result.label is None
    assert result.ambiguous is True
    assert result.degraded is False, "정상 판정이므로 시스템 장애(degraded)가 아니다"


def test_empty_label_is_not_marked_ambiguous() -> None:
    """빈 label 은 '해당 없음' 탈출구이지 후보가 갈린 것이 아니다."""
    draft = IntentDraft(label="", confidence=0.4)

    result = _normalize(draft, _spec())

    assert result.label is None
    assert result.ambiguous is False


def test_none_label_forces_zero_confidence() -> None:
    draft = IntentDraft(label=None, confidence=0.9)

    assert _normalize(draft, _spec()).confidence == pytest.approx(0.0)


def test_demoted_label_also_forces_zero_confidence() -> None:
    draft = IntentDraft(label="weather", confidence=0.95)

    assert _normalize(draft, _spec()).confidence == pytest.approx(0.0)


def test_confidence_above_one_is_clamped() -> None:
    draft = IntentDraft(label="search", confidence=1.7)

    assert _normalize(draft, _spec()).confidence == pytest.approx(1.0)


def test_negative_confidence_is_clamped() -> None:
    draft = IntentDraft(label="search", confidence=-0.3)

    assert _normalize(draft, _spec()).confidence == pytest.approx(0.0)


def test_slots_only_spec_needs_no_label() -> None:
    """분류 라벨 없이 슬롯만 쓰는 호출도 정상 동작한다 (FR-16)."""
    spec = IntentSpec(slots=[_slot("tone")])
    draft = IntentDraft(filled_slots={"tone": "친근"})

    result = _normalize(draft, spec)

    assert result.label is None
    assert result.filled_slots == {"tone": "친근"}


# ===========================================================================
# S1~S3 · I1/I2/I7 — filled_slots 필터와 missing_slots 계산
# ===========================================================================


def test_s1_unknown_slot_key_is_dropped() -> None:
    """I1: filled_slots 의 키는 spec.slots 부분집합이다."""
    draft = IntentDraft(filled_slots={"tone": "친근", "날씨": "맑음"})

    result = _normalize(draft, _spec(slots=[_slot("tone")]))

    assert result.filled_slots == {"tone": "친근"}


def test_s2_empty_value_is_treated_as_unfilled() -> None:
    """I7: 빈 값은 채워진 것이 아니다."""
    draft = IntentDraft(filled_slots={"tone": "", "task": "   "})

    result = _normalize(draft, _spec(slots=[_slot("tone"), _slot("task")]))

    assert result.filled_slots == {}
    assert result.missing_slots == ["tone", "task"]


def test_filled_value_is_stripped() -> None:
    draft = IntentDraft(filled_slots={"tone": "  친근  "})

    result = _normalize(draft, _spec(slots=[_slot("tone")]))

    assert result.filled_slots == {"tone": "친근"}


def test_s3_missing_slots_is_computed_not_taken_from_llm() -> None:
    """I2: missing_slots = spec.slots − filled_slots. LLM 은 이 필드를 채우지 못한다."""
    draft = IntentDraft(filled_slots={"tone": "친근"})

    result = _normalize(
        draft, _spec(slots=[_slot("tone"), _slot("task"), _slot("output")])
    )

    assert result.missing_slots == ["task", "output"]


def test_missing_slots_preserves_spec_order() -> None:
    draft = IntentDraft()

    result = _normalize(draft, _spec(slots=[_slot("c"), _slot("a"), _slot("b")]))

    assert result.missing_slots == ["c", "a", "b"]


def test_missing_slots_empty_when_spec_has_no_slots() -> None:
    result = _normalize(IntentDraft(filled_slots={"x": "y"}), _spec())

    assert result.missing_slots == []
    assert result.filled_slots == {}


# ===========================================================================
# S4~S5 — suggestions 필터와 상한
# ===========================================================================


def test_s4_suggestions_for_unknown_key_are_dropped() -> None:
    draft = IntentDraft(suggestions={"tone": ["친근"], "날씨": ["맑음"]})

    result = _normalize(draft, _spec(slots=[_slot("tone")]))

    assert result.suggestions == {"tone": ["친근"]}


def test_suggestions_for_already_filled_slot_are_dropped() -> None:
    """채워진 축에 선택지를 주는 것은 잡음이다."""
    draft = IntentDraft(
        filled_slots={"tone": "친근"}, suggestions={"tone": ["격식"], "task": ["분석"]}
    )

    result = _normalize(draft, _spec(slots=[_slot("tone"), _slot("task")]))

    assert result.suggestions == {"task": ["분석"]}


def test_s5_suggestions_are_clamped_per_slot() -> None:
    draft = IntentDraft(suggestions={"tone": ["a", "b", "c", "d", "e", "f"]})

    result = _normalize(
        draft, _spec(slots=[_slot("tone")]), limits=SlotLimits(max_options_per_slot=4)
    )

    assert result.suggestions["tone"] == ["a", "b", "c", "d"]


def test_empty_suggestion_list_is_dropped() -> None:
    draft = IntentDraft(suggestions={"tone": []})

    result = _normalize(draft, _spec(slots=[_slot("tone")]))

    assert result.suggestions == {}


# ===========================================================================
# S6~S7 · I3 — questions 필터와 상한
# ===========================================================================


def _q(slot_key: str, options: list[str] | None = None) -> SlotQuestionDraft:
    return SlotQuestionDraft(
        slot_key=slot_key, question=f"{slot_key}?", options=options or []
    )


def test_s6_question_for_already_filled_slot_is_dropped() -> None:
    """I3: questions 의 slot_key 는 전부 missing_slots 에 있다."""
    draft = IntentDraft(
        filled_slots={"tone": "친근"}, questions=[_q("tone"), _q("task")]
    )

    result = _normalize(draft, _spec(slots=[_slot("tone"), _slot("task")]))

    assert [q.slot_key for q in result.questions] == ["task"]


def test_question_for_unknown_slot_key_is_dropped() -> None:
    draft = IntentDraft(questions=[_q("날씨")])

    result = _normalize(draft, _spec(slots=[_slot("tone")]))

    assert result.questions == []


def test_s7_questions_are_clamped() -> None:
    slots = [_slot("a"), _slot("b"), _slot("c"), _slot("d")]
    draft = IntentDraft(questions=[_q("a"), _q("b"), _q("c"), _q("d")])

    result = _normalize(draft, _spec(slots=slots), limits=SlotLimits(max_questions=3))

    assert [q.slot_key for q in result.questions] == ["a", "b", "c"]


def test_duplicate_questions_for_same_slot_are_deduped() -> None:
    draft = IntentDraft(questions=[_q("tone"), _q("tone")])

    result = _normalize(draft, _spec(slots=[_slot("tone")]))

    assert len(result.questions) == 1


def test_question_options_are_clamped() -> None:
    draft = IntentDraft(questions=[_q("tone", ["a", "b", "c", "d", "e"])])

    result = _normalize(
        draft, _spec(slots=[_slot("tone")]), limits=SlotLimits(max_options_per_slot=4)
    )

    assert result.questions[0].options == ["a", "b", "c", "d"]


def test_allow_free_text_comes_from_spec_not_llm() -> None:
    """LLM 은 allow_free_text 를 정하지 못한다 — SlotSpec 이 진실이다."""
    draft = IntentDraft(questions=[_q("tone")])

    result = _normalize(draft, _spec(slots=[_slot("tone", free=False)]))

    assert result.questions[0].allow_free_text is False


# ===========================================================================
# S8~S11 — answers 병합 (Plan D6: 사람이 LLM 을 이긴다)
# ===========================================================================


def test_s8_answer_fills_slot_llm_did_not() -> None:
    draft = IntentDraft()

    result = _normalize(
        draft,
        _spec(slots=[_slot("tone")]),
        answers=[SlotAnswer(slot_key="tone", value="친근")],
    )

    assert result.filled_slots == {"tone": "친근"}
    assert result.missing_slots == []


def test_s9_answer_overrides_llm_extraction() -> None:
    """충돌 시 사용자 답변이 이긴다 — 되묻기의 존재 이유."""
    draft = IntentDraft(filled_slots={"tone": "격식"})

    result = _normalize(
        draft,
        _spec(slots=[_slot("tone")]),
        answers=[SlotAnswer(slot_key="tone", value="친근")],
    )

    assert result.filled_slots == {"tone": "친근"}


def test_s10_answer_for_unknown_slot_key_is_ignored() -> None:
    draft = IntentDraft()

    result = _normalize(
        draft,
        _spec(slots=[_slot("tone")]),
        answers=[SlotAnswer(slot_key="날씨", value="맑음")],
    )

    assert result.filled_slots == {}


def test_s11_whitespace_only_answer_is_treated_as_unfilled() -> None:
    draft = IntentDraft()

    result = _normalize(
        draft,
        _spec(slots=[_slot("tone")]),
        answers=[SlotAnswer(slot_key="tone", value="   ")],
    )

    assert result.filled_slots == {}
    assert result.missing_slots == ["tone"]


def test_answer_removes_the_matching_question() -> None:
    """답한 축은 다시 묻지 않는다 (I3 와 병합의 결합)."""
    draft = IntentDraft(questions=[_q("tone"), _q("task")])

    result = _normalize(
        draft,
        _spec(slots=[_slot("tone"), _slot("task")]),
        answers=[SlotAnswer(slot_key="tone", value="친근")],
    )

    assert [q.slot_key for q in result.questions] == ["task"]


def test_answer_value_is_stripped() -> None:
    result = _normalize(
        IntentDraft(),
        _spec(slots=[_slot("tone")]),
        answers=[SlotAnswer(slot_key="tone", value="  친근  ")],
    )

    assert result.filled_slots == {"tone": "친근"}


# ===========================================================================
# S12~S14 · I4 — complete 판정 (Plan D5: Policy 가 계산한다)
# ===========================================================================


def test_s12_complete_when_all_required_filled() -> None:
    draft = IntentDraft(filled_slots={"task": "분석"})

    result = _normalize(
        draft, _spec(slots=[_slot("task", required=True), _slot("tone")])
    )

    assert result.complete is True, "optional 축이 비어도 complete 다"
    assert result.missing_slots == ["tone"]


def test_s13_incomplete_when_one_required_missing() -> None:
    draft = IntentDraft(filled_slots={"task": "분석"})

    result = _normalize(
        draft,
        _spec(slots=[_slot("task", required=True), _slot("data", required=True)]),
    )

    assert result.complete is False


def test_s14_complete_when_no_required_slots() -> None:
    """required 가 없으면 공집합 조건이 참이다."""
    result = _normalize(IntentDraft(), _spec(slots=[_slot("tone")]))

    assert result.complete is True


def test_complete_when_spec_has_no_slots() -> None:
    result = _normalize(IntentDraft(label="search", confidence=0.9), _spec())

    assert result.complete is True


def test_answer_can_satisfy_required_slot() -> None:
    result = _normalize(
        IntentDraft(),
        _spec(slots=[_slot("task", required=True)]),
        answers=[SlotAnswer(slot_key="task", value="데이터 분석")],
    )

    assert result.complete is True


# ===========================================================================
# S15~S16 · I5 — 라운드 상한 (무한 되묻기 차단)
# ===========================================================================


def test_s15_questions_are_forced_empty_at_round_cap() -> None:
    """I5: 상한 도달 시 질문을 강제로 비운다. 프롬프트만 믿지 않는다."""
    draft = IntentDraft(questions=[_q("tone")])

    result = _normalize(
        draft, _spec(slots=[_slot("tone")]), round_=2, limits=SlotLimits(max_rounds=2)
    )

    assert result.questions == []


def test_questions_empty_beyond_round_cap() -> None:
    draft = IntentDraft(questions=[_q("tone")])

    result = _normalize(
        draft, _spec(slots=[_slot("tone")]), round_=99, limits=SlotLimits(max_rounds=2)
    )

    assert result.questions == []


def test_s16_questions_survive_below_round_cap() -> None:
    draft = IntentDraft(questions=[_q("tone")])

    result = _normalize(
        draft, _spec(slots=[_slot("tone")]), round_=1, limits=SlotLimits(max_rounds=2)
    )

    assert [q.slot_key for q in result.questions] == ["tone"]


def test_round_cap_does_not_affect_other_fields() -> None:
    """질문만 막고 판정 결과 자체는 그대로 준다."""
    draft = IntentDraft(filled_slots={"tone": "친근"}, suggestions={"task": ["분석"]})

    result = _normalize(
        draft,
        _spec(slots=[_slot("tone"), _slot("task")]),
        round_=2,
        limits=SlotLimits(max_rounds=2),
    )

    assert result.filled_slots == {"tone": "친근"}
    assert result.suggestions == {"task": ["분석"]}
    assert result.missing_slots == ["task"]


# ===========================================================================
# S17 · I6 — degraded
# ===========================================================================


def test_s17_degraded_factory_has_all_extension_fields_empty() -> None:
    """I6: degraded 면 확장 필드가 전부 비고 complete 는 False 다."""
    result = IntentResultPolicy.degraded()

    assert result.degraded is True
    assert result.label is None
    assert result.confidence == pytest.approx(0.0)
    assert result.ambiguous is False
    assert result.filled_slots == {}
    assert result.suggestions == {}
    assert result.questions == []
    assert result.missing_slots == []
    assert result.complete is False


def test_degraded_flag_comes_from_caller_not_draft() -> None:
    """IntentDraft 에는 degraded 필드가 없다 — 호출자만 이 값을 정한다."""
    draft = IntentDraft(label="search", confidence=0.7)

    result = _normalize(draft, _spec(), degraded=True)

    assert result.degraded is True


def test_success_path_is_not_degraded() -> None:
    result = _normalize(IntentDraft(label="search", confidence=0.7), _spec())

    assert result.degraded is False


# ===========================================================================
# 기본 상한 — limits 미지정 시 SlotLimits 기본값을 쓴다 (C3)
# ===========================================================================


def test_default_limits_are_applied_when_omitted() -> None:
    slots = [_slot(k) for k in ("a", "b", "c", "d")]
    draft = IntentDraft(questions=[_q("a"), _q("b"), _q("c"), _q("d")])

    result = _normalize(draft, _spec(slots=slots))

    assert len(result.questions) == 3, "SlotLimits 기본 max_questions=3"


# ===========================================================================
# Act-2 D1 — question.options 폴백
#
# 실 LLM 검증에서 발견: LLM 이 선택지를 options 배열 대신 질문 문장 안에 녹여
# 넣는다("...원하시나요? (예: 요약 통계, 추세 분석 등)"). 그러면 화면이 선택
# 버튼을 만들 수 없다. 같은 정보가 suggestions 에 이미 있으므로 Policy 가 접는다.
# ===========================================================================


def test_d1_question_options_fall_back_to_suggestions() -> None:
    draft = IntentDraft(
        suggestions=[SlotSuggestion(key="tone", options=["격식", "친근"])],
        questions=[SlotQuestionDraft(slot_key="tone", question="어조는?")],
    )

    result = _normalize(draft, _spec(slots=[_slot("tone")]))

    assert result.questions[0].options == ["격식", "친근"]


def test_d1_llm_supplied_question_options_win_over_suggestions() -> None:
    """LLM 이 질문별로 다른 선택지를 줬다면 그쪽이 더 구체적이다."""
    draft = IntentDraft(
        suggestions=[SlotSuggestion(key="tone", options=["격식", "친근"])],
        questions=[
            SlotQuestionDraft(
                slot_key="tone", question="어조는?", options=["아주 격식"]
            )
        ],
    )

    result = _normalize(draft, _spec(slots=[_slot("tone")]))

    assert result.questions[0].options == ["아주 격식"]


def test_d1_fallback_respects_option_cap() -> None:
    draft = IntentDraft(
        suggestions=[SlotSuggestion(key="tone", options=["a", "b", "c", "d", "e"])],
        questions=[SlotQuestionDraft(slot_key="tone", question="어조는?")],
    )

    result = _normalize(
        draft, _spec(slots=[_slot("tone")]), limits=SlotLimits(max_options_per_slot=2)
    )

    assert result.questions[0].options == ["a", "b"]


def test_d1_no_suggestion_leaves_options_empty() -> None:
    """폴백할 데이터가 없으면 빈 채로 둔다 — allow_free_text 가 탈출구다."""
    draft = IntentDraft(
        questions=[SlotQuestionDraft(slot_key="tone", question="어조는?")]
    )

    result = _normalize(draft, _spec(slots=[_slot("tone")]))

    assert result.questions[0].options == []
    assert result.questions[0].allow_free_text is True
