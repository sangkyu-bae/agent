"""서버 소유 intent 스펙 테스트 — Design §3.2 / Plan D5.

스펙은 "슬롯만" 형태의 IntentSpec 이어야 한다 (labels 없음 — 분류가 아니라
정보 수집이 목적). purpose 만 required 다: required 축이 늘어날수록 되묻기
왕복이 길어져 "하나의 엔드포인트" 가치가 줄기 때문이다.
"""
from src.domain.agent_create_pipeline.spec import (
    PURPOSE_SLOT_KEY,
    build_agent_create_spec,
)


def test_spec_is_slots_only() -> None:
    spec = build_agent_create_spec()
    assert spec.labels == []
    assert len(spec.slots) >= 2


def test_purpose_is_the_only_required_slot() -> None:
    spec = build_agent_create_spec()
    required = [s.key for s in spec.slots if s.required]
    assert required == [PURPOSE_SLOT_KEY]


def test_every_slot_has_description() -> None:
    """description 이 곧 LLM 프롬프트 품질이다 (intent 모듈 계약)."""
    for slot in build_agent_create_spec().slots:
        assert slot.description.strip()


def test_builder_returns_fresh_instance() -> None:
    """호출자 간 공유 상태가 없어야 한다 — 스펙 오염 방지."""
    assert build_agent_create_spec() is not build_agent_create_spec()
