"""정지 지점이 있는 파이프라인 실행 — agent-create-wizard Design §2.2 / §4.3.

위저드는 intent → tools → prompt 까지만 실행하고 create/bind 에 도달하지 않는다.
협력자 fake 와 builder 는 논스톱 테스트(`test_use_case`)와 공유한다 — 같은
UseCase 를 검증하므로 대역이 갈라지면 두 경로의 전제가 어긋난다.
"""
from src.application.agent_create_pipeline.events import StageEvent
from src.domain.agent_create_pipeline.policies import PipelinePolicy
from src.domain.agent_create_pipeline.stages import PipelineStop, StageStatus
from src.domain.intent.schemas import IntentResult, SlotQuestion

from tests.application.agent_create_pipeline.test_use_case import (
    FakeComposeUC,
    FakeIntentUC,
    _compose_result,
    _drain,
    _intent_ok,
    _outcome,
    _pipeline,
    _selection,
)


def _stages_of(events) -> list[str]:
    """stage_started 이벤트로 실제 실행된 단계 순서를 복원한다."""
    return [
        e.record.stage.value
        for e in events
        if isinstance(e, StageEvent) and e.kind == "stage_started"
    ]


def _step(outcome, stage: str):
    return {s.stage.value: s for s in outcome.steps}[stage]


# ── stop_after="tools" ──────────────────────────────────────────────────────


async def test_stop_after_tools_returns_tools_proposed() -> None:
    use_case, _ = _pipeline()
    events = await _drain(use_case, stop_after=PipelineStop.TOOLS)

    assert _outcome(events).status == "tools_proposed"
    assert _stages_of(events) == ["intent", "tools"]


async def test_stop_after_tools_does_not_create_agent() -> None:
    """위저드는 에이전트를 만들지 않는다 — 중복 생성 위험이 구조적으로 0이다."""
    use_case, fakes = _pipeline()
    await _drain(use_case, stop_after=PipelineStop.TOOLS)

    assert fakes["create"].calls == []
    assert fakes["compose"].compose_calls == []
    assert fakes["compose"].bind_calls == []


async def test_stop_after_tools_exposes_recommendations() -> None:
    use_case, _ = _pipeline(
        selection=_selection(
            final=("internal:a", "internal:b"),
            selected=("internal:a", "internal:b"),
        )
    )
    outcome = _outcome(await _drain(use_case, stop_after=PipelineStop.TOOLS))
    assert outcome.recommended_tool_ids == ("internal:a", "internal:b")
    assert outcome.final_tool_ids == ("internal:a", "internal:b")


async def test_stop_after_tools_fills_remaining_steps_as_skipped() -> None:
    """steps 는 정지해도 항상 5개다 — 화면이 단계 바를 고정 렌더한다 (§4.3)."""
    use_case, _ = _pipeline()
    outcome = _outcome(await _drain(use_case, stop_after=PipelineStop.TOOLS))

    assert len(outcome.steps) == 5
    for stage in ("prompt", "create", "bind"):
        assert _step(outcome, stage).status == StageStatus.SKIPPED
        assert _step(outcome, stage).reason == "stopped_for_review"


async def test_stop_after_tools_suggests_agent_name() -> None:
    """스튜디오 프리필용 이름 후보 — 서버가 제안하고 사용자가 고친다."""
    use_case, _ = _pipeline()
    outcome = _outcome(await _drain(use_case, stop_after=PipelineStop.TOOLS))
    assert outcome.suggested_name == "문서 Q&A"


# ── need_input 이 정지 지점보다 우선 ────────────────────────────────────────


async def test_need_input_wins_over_stop_after() -> None:
    """되묻기가 남았으면 도구 추천으로 넘어가지 않는다."""
    intent = FakeIntentUC(
        _intent_ok(
            complete=False,
            filled_slots={},
            questions=[SlotQuestion(slot_key="purpose", question="용도는?")],
        )
    )
    use_case, fakes = _pipeline(intent=intent)
    events = await _drain(use_case, stop_after=PipelineStop.TOOLS)

    assert _outcome(events).status == "need_input"
    assert _stages_of(events) == ["intent"]
    assert fakes["selector"].calls == []


# ── stop_after="prompt" + tools_confirmed (D1) ──────────────────────────────


async def test_stop_after_prompt_returns_prompt_ready() -> None:
    use_case, _ = _pipeline()
    events = await _drain(
        use_case,
        stop_after=PipelineStop.PROMPT,
        tools_confirmed=True,
        tool_ids=("internal:a",),
    )
    outcome = _outcome(events)
    assert outcome.status == "prompt_ready"
    assert _stages_of(events) == ["intent", "tools", "prompt"]
    assert outcome.session_id == "ps1"
    assert outcome.version_id == "pv1"
    assert outcome.assembled_prompt == "조립된 프롬프트"


async def test_confirmed_tools_skip_the_selector() -> None:
    """D1 — 확정 후에는 셀렉터를 돌리지 않는다."""
    use_case, fakes = _pipeline()
    await _drain(
        use_case,
        stop_after=PipelineStop.PROMPT,
        tools_confirmed=True,
        tool_ids=("internal:a",),
    )
    assert fakes["selector"].calls == []


async def test_confirmed_tools_are_not_re_expanded_by_selector() -> None:
    """**D1 회귀 방지** — 사용자가 제거한 도구가 되살아나면 안 된다.

    셀렉터가 internal:b 를 추천하도록 두고 사용자는 internal:a 만 확정한
    상황이다. tools_confirmed 가 없으면 final = 셀렉터출력 ∪ 확정목록 이 된다.
    """
    use_case, fakes = _pipeline(
        selection=_selection(
            final=("internal:a", "internal:b"), selected=("internal:b",)
        )
    )
    outcome = _outcome(
        await _drain(
            use_case,
            stop_after=PipelineStop.PROMPT,
            tools_confirmed=True,
            tool_ids=("internal:a",),
        )
    )
    assert outcome.final_tool_ids == ("internal:a",)
    assert fakes["compose"].compose_calls[0]["tool_ids"] == ("internal:a",)


async def test_confirmed_tools_stage_is_ok_not_degraded() -> None:
    """추천 생략은 강하가 아니다 — degraded 면 화면이 '추천 실패'로 오표시한다."""
    use_case, _ = _pipeline()
    outcome = _outcome(
        await _drain(
            use_case,
            stop_after=PipelineStop.PROMPT,
            tools_confirmed=True,
            tool_ids=("internal:a",),
        )
    )
    assert _step(outcome, "tools").status == StageStatus.OK
    assert _step(outcome, "tools").reason


async def test_confirmed_empty_tools_is_allowed() -> None:
    """도구 없는 에이전트도 유효하다."""
    use_case, _ = _pipeline()
    outcome = _outcome(
        await _drain(
            use_case,
            stop_after=PipelineStop.PROMPT,
            tools_confirmed=True,
            tool_ids=(),
        )
    )
    assert outcome.status == "prompt_ready"
    assert outcome.final_tool_ids == ()


# ── intent 에코백 재사용 (D2) ───────────────────────────────────────────────


async def test_intent_echo_skips_the_intent_llm() -> None:
    use_case, fakes = _pipeline()
    events = await _drain(
        use_case,
        stop_after=PipelineStop.PROMPT,
        tools_confirmed=True,
        intent_echo=IntentResult(filled_slots={"purpose": "여신 심사 Q&A"}),
    )
    assert fakes["intent"].calls == []
    assert _step(_outcome(events), "intent").status == StageStatus.OK
    assert _step(_outcome(events), "intent").reason == "확정된 의도 재사용"


async def test_intent_echo_is_used_for_prompt_generation() -> None:
    """재사용한 의도가 실제로 프롬프트 생성에 전달돼야 의미가 있다."""
    use_case, fakes = _pipeline()
    await _drain(
        use_case,
        stop_after=PipelineStop.PROMPT,
        tools_confirmed=True,
        intent_echo=IntentResult(filled_slots={"purpose": "여신 심사 Q&A"}),
    )
    passed = fakes["compose"].compose_calls[0]["intent"]
    assert passed is not None
    assert passed["filled_slots"] == {"purpose": "여신 심사 Q&A"}


async def test_invalid_intent_echo_falls_back_to_llm() -> None:
    """스펙 밖 키만 온 에코백은 재사용하지 않고 정상 판정한다."""
    use_case, fakes = _pipeline()
    await _drain(
        use_case,
        stop_after=PipelineStop.PROMPT,
        tools_confirmed=True,
        intent_echo=IntentResult(filled_slots={"evil": "주입"}),
    )
    assert len(fakes["intent"].calls) == 1


async def test_degraded_intent_echo_falls_back_to_llm() -> None:
    use_case, fakes = _pipeline()
    await _drain(
        use_case,
        stop_after=PipelineStop.PROMPT,
        tools_confirmed=True,
        intent_echo=IntentResult(degraded=True, filled_slots={"purpose": "x"}),
    )
    assert len(fakes["intent"].calls) == 1


# ── 프롬프트 clamp (D3) ─────────────────────────────────────────────────────


async def test_prompt_ready_clamps_prompt_to_storable_length() -> None:
    """화면에 보이는 프롬프트 = 실제 저장될 프롬프트 (D3).

    clamp 없이 원본을 보여주면 스튜디오 저장에서 422 가 나 사용자가 마지막
    단계에서 실패한다 (CreateAgentRequest.system_prompt max_length 와 동일 상한).
    """
    use_case, _ = _pipeline(
        compose=FakeComposeUC(
            _compose_result(assembled="가" * (PipelinePolicy.PROMPT_MAX_CHARS + 1000))
        )
    )
    outcome = _outcome(
        await _drain(
            use_case, stop_after=PipelineStop.PROMPT, tools_confirmed=True
        )
    )
    assert len(outcome.assembled_prompt) == PipelinePolicy.PROMPT_MAX_CHARS
    assert outcome.prompt_clamp_reason is not None


async def test_prompt_ready_has_no_clamp_reason_when_within_limit() -> None:
    use_case, _ = _pipeline()
    outcome = _outcome(
        await _drain(
            use_case, stop_after=PipelineStop.PROMPT, tools_confirmed=True
        )
    )
    assert outcome.prompt_clamp_reason is None


async def test_prompt_ready_propagates_degraded_prompt() -> None:
    """LLM 실패 폴백도 정상 정지한다 — 화면이 배지로 알린다."""
    use_case, _ = _pipeline(
        compose=FakeComposeUC(_compose_result(degraded=True, reason="timeout"))
    )
    outcome = _outcome(
        await _drain(
            use_case, stop_after=PipelineStop.PROMPT, tools_confirmed=True
        )
    )
    assert outcome.status == "prompt_ready"
    assert _step(outcome, "prompt").status == StageStatus.DEGRADED


# ── 회귀: stop 미지정은 기존과 동일 (FR-B09) ────────────────────────────────


async def test_no_stop_after_still_runs_all_five_stages() -> None:
    use_case, fakes = _pipeline()
    events = await _drain(use_case)

    assert _stages_of(events) == ["intent", "tools", "prompt", "create", "bind"]
    assert _outcome(events).status == "created"
    assert len(fakes["create"].calls) == 1
    assert len(fakes["selector"].calls) == 1


async def test_no_stop_after_leaves_wizard_fields_unset() -> None:
    """created 응답에는 위저드 전용 필드가 채워지지 않는다."""
    use_case, _ = _pipeline()
    outcome = _outcome(await _drain(use_case))
    assert outcome.prompt_clamp_reason is None
