"""AGENT_BUILD_SLOTS 프리셋 무결성 테스트 (Design §8.2 S32).

프리셋은 순수 데이터이므로 검증할 것은 "판정 품질을 망가뜨리는 실수가 없는가"뿐이다.
이번 사이클엔 소비자가 없으므로(Plan R6), 이 테스트가 프리셋의 유일한 계약이다.
"""
from src.application.agent_composer.build_slots import AGENT_BUILD_SLOTS
from src.domain.intent.schemas import IntentSpec, SlotSpec

_EXPECTED_KEYS = ["task", "domain_detail", "data_source", "output_format", "tone"]
_EXPECTED_REQUIRED = {"task", "domain_detail", "data_source"}


def test_preset_declares_the_five_axes() -> None:
    assert [slot.key for slot in AGENT_BUILD_SLOTS] == _EXPECTED_KEYS


def test_every_entry_is_a_slot_spec() -> None:
    assert all(isinstance(slot, SlotSpec) for slot in AGENT_BUILD_SLOTS)


def test_keys_are_unique() -> None:
    keys = [slot.key for slot in AGENT_BUILD_SLOTS]

    assert len(keys) == len(set(keys))


def test_every_description_is_meaningful() -> None:
    """description 이 곧 프롬프트다 — key 를 그대로 베끼면 판정 품질이 떨어진다."""
    for slot in AGENT_BUILD_SLOTS:
        assert slot.description.strip(), f"{slot.key} 에 설명이 없다"
        assert slot.description != slot.key, f"{slot.key} 설명이 key 와 같다"


def test_required_axes_are_the_three_that_block_drafting() -> None:
    """앞 3축은 없으면 초안을 만들 수 없다 (Design §4.5).

    뒤 2축은 합리적 기본값이 있으므로 되묻기 예산을 앞 3축에 몰아준다.
    """
    required = {slot.key for slot in AGENT_BUILD_SLOTS if slot.required}

    assert required == _EXPECTED_REQUIRED


def test_every_axis_offers_option_hints() -> None:
    """options 는 LLM 앵커링용이다 — 없으면 추천 품질이 흔들린다 (Plan R4)."""
    for slot in AGENT_BUILD_SLOTS:
        assert len(slot.options) >= 2, f"{slot.key} 에 선택지 힌트가 부족하다"


def test_free_text_is_always_allowed() -> None:
    """선택지 밖 답변을 막으면 위키 계약 2(목록 프레이밍 과차단)를 재현한다."""
    assert all(slot.allow_free_text for slot in AGENT_BUILD_SLOTS)


def test_preset_forms_a_valid_slots_only_spec() -> None:
    """분류 라벨 없이 이 프리셋만으로 IntentSpec 이 성립해야 한다 (FR-16)."""
    spec = IntentSpec(slots=AGENT_BUILD_SLOTS)

    assert spec.labels == []
    assert len(spec.slots) == len(_EXPECTED_KEYS)


def test_preset_is_not_mutated_by_spec_construction() -> None:
    """모듈 상수가 호출자에 의해 오염되면 다음 호출이 조용히 달라진다."""
    before = [slot.model_copy(deep=True) for slot in AGENT_BUILD_SLOTS]

    IntentSpec(slots=AGENT_BUILD_SLOTS)

    assert [slot.model_dump() for slot in AGENT_BUILD_SLOTS] == [
        slot.model_dump() for slot in before
    ]
