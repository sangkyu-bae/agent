"""에이전트 생성 파이프라인 엔드포인트 — /api/v1/agents/pipeline.

Design Ref: §4.1~§4.5.

- 동기 POST 와 SSE POST 는 **같은 UseCase 제너레이터**를 소비 방식만 달리한다
  — 최종 payload 의미 동일이 코드 구조로 강제된다 (FR-15).
- SSE 가 GET 이 아닌 이유: 입력이 본문이라 query 로 못 싣는다. fetch-stream
  소비 전제이며 인증도 표준 헤더로 통일한다 (query-token 특례 불필요).
- LLM 실패는 단계별 degraded(200), **저장 실패는 5xx 전파** (FR-08) —
  stage_failed 합성은 SSE 제너레이터가 담당한다 (UseCase 는 try/except 금지).
- v3 auto 빌더와 달리 **세션 없음(stateless)** — 되묻기는 answers/round
  에코백 재호출로 진행한다 (Plan R6).

DI placeholder 는 main.py 에서 override 한다. 미등록(킬스위치 off) 시
이 라우터 자체가 앱에 붙지 않는다.
"""
import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.application.agent_create_pipeline.events import (
    PipelineOutcome,
    StageEvent,
)
from src.application.agent_create_pipeline.use_case import (
    AgentCreatePipelineUseCase,
)
from src.application.prompt_composer.errors import PromptSessionNotFoundError
from src.domain.agent_create_pipeline.policies import PipelinePolicy
from src.domain.agent_create_pipeline.stages import (
    PipelineStage,
    PipelineStop,
    StageRecord,
    StageStatus,
)
from src.domain.auth.entities import User
from src.domain.intent.schemas import IntentResult, SlotAnswer, Turn
from src.interfaces.dependencies.auth import get_current_user
from src.interfaces.schemas.agent_pipeline import (
    AgentPipelineRequest,
    AgentPipelineResponse,
    IntentSummaryOut,
    QuestionOut,
    StageRecordOut,
)

router = APIRouter(prefix="/api/v1/agents/pipeline", tags=["Agent Pipeline"])

_NOT_FOUND = "세션을 찾을 수 없습니다"
_NOT_REACHED = "not_reached"
# LLM 단계 대기 중 프록시 idle 절단 방지 (Design §4.4 / Plan R2·R7).
# run/stream 관례(15초)와 동일 주기.
_HEARTBEAT_INTERVAL_SEC = 15.0


def get_agent_pipeline_use_case() -> AgentCreatePipelineUseCase:
    raise NotImplementedError("AgentCreatePipelineUseCase not initialized")


@router.post("", response_model=AgentPipelineResponse)
async def run_pipeline(
    request: AgentPipelineRequest,
    current_user: User = Depends(get_current_user),
    use_case: AgentCreatePipelineUseCase = Depends(get_agent_pipeline_use_case),
) -> AgentPipelineResponse:
    """의도 판정 → 도구 추천 → 프롬프트 생성 → 에이전트 생성, 한 호출.

    Returns:
        200: `status=need_input` 이면 questions 에 답해 answers/round 를 실어
            재호출한다. `status=created` 면 agent_id 가 만들어져 있다.
            단계별 결과는 steps[] (항상 5개, degraded 포함)로 확인한다.

    Errors:
        401: 인증 실패
        404: session_id 가 없거나 타인 소유
        422: 입력 검증 실패, 에이전트 생성 검증 실패(모델 없음 등)
        500: 프롬프트 버전·에이전트 저장 실패 (degraded 로 위장하지 않는다)
    """
    outcome: PipelineOutcome | None = None
    try:
        async for item in use_case.run(
            **_run_kwargs(request, current_user, str(uuid.uuid4()))
        ):
            if isinstance(item, PipelineOutcome):
                outcome = item
    except PromptSessionNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if outcome is None:  # 제너레이터는 항상 outcome 으로 끝나는 계약이다
        raise HTTPException(status_code=500, detail="pipeline produced no result")
    return _to_response(outcome)


@router.post("/stream")
async def run_pipeline_stream(
    request: AgentPipelineRequest,
    current_user: User = Depends(get_current_user),
    use_case: AgentCreatePipelineUseCase = Depends(get_agent_pipeline_use_case),
) -> StreamingResponse:
    """동일 계약의 SSE 변형 — 단계 이벤트를 실시간 송출한다 (Design §4.4).

    이벤트: stage_started / stage_completed / stage_failed / pipeline_result.
    스트림 시작 후의 실패는 HTTP 에러가 아니라 stage_failed +
    pipeline_result(status=failed) 로 표현된다.
    """
    kwargs = _run_kwargs(request, current_user, str(uuid.uuid4()))
    return StreamingResponse(
        _sse_stream(use_case, kwargs),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _sse_stream(use_case: AgentCreatePipelineUseCase, kwargs: dict):
    """제너레이터 → SSE wire. 실패 시 stage_failed 를 여기서 합성한다.

    UseCase 는 예외를 전파하는 것이 계약(§6.2)이므로, 어느 단계에서
    죽었는지는 마지막 stage_started 기록으로 복원한다.

    heartbeat: LLM 단계 대기가 주기를 넘기면 SSE 주석 라인을 흘린다.
    `wait_for` 를 쓰지 않는 이유 — timeout 시 `__anext__` 를 취소하면
    CancelledError 가 파이프라인 제너레이터 내부(LLM await 지점)로 주입되어
    실행 자체가 중단된다. task 를 유지한 채 `asyncio.wait(timeout)` 으로
    기다려야 단계가 계속 진행된다.
    """
    seq = 0
    current = PipelineStage.INTENT
    records: list[StageRecord] = []
    generator = use_case.run(**kwargs)
    task = asyncio.ensure_future(anext(generator))
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=_HEARTBEAT_INTERVAL_SEC)
            if not done:
                yield b": heartbeat\n\n"
                continue
            try:
                item = task.result()
            except StopAsyncIteration:
                break
            except Exception as e:
                failed = StageRecord(current, StageStatus.FAILED, str(e))
                records.append(failed)
                yield _sse("stage_failed", _record_out(failed).model_dump(), seq)
                steps = PipelinePolicy.finalize_steps(records, _NOT_REACHED)
                yield _sse(
                    "pipeline_result",
                    {
                        "status": "failed",
                        "error": {"message": str(e)},
                        "steps": [_record_out(r).model_dump() for r in steps],
                    },
                    seq + 1,
                )
                return
            yield _serialize_item(item, seq, records)
            if isinstance(item, StageEvent) and item.kind == "stage_started":
                current = item.record.stage
            seq += 1
            task = asyncio.ensure_future(anext(generator))
    finally:
        if not task.done():
            task.cancel()


def _serialize_item(
    item: StageEvent | PipelineOutcome, seq: int, records: list[StageRecord]
) -> bytes:
    """이벤트 1건 → SSE 블록. stage_started 는 §4.4 계약대로 stage 만 싣는다."""
    if isinstance(item, StageEvent):
        if item.kind == "stage_started":
            return _sse(item.kind, {"stage": item.record.stage.value}, seq)
        records.append(item.record)
        return _sse(item.kind, _record_out(item.record).model_dump(), seq)
    return _sse("pipeline_result", _to_response(item).model_dump(), seq)


# ── 변환 (비즈니스 로직 아님 — 직렬화만) ────────────────────────────────────


def _run_kwargs(
    request: AgentPipelineRequest, user: User, request_id: str
) -> dict:
    answers = [
        SlotAnswer(slot_key=a.slot_key, value=a.value) for a in request.answers
    ]
    return {
        "user_id": str(user.id),
        "user_request": request.user_request,
        "request_id": request_id,
        "history": [
            Turn(role=t.role, content=t.content) for t in request.history
        ],
        "answers": answers or None,
        "round_": request.round,
        "tool_ids": tuple(request.tool_ids),
        "name": request.name,
        "llm_model_id": request.llm_model_id,
        "session_id": request.session_id,
        # agent-create-wizard §4.2 — 미지정이면 전부 no-op 기본값이라
        # 기존 논스톱 호출의 동작이 변하지 않는다 (FR-B09).
        "stop_after": (
            PipelineStop(request.stop_after) if request.stop_after else None
        ),
        "tools_confirmed": request.tools_confirmed,
        "intent_echo": _to_intent_echo(request.intent),
    }


def _to_intent_echo(echo) -> IntentResult | None:
    """에코백 DTO → IntentResult. **검증은 하지 않는다** — Policy 의 몫이다.

    여기서 걸러내면 신뢰 경계가 라우터와 domain 두 곳으로 갈린다.
    """
    if echo is None:
        return None
    return IntentResult(
        label=echo.label,
        filled_slots=dict(echo.filled_slots),
        degraded=echo.degraded,
    )


def _record_out(record: StageRecord) -> StageRecordOut:
    return StageRecordOut(
        stage=record.stage.value,
        status=record.status.value,
        reason=record.reason,
        elapsed_ms=record.elapsed_ms,
    )


def _to_response(outcome: PipelineOutcome) -> AgentPipelineResponse:
    steps = [_record_out(record) for record in outcome.steps]
    intent = outcome.intent
    return AgentPipelineResponse(
        status=outcome.status,
        round=outcome.round,
        steps=steps,
        degraded_stages=[s.stage for s in steps if s.status == "degraded"],
        questions=[
            QuestionOut(
                slot_key=q.slot_key,
                question=q.question,
                options=list(q.options),
                allow_free_text=q.allow_free_text,
            )
            for q in outcome.questions
        ],
        intent=(
            IntentSummaryOut(
                label=intent.label,
                filled_slots=dict(intent.filled_slots),
                missing_slots=list(intent.missing_slots),
                degraded=intent.degraded,
            )
            if intent is not None
            else None
        ),
        recommended_tool_ids=list(outcome.recommended_tool_ids),
        final_tool_ids=list(outcome.final_tool_ids),
        unknown_tool_ids=list(outcome.unknown_tool_ids),
        session_id=outcome.session_id,
        version_id=outcome.version_id,
        agent_id=outcome.agent_id,
        agent_name=outcome.agent_name,
        assembled_prompt=outcome.assembled_prompt,
        bind_ok=outcome.bind_ok,
        suggested_name=outcome.suggested_name,
        prompt_clamp_reason=outcome.prompt_clamp_reason,
    )


def _sse(event: str, payload: dict, seq: int) -> bytes:
    """SSE 라인 블록 — agent_run SSE 포매터와 동일 규칙 (event/id/data)."""
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\nid: {seq}\ndata: {data}\n\n".encode()
