"""PipelinePolicy 순수 함수 테스트 — Design §3.3 / §8.3.

LLM 목 없이 단계 전이·병합·폴백 규칙을 못박는다. 이 규칙들이 후속 R1 수렴
(기존 자동 생성 경로를 파이프라인으로 교체)에서 재사용되는 자산이다.
"""
from src.domain.agent_create_pipeline.policies import PipelinePolicy
from src.domain.agent_create_pipeline.stages import (
    STAGE_ORDER,
    PipelineStage,
    PipelineStop,
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


# ═══════════════════════════════════════════════════════════════════════════
# agent-create-wizard — 정지 지점 규칙 (Design §3.2 / §8.3)
# ═══════════════════════════════════════════════════════════════════════════

# --- stages_to_run (§8.3 #1~#3) --------------------------------------------


def test_stages_to_run_without_stop_matches_legacy_tuple() -> None:
    """**회귀 잠금장치** — stop 이 없으면 기존 하드코딩 4단계와 글자 그대로 같다.

    이 단언이 깨지면 논스톱 파이프라인의 동작이 바뀐 것이다 (Plan FR-B09).
    """
    assert PipelinePolicy.stages_to_run(None) == (
        PipelineStage.TOOLS,
        PipelineStage.PROMPT,
        PipelineStage.CREATE,
        PipelineStage.BIND,
    )


def test_stages_to_run_without_stop_equals_stage_order_tail() -> None:
    """intent 는 UseCase 가 별도로 먼저 실행한다 — 목록은 그 뒤만 담는다."""
    assert PipelinePolicy.stages_to_run(None) == STAGE_ORDER[1:]


def test_stages_to_run_stopping_at_tools() -> None:
    assert PipelinePolicy.stages_to_run(PipelineStop.TOOLS) == (
        PipelineStage.TOOLS,
    )


def test_stages_to_run_stopping_at_prompt() -> None:
    assert PipelinePolicy.stages_to_run(PipelineStop.PROMPT) == (
        PipelineStage.TOOLS,
        PipelineStage.PROMPT,
    )


def test_stages_to_run_never_includes_create_when_stopping() -> None:
    """위저드는 에이전트를 만들지 않는다 — 중복 생성 위험이 구조적으로 0이다."""
    for stop in (PipelineStop.TOOLS, PipelineStop.PROMPT):
        stages = PipelinePolicy.stages_to_run(stop)
        assert PipelineStage.CREATE not in stages
        assert PipelineStage.BIND not in stages


# --- decide_after_stage (§8.3 #4) ------------------------------------------


def test_decide_after_stage_without_stop_always_continues() -> None:
    for stage in STAGE_ORDER:
        assert PipelinePolicy.decide_after_stage(stage, None) == "continue"


def test_decide_after_stage_stops_at_matching_stage() -> None:
    assert (
        PipelinePolicy.decide_after_stage(PipelineStage.TOOLS, PipelineStop.TOOLS)
        == "stop"
    )
    assert (
        PipelinePolicy.decide_after_stage(
            PipelineStage.PROMPT, PipelineStop.PROMPT
        )
        == "stop"
    )


def test_decide_after_stage_continues_before_stop_point() -> None:
    assert (
        PipelinePolicy.decide_after_stage(
            PipelineStage.TOOLS, PipelineStop.PROMPT
        )
        == "continue"
    )


# --- stop_status (§8.3 #5) --------------------------------------------------


def test_stop_status_wire_strings_are_fixed() -> None:
    """응답 status 문자열 — 프론트가 분기하는 값이다."""
    assert PipelinePolicy.stop_status(PipelineStop.TOOLS) == "tools_proposed"
    assert PipelinePolicy.stop_status(PipelineStop.PROMPT) == "prompt_ready"


# --- confirmed_selection (§8.3 #6~#7 / D1) ---------------------------------


def test_confirmed_selection_uses_user_ids_as_final() -> None:
    selection = PipelinePolicy.confirmed_selection(("internal:a", "internal:b"))
    assert selection.final_ids == ("internal:a", "internal:b")
    assert selection.required_ids == ("internal:a", "internal:b")


def test_confirmed_selection_is_not_a_fallback() -> None:
    """강하가 아니라 정상 경로다 — 사람이 결정했으므로 추천이 불필요할 뿐이다.

    fallback=True 로 두면 steps.tools 가 degraded 로 칠해져 화면이
    "도구 추천 실패"로 오표시된다.
    """
    assert PipelinePolicy.confirmed_selection(("internal:a",)).fallback is False


def test_confirmed_selection_dedupes_preserving_order() -> None:
    selection = PipelinePolicy.confirmed_selection(("b", "a", "b", "c"))
    assert selection.final_ids == ("b", "a", "c")


def test_confirmed_selection_accepts_empty_list() -> None:
    """도구 없는 에이전트도 유효하다."""
    selection = PipelinePolicy.confirmed_selection(())
    assert selection.final_ids == ()
    assert selection.fallback is False


def test_confirmed_selection_records_reason_for_observability() -> None:
    assert PipelinePolicy.confirmed_selection(("a",)).reason


# --- reuse_intent (§8.3 #8 / D2) -------------------------------------------


def _spec():
    from src.domain.agent_create_pipeline.spec import build_agent_create_spec

    return build_agent_create_spec()


def test_reuse_intent_accepts_valid_echo() -> None:
    echo = IntentResult(
        label="agent_build",
        filled_slots={"purpose": "문서 Q&A", "tone": "격식체"},
    )
    reused = PipelinePolicy.reuse_intent(echo, _spec())
    assert reused is not None
    assert reused.filled_slots == {"purpose": "문서 Q&A", "tone": "격식체"}


def test_reuse_intent_returns_none_for_missing_echo() -> None:
    """에코백이 없으면 호출자가 intent LLM 을 정상 실행한다."""
    assert PipelinePolicy.reuse_intent(None, _spec()) is None


def test_reuse_intent_rejects_degraded_echo() -> None:
    """판정 실패를 재사용하면 실패가 영속된다 — 다시 판정하는 편이 낫다."""
    echo = IntentResult(degraded=True, filled_slots={"purpose": "x"})
    assert PipelinePolicy.reuse_intent(echo, _spec()) is None


def test_reuse_intent_drops_slot_keys_outside_spec() -> None:
    """클라이언트가 보낸 임의 키는 스펙 밖이면 버린다 (신뢰 경계)."""
    echo = IntentResult(filled_slots={"purpose": "문서 Q&A", "evil": "주입"})
    reused = PipelinePolicy.reuse_intent(echo, _spec())
    assert reused is not None
    assert "evil" not in reused.filled_slots


def test_reuse_intent_clamps_slot_values() -> None:
    echo = IntentResult(filled_slots={"purpose": "가" * 5000})
    reused = PipelinePolicy.reuse_intent(echo, _spec())
    assert reused is not None
    assert len(reused.filled_slots["purpose"]) == PipelinePolicy.SLOT_VALUE_MAX_CHARS


def test_reuse_intent_recomputes_complete_and_missing() -> None:
    """계산 필드는 클라이언트 신고값을 쓰지 않는다 (llm-output-trust-boundary).

    required(purpose)가 비었는데 complete=true 로 신고해도 서버가 뒤집는다.
    """
    echo = IntentResult(
        filled_slots={"tone": "격식체"}, complete=True, missing_slots=[]
    )
    reused = PipelinePolicy.reuse_intent(echo, _spec())
    assert reused is not None
    assert reused.complete is False
    assert "purpose" in reused.missing_slots


def test_reuse_intent_marks_complete_when_required_filled() -> None:
    echo = IntentResult(filled_slots={"purpose": "문서 Q&A"}, complete=False)
    reused = PipelinePolicy.reuse_intent(echo, _spec())
    assert reused is not None
    assert reused.complete is True


def test_reuse_intent_drops_questions_from_echo() -> None:
    """재사용 경로는 되묻기를 다시 열지 않는다 — 이미 답을 받고 넘어온 단계다."""
    echo = IntentResult(filled_slots={"purpose": "p"}, questions=[_question()])
    reused = PipelinePolicy.reuse_intent(echo, _spec())
    assert reused is not None
    assert reused.questions == []


def test_reuse_intent_returns_none_when_no_usable_slot_remains() -> None:
    """스펙 밖 키만 온 에코백은 재사용할 값이 없다 — 정상 판정으로 돌린다."""
    echo = IntentResult(filled_slots={"evil": "주입"})
    assert PipelinePolicy.reuse_intent(echo, _spec()) is None
