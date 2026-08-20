"""PipelinePolicy 순수 함수 테스트 — Design §3.3 / §8.3.

LLM 목 없이 단계 전이·병합·폴백 규칙을 못박는다. 이 규칙들이 후속 R1 수렴
(기존 자동 생성 경로를 파이프라인으로 교체)에서 재사용되는 자산이다.
"""
from src.domain.agent_create_pipeline.policies import PipelinePolicy
from src.domain.agent_create_pipeline.stages import (
    STAGE_ORDER,
    PipelineStage,
    StageRecord,
    StageStatus,
)
from src.domain.intent.schemas import IntentResult, SlotQuestion


def _question() -> SlotQuestion:
    return SlotQuestion(slot_key="purpose", question="핵심 용도는 무엇인가요?")


# --- decide_after_intent (§8.3 #1) -----------------------------------------


def test_complete_intent_proceeds() -> None:
    result = IntentResult(complete=True)
    assert PipelinePolicy.decide_after_intent(result) == "proceed"


def test_incomplete_with_questions_asks() -> None:
    result = IntentResult(complete=False, questions=[_question()])
    assert PipelinePolicy.decide_after_intent(result) == "ask"


def test_degraded_incomplete_proceeds_without_asking() -> None:
    """FR-07 — 판정 실패는 되묻기 불능이다. 의도 없이 진행한다."""
    result = IntentResult(complete=False, degraded=True, questions=[_question()])
    assert PipelinePolicy.decide_after_intent(result) == "proceed"


def test_incomplete_without_questions_proceeds() -> None:
    """물을 것이 없는 미충족은 진행 — 빈 되묻기 왕복은 무한 루프다."""
    result = IntentResult(complete=False, questions=[])
    assert PipelinePolicy.decide_after_intent(result) == "proceed"


# --- build_selector_query ---------------------------------------------------


def test_query_includes_filled_slots() -> None:
    result = IntentResult(
        complete=True, filled_slots={"purpose": "여신 문서 Q&A", "tone": "격식체"}
    )
    query = PipelinePolicy.build_selector_query("에이전트 만들어줘", result)
    assert query.startswith("에이전트 만들어줘")
    assert "purpose: 여신 문서 Q&A" in query
    assert "tone: 격식체" in query


def test_query_is_request_only_when_intent_missing_or_degraded() -> None:
    assert PipelinePolicy.build_selector_query("요청", None) == "요청"
    degraded = IntentResult(degraded=True, filled_slots={"purpose": "오염값"})
    assert PipelinePolicy.build_selector_query("요청", degraded) == "요청"


# --- resolve_tool_ids / empty_candidate_selection ---------------------------


def test_resolve_tool_ids_returns_final_ids_verbatim() -> None:
    """선별 결과의 final_ids 를 그대로 신뢰한다 — required 포함은 포트 계약."""
    selection = PipelinePolicy.empty_candidate_selection(["internal:a"])
    assert PipelinePolicy.resolve_tool_ids(selection) == ("internal:a",)


def test_empty_candidate_selection_is_fallback_with_user_ids_only() -> None:
    selection = PipelinePolicy.empty_candidate_selection(
        ["internal:a", "internal:b", "internal:a"]
    )
    assert selection.fallback is True
    assert selection.selected_ids == ()
    assert selection.final_ids == ("internal:a", "internal:b")  # 순서 보존 dedupe
    assert selection.candidate_count == 0
    assert selection.reason


# --- resolve_agent_name -----------------------------------------------------


def test_explicit_name_wins() -> None:
    result = IntentResult(filled_slots={"purpose": "문서 Q&A"})
    name = PipelinePolicy.resolve_agent_name("  내 에이전트  ", result, "요청")
    assert name == "내 에이전트"


def test_purpose_slot_is_second_priority() -> None:
    result = IntentResult(filled_slots={"purpose": "여신 심사 문서 Q&A"})
    assert (
        PipelinePolicy.resolve_agent_name(None, result, "요청")
        == "여신 심사 문서 Q&A"
    )


def test_degraded_intent_slots_are_not_trusted_for_name() -> None:
    result = IntentResult(degraded=True, filled_slots={"purpose": "오염값"})
    name = PipelinePolicy.resolve_agent_name(None, result, "검색 에이전트 만들어줘")
    assert name == "검색 에이전트 만들어줘"


def test_request_preview_fallback_is_30_chars() -> None:
    long_request = "가" * 100
    name = PipelinePolicy.resolve_agent_name(None, None, long_request)
    assert name == "가" * 30


def test_name_clamped_to_200_chars() -> None:
    assert len(PipelinePolicy.resolve_agent_name("가" * 300, None, "요청")) == 200


# --- clamp_prompt (§8.3 4000 경계) ------------------------------------------


def test_prompt_at_or_below_limit_is_untouched() -> None:
    for length in (3999, 4000):
        clamped, reason = PipelinePolicy.clamp_prompt("a" * length)
        assert len(clamped) == length
        assert reason is None


def test_prompt_over_limit_is_truncated_with_reason() -> None:
    clamped, reason = PipelinePolicy.clamp_prompt("a" * 4001)
    assert len(clamped) == 4000
    assert reason is not None and "4001" in reason


# --- finalize_steps ---------------------------------------------------------


def test_missing_stages_are_filled_as_skipped_in_fixed_order() -> None:
    done = [StageRecord(PipelineStage.INTENT, StageStatus.OK, elapsed_ms=10)]
    steps = PipelinePolicy.finalize_steps(done, skip_reason="need_input")
    assert [s.stage for s in steps] == list(STAGE_ORDER)
    assert steps[0].status is StageStatus.OK
    assert all(s.status is StageStatus.SKIPPED for s in steps[1:])
    assert all(s.reason == "need_input" for s in steps[1:])


def test_full_records_pass_through_unchanged() -> None:
    done = [StageRecord(stage, StageStatus.OK) for stage in STAGE_ORDER]
    steps = PipelinePolicy.finalize_steps(done, skip_reason="unused")
    assert steps == tuple(done)


# --- clamp_round ------------------------------------------------------------


def test_round_is_reclamped_server_side() -> None:
    """클라이언트 신고값 불신 — stateless-hitl 위키 패턴."""
    assert PipelinePolicy.clamp_round(-1, max_rounds=2) == 0
    assert PipelinePolicy.clamp_round(0, max_rounds=2) == 0
    assert PipelinePolicy.clamp_round(99, max_rounds=2) == 2
