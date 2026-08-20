"""서버 소유 intent 스펙 테스트 — Design §3.2 / Plan D5.

스펙은 "슬롯만" 형태의 IntentSpec 이어야 한다 (labels 없음 — 분류가 아니라
정보 수집이 목적). purpose 만 required 다: required 축이 늘어날수록 되묻기
왕복이 길어져 "하나의 엔드포인트" 가치가 줄기 때문이다.

prompt-depth §3.5 — 축이 6개가 됐다. 신규 2축(constraints/decision_priority)은
"LLM 이 추측하면 위험한 것"이며, 둘 다 optional 이라 상세히 쓴 1문장 요청은
여전히 되묻기 없이 통과한다 (SC-4).
"""
from src.domain.agent_create_pipeline.spec import (
    PURPOSE_SLOT_KEY,
    build_agent_create_spec,
)
from src.infrastructure.config.intent_config import IntentConfig


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


# ── prompt-depth: 신규 2축 (FR-14 / FR-15 / FR-16) ──────────────────────────


def test_spec_has_six_axes() -> None:
    keys = [s.key for s in build_agent_create_spec().slots]
    assert keys == [
        PURPOSE_SLOT_KEY,
        "target_users",
        "data_sources",
        "tone",
        "constraints",
        "decision_priority",
    ]


def test_new_axes_are_optional() -> None:
    """required 면 '간단한 봇 하나'에도 되묻기를 강요한다 (사용자 결정)."""
    by_key = {s.key: s for s in build_agent_create_spec().slots}
    assert by_key["constraints"].required is False
    assert by_key["decision_priority"].required is False


def test_new_axes_offer_options_within_limit() -> None:
    """옵션 수는 INTENT_MAX_OPTIONS_PER_SLOT 이내여야 잘리지 않는다."""
    limit = IntentConfig().INTENT_MAX_OPTIONS_PER_SLOT
    by_key = {s.key: s for s in build_agent_create_spec().slots}
    for key in ("constraints", "decision_priority"):
        assert by_key[key].options
        assert len(by_key[key].options) <= limit


# ── prompt-depth: 되묻기 라운드 상한 (FR-17) ────────────────────────────────


def test_clarification_rounds_default_is_three() -> None:
    """6축을 회당 3개씩 물으면 2라운드로 부족하다 (사용자 결정)."""
    assert IntentConfig().INTENT_MAX_CLARIFICATION_ROUNDS == 3


def test_slot_limits_carry_the_new_round_cap() -> None:
    """단일 출처 — 어댑터 프롬프트와 파이프라인 clamp 가 같은 값을 본다."""
    assert IntentConfig().slot_limits().max_rounds == 3


def test_questions_per_round_cap_is_unchanged() -> None:
    """FR-18 — 축이 늘어도 한 번에 3개를 넘겨 묻지 않는다."""
    assert IntentConfig().slot_limits().max_questions == 3


# ── prompt-depth: 프롬프트 길이 상한 정합 (FR-20~22 / Plan R-08) ────────────
#
# 상한이 정의된 4곳 중 하나만 어긋나도 사용자는 **마지막 저장 단계에서** 422 를
# 만난다 — 앞선 모든 단계를 통과한 뒤라 가장 비싼 실패다. 값 자체를 테스트로
# 묶어 어느 한 곳만 바뀌는 일을 막는다.


def test_prompt_length_caps_agree_across_layers() -> None:
    from src.application.agent_builder.schemas import (
        CreateAgentRequest,
        UpdateAgentRequest,
    )
    from src.domain.agent_create_pipeline.policies import PipelinePolicy
    from src.interfaces.schemas.prompt_composer import MAX_ASSEMBLED_CHARS

    def _cap(model, field: str) -> int:
        for meta in model.model_fields[field].metadata:
            if hasattr(meta, "max_length"):
                return meta.max_length
        raise AssertionError(f"{model.__name__}.{field} 에 max_length 가 없다")

    assert PipelinePolicy.PROMPT_MAX_CHARS == 8000
    assert MAX_ASSEMBLED_CHARS == 8000
    assert _cap(CreateAgentRequest, "system_prompt") == 8000
    assert _cap(UpdateAgentRequest, "system_prompt") == 8000


def test_clamp_prompt_boundary() -> None:
    """FR-21 — 8000 은 통과, 8001 은 절단 + 사유."""
    from src.domain.agent_create_pipeline.policies import PipelinePolicy

    cap = PipelinePolicy.PROMPT_MAX_CHARS
    kept, reason = PipelinePolicy.clamp_prompt("가" * cap)
    assert len(kept) == cap and reason is None

    cut, reason = PipelinePolicy.clamp_prompt("가" * (cap + 1))
    assert len(cut) == cap
    assert reason is not None and str(cap) in reason
