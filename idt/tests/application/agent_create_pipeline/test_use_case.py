"""AgentCreatePipelineUseCase 테스트 — Design §2.1/§6.1, 협력자 전부 fake.

검증 대상: 단계 전이·이벤트 순서·실패 매트릭스. 규칙 자체(병합·clamp)는
domain 테스트가 이미 못박았으므로 여기서는 조합 흐름만 본다.
"""
from typing import Any

import pytest
from src.application.agent_builder.schemas import CreateAgentResponse
from src.application.agent_create_pipeline.events import (
    PipelineOutcome,
    StageEvent,
)
from src.application.agent_create_pipeline.use_case import (
    AgentCreatePipelineUseCase,
)
from src.application.prompt_composer.compose_prompt_use_case import ComposeResult
from src.domain.agent_create_pipeline.interfaces import ToolCandidateReaderPort
from src.domain.agent_create_pipeline.stages import StageStatus
from src.domain.intent.schemas import IntentResult, SlotAnswer, SlotQuestion
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.prompt_composer.schemas import ComposedPrompt, PromptSections
from src.domain.tool_selection.schemas import SelectionResult, ToolCandidate

# ── fakes ───────────────────────────────────────────────────────────────────


class FakeLogger(LoggerInterface):
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict]] = []

    def debug(self, message: str, **kwargs) -> None: ...
    def info(self, message: str, **kwargs) -> None: ...

    def warning(self, message: str, **kwargs) -> None:
        self.warnings.append((message, kwargs))

    def error(self, message, exception=None, **kwargs) -> None: ...
    def critical(self, message, exception=None, **kwargs) -> None: ...


class FakeIntentUC:
    def __init__(self, result: IntentResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def execute(self, *, message, spec, history=None, answers=None,
                      round_=0, request_id="") -> IntentResult:
        self.calls.append({"message": message, "spec": spec, "round_": round_,
                           "answers": answers})
        return self.result


class FakeCandidateReader(ToolCandidateReaderPort):
    def __init__(self, candidates: tuple[ToolCandidate, ...]) -> None:
        self.candidates = candidates

    async def list_active(self) -> tuple[ToolCandidate, ...]:
        return self.candidates


class FakeSelector:
    def __init__(self, result: SelectionResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def select(self, query, candidates, *, required_ids=(),
                     request_id="") -> SelectionResult:
        self.calls.append({"query": query, "candidates": candidates,
                           "required_ids": required_ids})
        return self.result


class FakeComposeUC:
    def __init__(self, result: ComposeResult,
                 compose_error: Exception | None = None,
                 bind_error: Exception | None = None) -> None:
        self.result = result
        self.compose_error = compose_error
        self.bind_error = bind_error
        self.compose_calls: list[dict[str, Any]] = []
        self.bind_calls: list[tuple[str, str, str]] = []

    async def compose(self, *, user_id, user_request, request_id, history=None,
                      intent=None, tool_ids=(), session_id=None,
                      agent_id=None) -> ComposeResult:
        self.compose_calls.append({"intent": intent, "tool_ids": tool_ids,
                                   "history": history, "session_id": session_id})
        if self.compose_error is not None:
            raise self.compose_error
        return self.result

    async def bind_agent(self, session_id, user_id, agent_id) -> None:
        self.bind_calls.append((session_id, user_id, agent_id))
        if self.bind_error is not None:
            raise self.bind_error


class FakeCreateUC:
    def __init__(self, response: CreateAgentResponse,
                 error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[Any] = []

    async def execute(self, request, request_id,
                      viewer_role="user") -> CreateAgentResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.response


# ── builders ────────────────────────────────────────────────────────────────


def _intent_ok(**overrides) -> IntentResult:
    base = dict(complete=True, filled_slots={"purpose": "문서 Q&A"})
    return IntentResult(**{**base, **overrides})


def _selection(final=("internal:a",), selected=("internal:a",),
               fallback=False, reason=None) -> SelectionResult:
    return SelectionResult(selected_ids=tuple(selected), required_ids=(),
                           final_ids=tuple(final), candidate_count=3,
                           fallback=fallback, reason=reason)


def _compose_result(assembled="조립된 프롬프트", degraded=False,
                    reason=None) -> ComposeResult:
    prompt = ComposedPrompt(sections=PromptSections(purpose="p"),
                            assembled=assembled, degraded=degraded,
                            reason=reason)
    return ComposeResult("ps1", "pv1", 1, prompt)


def _agent_response(system_prompt="조립된 프롬프트") -> CreateAgentResponse:
    return CreateAgentResponse(
        agent_id="agt1", name="문서 Q&A", system_prompt=system_prompt,
        tool_ids=["internal:a"], workers=[], flow_hint="",
        llm_model_id="m1", visibility="private", temperature=0.7,
        created_at="2026-08-19T00:00:00Z",
    )


def _pipeline(intent=None, candidates=None, selection=None, compose=None,
              create=None, logger=None):
    fakes = {
        "intent": intent or FakeIntentUC(_intent_ok()),
        "candidates": FakeCandidateReader(
            candidates if candidates is not None
            else (ToolCandidate(tool_id="internal:a", name="검색"),)
        ),
        "selector": FakeSelector(selection or _selection()),
        "compose": compose or FakeComposeUC(_compose_result()),
        "create": create or FakeCreateUC(_agent_response()),
        "logger": logger or FakeLogger(),
    }
    use_case = AgentCreatePipelineUseCase(
        intent_use_case=fakes["intent"],
        candidate_reader=fakes["candidates"],
        tool_selector=fakes["selector"],
        compose_use_case=fakes["compose"],
        create_agent_use_case=fakes["create"],
        logger=fakes["logger"],
    )
    return use_case, fakes


async def _drain(use_case, **kwargs) -> list:
    kwargs.setdefault("user_id", "u1")
    kwargs.setdefault("user_request", "검색 에이전트 만들어줘")
    kwargs.setdefault("request_id", "req1")
    return [event async for event in use_case.run(**kwargs)]


def _kinds(events) -> list[str]:
    return [e.kind for e in events if isinstance(e, StageEvent)]


def _outcome(events) -> PipelineOutcome:
    assert isinstance(events[-1], PipelineOutcome)
    return events[-1]


# ── 시나리오 ────────────────────────────────────────────────────────────────


async def test_happy_path_emits_five_stages_then_created_outcome() -> None:
    use_case, fakes = _pipeline()
    events = await _drain(use_case)

    assert _kinds(events) == [
        kind
        for _ in range(5)
        for kind in ("stage_started", "stage_completed")
    ]
    outcome = _outcome(events)
    assert outcome.status == "created"
    assert outcome.agent_id == "agt1"
    assert outcome.session_id == "ps1"
    assert outcome.bind_ok is True
    assert [s.status for s in outcome.steps] == [StageStatus.OK] * 5
    assert fakes["compose"].bind_calls == [("ps1", "u1", "agt1")]


async def test_need_input_stops_after_intent_and_echoes_questions() -> None:
    question = SlotQuestion(slot_key="purpose", question="용도는요?")
    intent = FakeIntentUC(IntentResult(complete=False, questions=[question]))
    use_case, fakes = _pipeline(intent=intent)

    events = await _drain(use_case, round_=0)

    assert _kinds(events) == ["stage_started", "stage_completed"]
    outcome = _outcome(events)
    assert outcome.status == "need_input"
    assert outcome.questions == (question,)
    assert outcome.round == 1  # 다음 재호출에 실을 값
    statuses = [s.status for s in outcome.steps]
    assert statuses == [StageStatus.OK] + [StageStatus.SKIPPED] * 4
    assert fakes["selector"].calls == []
    assert fakes["compose"].compose_calls == []
    assert fakes["create"].calls == []


async def test_degraded_intent_proceeds_and_compose_gets_no_intent() -> None:
    intent = FakeIntentUC(IntentResult(complete=False, degraded=True,
                                       reason="LLM 실패"))
    use_case, fakes = _pipeline(intent=intent)

    events = await _drain(use_case)

    outcome = _outcome(events)
    assert outcome.status == "created"
    assert outcome.steps[0].status is StageStatus.DEGRADED
    assert fakes["compose"].compose_calls[0]["intent"] is None


async def test_selector_fallback_marks_tools_degraded() -> None:
    selection = _selection(final=("internal:user",), selected=(),
                           fallback=True, reason="timeout")
    use_case, fakes = _pipeline(selection=selection)

    events = await _drain(use_case, tool_ids=("internal:user",))

    outcome = _outcome(events)
    assert outcome.steps[1].status is StageStatus.DEGRADED
    assert outcome.steps[1].reason == "timeout"
    assert outcome.final_tool_ids == ("internal:user",)
    assert fakes["compose"].compose_calls[0]["tool_ids"] == ("internal:user",)


async def test_empty_candidates_skip_selector_llm_call() -> None:
    use_case, fakes = _pipeline(candidates=())

    events = await _drain(use_case, tool_ids=("internal:user",))

    assert fakes["selector"].calls == []  # LLM 호출 없이 강하
    outcome = _outcome(events)
    assert outcome.steps[1].status is StageStatus.DEGRADED
    assert outcome.final_tool_ids == ("internal:user",)


async def test_prompt_degraded_still_creates_agent() -> None:
    compose = FakeComposeUC(_compose_result(degraded=True, reason="폴백"))
    use_case, fakes = _pipeline(compose=compose)

    events = await _drain(use_case)

    outcome = _outcome(events)
    assert outcome.status == "created"
    assert outcome.steps[2].status is StageStatus.DEGRADED
    assert outcome.steps[2].reason == "폴백"
    assert len(fakes["create"].calls) == 1


async def test_compose_storage_failure_propagates_and_halts() -> None:
    """저장 실패는 삼키지 않는다 (FR-08) — create/bind 미도달."""
    compose = FakeComposeUC(_compose_result(),
                            compose_error=RuntimeError("db down"))
    use_case, fakes = _pipeline(compose=compose)

    with pytest.raises(RuntimeError, match="db down"):
        await _drain(use_case)
    assert fakes["create"].calls == []
    assert fakes["compose"].bind_calls == []


async def test_create_failure_propagates() -> None:
    create = FakeCreateUC(_agent_response(), error=ValueError("모델 없음"))
    use_case, fakes = _pipeline(create=create)

    with pytest.raises(ValueError):
        await _drain(use_case)
    assert fakes["compose"].bind_calls == []


async def test_bind_failure_is_absorbed_and_reported() -> None:
    """bind 만 예외 흡수 지점이다 (Design §6.1) — 생성 성공을 뒤집지 않는다."""
    logger = FakeLogger()
    compose = FakeComposeUC(_compose_result(),
                            bind_error=RuntimeError("conflict"))
    use_case, fakes = _pipeline(compose=compose, logger=logger)

    events = await _drain(use_case)

    outcome = _outcome(events)
    assert outcome.status == "created"
    assert outcome.agent_id == "agt1"
    assert outcome.bind_ok is False
    assert outcome.steps[4].status is StageStatus.FAILED
    assert len(logger.warnings) == 1


async def test_round_is_reclamped_before_intent_call() -> None:
    intent = FakeIntentUC(_intent_ok())
    use_case, fakes = _pipeline(intent=intent)

    await _drain(use_case, round_=99)

    assert fakes["intent"].calls[0]["round_"] == 2  # SlotLimits 기본 max_rounds


async def test_oversized_prompt_is_clamped_for_create() -> None:
    compose = FakeComposeUC(_compose_result(assembled="a" * 4500))
    use_case, fakes = _pipeline(compose=compose)

    events = await _drain(use_case)

    request = fakes["create"].calls[0]
    assert len(request.system_prompt) == 4000
    outcome = _outcome(events)
    assert outcome.steps[3].status is StageStatus.OK
    assert "절단" in (outcome.steps[3].reason or "")


async def test_created_outcome_reports_stored_prompt() -> None:
    """응답의 프롬프트는 에이전트에 실제 저장된 값이다 (clamp 반영)."""
    use_case, _ = _pipeline()
    events = await _drain(use_case)
    assert _outcome(events).assembled_prompt == "조립된 프롬프트"


# ── Act-1 보강 (Design §8.2 시나리오 #3/#8/#9 정밀화) ───────────────────────


class SequencedIntentUC:
    """호출 순서대로 준비된 결과를 돌려주는 대역 — 왕복 시나리오용."""

    def __init__(self, results: list[IntentResult]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    async def execute(self, *, message, spec, history=None, answers=None,
                      round_=0, request_id="") -> IntentResult:
        self.calls.append({"round_": round_, "answers": answers})
        return self.results.pop(0)


async def test_clarification_round_trip_completes_creation() -> None:
    """시나리오 #3 — need_input → answers 재호출 → created 왕복 완주.

    이 기능의 존재 이유(stateless HITL로 에이전트 생성)를 증명하는 시나리오다.
    """
    question = SlotQuestion(slot_key="purpose", question="용도는요?")
    intent = SequencedIntentUC([
        IntentResult(complete=False, questions=[question]),
        IntentResult(complete=True, filled_slots={"purpose": "문서 Q&A"}),
    ])
    use_case, fakes = _pipeline(intent=intent)

    first = await _drain(use_case, round_=0)
    outcome1 = _outcome(first)
    assert outcome1.status == "need_input"
    assert fakes["create"].calls == []

    answer = SlotAnswer(slot_key="purpose", value="문서 Q&A")
    second = await _drain(use_case, answers=[answer], round_=outcome1.round)
    outcome2 = _outcome(second)

    assert outcome2.status == "created"
    assert outcome2.agent_id == "agt1"
    assert intent.calls[1]["round_"] == 1  # 에코백된 round 재사용
    assert intent.calls[1]["answers"] == [answer]
    assert len(fakes["create"].calls) == 1


async def test_create_storage_failure_propagates_as_is() -> None:
    """시나리오 #8 — create 단계 DB 예외는 ValueError(422)와 달리 그대로 전파(500)."""
    create = FakeCreateUC(_agent_response(), error=RuntimeError("agent store down"))
    use_case, fakes = _pipeline(create=create)

    with pytest.raises(RuntimeError, match="agent store down"):
        await _drain(use_case)
    assert fakes["compose"].bind_calls == []


async def test_bind_conflict_contract_exception_is_absorbed() -> None:
    """시나리오 #9 정밀화 — 계약 예외(AgentAlreadyBoundError=409)로 주입."""
    from src.application.prompt_composer.errors import AgentAlreadyBoundError

    compose = FakeComposeUC(
        _compose_result(), bind_error=AgentAlreadyBoundError("ps1")
    )
    use_case, _ = _pipeline(compose=compose)

    outcome = _outcome(await _drain(use_case))

    assert outcome.status == "created"
    assert outcome.bind_ok is False
    assert outcome.steps[4].status is StageStatus.FAILED
