"""intent 도메인 스키마 검증 테스트.

Design §8.2 시나리오 S18~S24 — SlotSpec 승격과 spec 검증 규칙.
pydantic validator 만 검증하므로 LLM·IO 가 없다.
"""
import pytest
from pydantic import ValidationError
from src.domain.intent.schemas import (
    IntentDraft,
    IntentLabel,
    IntentResult,
    IntentSpec,
    SlotAnswer,
    SlotLimits,
    SlotQuestion,
    SlotQuestionDraft,
    SlotSpec,
)


def _labels() -> list[IntentLabel]:
    return [
        IntentLabel(name="search", description="근거 문서를 찾아야 하는 질문"),
        IntentLabel(name="analysis", description="데이터를 계산·비교하는 질문"),
    ]


# --- S18~S19: slots 하위호환 승격 (FR-02) -----------------------------------


def test_str_slots_are_promoted_to_slot_spec() -> None:
    """구형 list[str] 입력이 SlotSpec 으로 승격된다 — 기존 호출부 무파손."""
    spec = IntentSpec(labels=_labels(), slots=["기간"])

    assert len(spec.slots) == 1
    assert isinstance(spec.slots[0], SlotSpec)
    assert spec.slots[0].key == "기간"
    assert spec.slots[0].description == "기간", "key 를 description 으로도 쓴다"
    assert spec.slots[0].required is False
    assert spec.slots[0].allow_free_text is True


def test_slot_spec_slots_pass_through() -> None:
    slot = SlotSpec(key="tone", description="답변 어조", required=True)

    spec = IntentSpec(labels=_labels(), slots=[slot])

    assert spec.slots[0].key == "tone"
    assert spec.slots[0].required is True


def test_mixed_str_and_slot_spec_are_both_accepted() -> None:
    spec = IntentSpec(
        labels=_labels(),
        slots=["기간", SlotSpec(key="tone", description="답변 어조")],
    )

    assert [s.key for s in spec.slots] == ["기간", "tone"]


# --- S20~S23: labels / slots 조건 (FR-16) -----------------------------------


def test_slots_only_spec_is_allowed() -> None:
    """에이전트 생성은 분류 라벨 없이 슬롯만 쓴다 — 이제 허용된다."""
    spec = IntentSpec(slots=[SlotSpec(key="tone", description="답변 어조")])

    assert spec.labels == []
    assert len(spec.slots) == 1


def test_labels_only_spec_is_allowed() -> None:
    spec = IntentSpec(labels=_labels())

    assert spec.slots == []


def test_single_label_is_rejected() -> None:
    """라벨이 1개면 분류가 성립하지 않는다."""
    with pytest.raises(ValidationError):
        IntentSpec(labels=[IntentLabel(name="search", description="설명")])


def test_single_label_rejected_even_with_slots() -> None:
    with pytest.raises(ValidationError):
        IntentSpec(
            labels=[IntentLabel(name="search", description="설명")],
            slots=[SlotSpec(key="tone", description="답변 어조")],
        )


def test_empty_labels_and_empty_slots_is_rejected() -> None:
    with pytest.raises(ValidationError):
        IntentSpec()


# --- S24: 필수 description --------------------------------------------------


def test_slot_description_is_required() -> None:
    with pytest.raises(ValidationError):
        SlotSpec(key="tone", description="")


def test_slot_key_is_required() -> None:
    with pytest.raises(ValidationError):
        SlotSpec(key="", description="답변 어조")


def test_label_description_is_required() -> None:
    with pytest.raises(ValidationError):
        IntentLabel(name="search", description="")


# --- SlotAnswer / SlotQuestion ---------------------------------------------


def test_slot_answer_rejects_empty_value() -> None:
    """빈 답변은 '답하지 않음'이며 애초에 보내지 않는다."""
    with pytest.raises(ValidationError):
        SlotAnswer(slot_key="tone", value="")


def test_slot_question_defaults_allow_free_text() -> None:
    q = SlotQuestion(slot_key="tone", question="어떤 어조를 원하시나요?")

    assert q.options == []
    assert q.allow_free_text is True


def test_slot_question_draft_has_no_allow_free_text() -> None:
    """allow_free_text 는 SlotSpec 에서 오지 LLM 이 정하지 않는다."""
    assert "allow_free_text" not in SlotQuestionDraft.model_fields


# --- IntentDraft: LLM 이 채울 수 있는 필드만 가진다 (Design §2.4) -------------


def test_intent_draft_excludes_system_computed_fields() -> None:
    """complete / missing_slots / degraded 는 LLM 이 볼 수 없어야 한다."""
    fields = set(IntentDraft.model_fields)

    assert "complete" not in fields
    assert "missing_slots" not in fields
    assert "degraded" not in fields


def test_intent_draft_defaults_are_empty() -> None:
    draft = IntentDraft()

    assert draft.label is None
    assert draft.confidence == pytest.approx(0.0)
    assert draft.filled_slots == []
    assert draft.suggestions == []
    assert draft.questions == []


# --- IntentResult: entities 는 제거되었다 (Plan D9) ---------------------------


def test_intent_result_has_no_entities_field() -> None:
    assert "entities" not in IntentResult.model_fields
    assert "filled_slots" in IntentResult.model_fields


def test_intent_result_defaults() -> None:
    result = IntentResult()

    assert result.filled_slots == {}
    assert result.suggestions == {}
    assert result.questions == []
    assert result.missing_slots == []
    assert result.complete is False
    assert result.degraded is False


# --- SlotLimits -------------------------------------------------------------


def test_slot_limits_defaults_match_planner_policy() -> None:
    """agent_composer PlannerPolicy 와 기본값을 맞춰 둔다 (Design §4.4)."""
    limits = SlotLimits()

    assert limits.max_rounds == 2
    assert limits.max_questions == 3
    assert limits.max_options_per_slot == 4


# --- OpenAI strict structured outputs 호환성 (Act-1 회귀 방어) ---------------
#
# 실 LLM 검증(M5)에서 발견: 자유 키 dict(`dict[str, X]`)가 하나라도 있으면
# OpenAI structured outputs 가 400 을 반환해 판정이 **항상** degraded 로 떨어진다.
# 선행 사이클의 `IntentResult(entities: dict[str,str])` 도 같은 이유로 깨져 있었고,
# 미배선 + degraded 폴백이 그 사실을 가려 왔다.
#
# 아래 테스트는 그 결함을 구조적으로 재발 불가능하게 만든다.


def _free_key_dict_paths(schema: dict, path: str = "") -> list[str]:
    """스키마에서 자유 키 dict(additionalProperties 가 스키마인 object)를 찾는다."""
    found: list[str] = []
    if isinstance(schema, dict):
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            found.append(path or "<root>")
        for key, value in schema.items():
            if key == "additionalProperties":
                continue
            found += _free_key_dict_paths(value, f"{path}.{key}" if path else key)
    elif isinstance(schema, list):
        for i, item in enumerate(schema):
            found += _free_key_dict_paths(item, f"{path}[{i}]")
    return found


def test_intent_draft_schema_has_no_free_key_dict() -> None:
    """IntentDraft 는 LLM 이 보는 유일한 스키마다 — strict 모드를 깨면 안 된다."""
    paths = _free_key_dict_paths(IntentDraft.model_json_schema())

    assert paths == [], f"자유 키 dict 발견: {paths}"


def test_intent_draft_slot_fields_are_lists() -> None:
    props = IntentDraft.model_json_schema()["properties"]

    for field in ("filled_slots", "suggestions", "questions"):
        assert props[field]["type"] == "array", f"{field} 가 배열이 아니다"


def test_intent_draft_accepts_dict_shaped_slots() -> None:
    """dict 로 오는 구현체(function_calling 등)도 받아들인다 — 입력 관용."""
    draft = IntentDraft.model_validate(
        {
            "filled_slots": {"tone": "친근"},
            "suggestions": {"task": ["분석", "요약"]},
        }
    )

    assert draft.filled_slots[0].key == "tone"
    assert draft.filled_slots[0].value == "친근"
    assert draft.suggestions[0].key == "task"
    assert draft.suggestions[0].options == ["분석", "요약"]


def test_intent_draft_accepts_list_shaped_slots() -> None:
    draft = IntentDraft.model_validate(
        {
            "filled_slots": [{"key": "tone", "value": "친근"}],
            "suggestions": [{"key": "task", "options": ["분석"]}],
        }
    )

    assert draft.filled_slots[0].key == "tone"
    assert draft.suggestions[0].options == ["분석"]


def test_intent_result_may_keep_dicts() -> None:
    """도메인 VO·API 응답은 dict 를 유지한다 — LLM 이 보지 않는 타입이다."""
    props = IntentResult.model_json_schema()["properties"]

    assert props["filled_slots"]["type"] == "object"
    assert props["suggestions"]["type"] == "object"
