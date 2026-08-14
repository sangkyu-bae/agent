"""IntentResultPolicy 단위 테스트.

Design §8.2 시나리오 1~9. 순수 함수이므로 LLM·IO 없이 분기 100% 커버한다.
"""
import pytest
from src.domain.intent.policies import IntentResultPolicy
from src.domain.intent.schemas import IntentLabel, IntentResult, IntentSpec


def _spec(slots: list[str] | None = None) -> IntentSpec:
    return IntentSpec(
        labels=[
            IntentLabel(name="search", description="근거 문서를 찾아야 하는 질문"),
            IntentLabel(name="analysis", description="데이터를 계산·비교하는 질문"),
        ],
        slots=slots or [],
    )


# --- 시나리오 1: spec 안의 label 은 그대로 통과 -----------------------------


def test_label_in_spec_passes_through() -> None:
    raw = IntentResult(label="search", confidence=0.82, reason="근거 필요")

    result = IntentResultPolicy.normalize(raw, _spec())

    assert result.label == "search"
    assert result.confidence == pytest.approx(0.82)
    assert result.ambiguous is False
    assert result.degraded is False
    assert result.reason == "근거 필요"


# --- 시나리오 2: spec 밖 label 은 강등 (E7 — degraded 아님) ------------------


def test_label_outside_spec_is_demoted_not_degraded() -> None:
    raw = IntentResult(label="weather", confidence=0.9)

    result = IntentResultPolicy.normalize(raw, _spec())

    assert result.label is None
    assert result.ambiguous is True
    assert result.degraded is False, "정상 판정이므로 시스템 장애(degraded)가 아니다"


def test_empty_label_is_not_marked_ambiguous() -> None:
    """빈 label 은 '해당 없음' 탈출구(Design §4.3)이지 후보가 갈린 것이 아니다."""
    raw = IntentResult(label="", confidence=0.4)

    result = IntentResultPolicy.normalize(raw, _spec())

    assert result.label is None
    assert result.ambiguous is False


# --- 시나리오 3: label 이 없으면 confidence 는 0 ----------------------------


def test_none_label_forces_zero_confidence() -> None:
    raw = IntentResult(label=None, confidence=0.9)

    result = IntentResultPolicy.normalize(raw, _spec())

    assert result.label is None
    assert result.confidence == pytest.approx(0.0)


def test_demoted_label_also_forces_zero_confidence() -> None:
    raw = IntentResult(label="weather", confidence=0.95)

    result = IntentResultPolicy.normalize(raw, _spec())

    assert result.confidence == pytest.approx(0.0)


# --- 시나리오 4~5: confidence clamp ----------------------------------------


def test_confidence_above_one_is_clamped() -> None:
    raw = IntentResult(label="search", confidence=1.7)

    assert IntentResultPolicy.normalize(raw, _spec()).confidence == pytest.approx(1.0)


def test_negative_confidence_is_clamped() -> None:
    raw = IntentResult(label="search", confidence=-0.3)

    assert IntentResultPolicy.normalize(raw, _spec()).confidence == pytest.approx(0.0)


# --- 시나리오 6~7: missing_slots 필터 --------------------------------------


def test_missing_slots_filtered_to_requested_slots() -> None:
    raw = IntentResult(label="search", confidence=0.5, missing_slots=["기간", "날씨"])

    result = IntentResultPolicy.normalize(raw, _spec(slots=["기간"]))

    assert result.missing_slots == ["기간"]


def test_missing_slots_empty_when_no_slots_requested() -> None:
    raw = IntentResult(label="search", confidence=0.5, missing_slots=["기간"])

    result = IntentResultPolicy.normalize(raw, _spec())

    assert result.missing_slots == []


def test_entities_are_not_filtered() -> None:
    """entities 는 필터하지 않는다 — 호출자가 요청하지 않은 부가 추출도 유용하다."""
    raw = IntentResult(
        label="search", confidence=0.5, entities={"기간": "2024", "부서": "여신"}
    )

    result = IntentResultPolicy.normalize(raw, _spec(slots=["기간"]))

    assert result.entities == {"기간": "2024", "부서": "여신"}


# --- 시나리오 8: LLM 이 채운 degraded 는 절대 신뢰하지 않는다 (§2.4 / E9) ----


def test_llm_supplied_degraded_true_is_overridden_on_success_path() -> None:
    raw = IntentResult(label="search", confidence=0.7, degraded=True)

    result = IntentResultPolicy.normalize(raw, _spec())

    assert result.degraded is False, "성공 경로에서는 LLM 의 degraded 값을 무시한다"


def test_degraded_flag_comes_from_caller_not_payload() -> None:
    raw = IntentResult(label="search", confidence=0.7, degraded=False)

    result = IntentResultPolicy.normalize(raw, _spec(), degraded=True)

    assert result.degraded is True


# --- 시나리오 9: degraded() 팩토리 ------------------------------------------


def test_degraded_factory_returns_unknown_result() -> None:
    result = IntentResultPolicy.degraded()

    assert result.label is None
    assert result.confidence == pytest.approx(0.0)
    assert result.degraded is True
    assert result.ambiguous is False
    assert result.entities == {}
    assert result.missing_slots == []


# --- spec 검증 (FR-11) ------------------------------------------------------


def test_spec_requires_at_least_two_labels() -> None:
    with pytest.raises(ValueError):
        IntentSpec(labels=[IntentLabel(name="search", description="설명")])


def test_label_description_is_required() -> None:
    with pytest.raises(ValueError):
        IntentLabel(name="search", description="")
