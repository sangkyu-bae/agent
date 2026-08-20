"""AgentCreatePipelineUseCase — intent → tools → prompt → create → bind 조합.

Design Ref: §2.1/§2.2 — async generator 하나가 단계 이벤트와 최종 결과를
순서대로 yield 한다. 동기 라우터는 소진해 마지막만, SSE 라우터는 실시간 송출.

**try/except 는 bind 한 곳뿐이다** (Design §6.1/§6.2):
  - intent·tools·prompt 의 LLM 실패는 각 모듈 어댑터가 흡수해 degraded 로
    돌려주는 것이 포트 계약이므로 여기서 잡을 것이 없다.
  - 저장 실패(프롬프트 버전·에이전트)는 잡으면 안 된다 — 200 으로 위장하면
    호출자가 없는 리소스를 참조한다 (FR-08). 예외는 그대로 전파된다.
  - bind 만 흡수한다: 이미 agent_id 라는 "쓸 수 있는 결과"가 존재하므로
    백필 실패가 생성 성공을 뒤집으면 안 된다 (FR-06).
"""
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace

from src.application.agent_builder.schemas import (
    CreateAgentRequest,
    CreateAgentResponse,
)
from src.application.agent_create_pipeline.events import (
    PipelineOutcome,
    StageEvent,
)
from src.application.prompt_composer.compose_prompt_use_case import ComposeResult
from src.domain.agent_create_pipeline.interfaces import ToolCandidateReaderPort
from src.domain.agent_create_pipeline.policies import PipelinePolicy
from src.domain.agent_create_pipeline.spec import build_agent_create_spec
from src.domain.agent_create_pipeline.stages import (
    PipelineStage,
    PipelineStop,
    StageRecord,
    StageStatus,
)
from src.domain.intent.schemas import (
    IntentResult,
    IntentSpec,
    SlotAnswer,
    SlotLimits,
    Turn,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_selection.schemas import SelectionResult

_NEED_INPUT = "need_input"
_NOT_REACHED = "not_reached"
_STOPPED = "stopped_for_review"
"""정지로 미도달한 단계의 skip 사유 (agent-create-wizard §4.3)."""


@dataclass
class _Run:
    """요청 1건의 가변 컨텍스트 — 단계 간 산출물 전달용 (외부 비노출)."""

    user_id: str
    user_request: str
    request_id: str
    history: list[Turn]
    answers: list[SlotAnswer] | None
    round: int
    tool_ids: tuple[str, ...]
    name: str | None
    llm_model_id: str | None
    session_id: str | None
    # agent-create-wizard §2.2 — 위저드 입력 3종. 전부 no-op 기본값이므로
    # 미지정이면 기존 논스톱 실행과 동일하다 (FR-B09).
    stop: PipelineStop | None = None
    tools_confirmed: bool = False
    intent_echo: IntentResult | None = None
    records: list[StageRecord] = field(default_factory=list)
    intent: IntentResult | None = None
    selection: SelectionResult | None = None
    compose: ComposeResult | None = None
    agent: CreateAgentResponse | None = None
    bind_ok: bool | None = None


class AgentCreatePipelineUseCase:
    """단계 이벤트를 방출하는 오케스트레이터."""

    def __init__(
        self,
        intent_use_case,
        candidate_reader: ToolCandidateReaderPort,
        tool_selector,
        compose_use_case,
        create_agent_use_case,
        logger: LoggerInterface,
        spec: IntentSpec | None = None,
        limits: SlotLimits | None = None,
    ) -> None:
        self._intent = intent_use_case
        self._candidates = candidate_reader
        self._selector = tool_selector
        self._compose = compose_use_case
        self._create = create_agent_use_case
        self._logger = logger
        self._spec = spec or build_agent_create_spec()
        self._limits = limits or SlotLimits()

    async def run(
        self,
        *,
        user_id: str,
        user_request: str,
        request_id: str,
        history: Sequence[Turn] | None = None,
        answers: Sequence[SlotAnswer] | None = None,
        round_: int = 0,
        tool_ids: Sequence[str] = (),
        name: str | None = None,
        llm_model_id: str | None = None,
        session_id: str | None = None,
        stop_after: PipelineStop | None = None,
        tools_confirmed: bool = False,
        intent_echo: IntentResult | None = None,
    ) -> AsyncIterator[StageEvent | PipelineOutcome]:
        """파이프라인 실행 — StageEvent* 를 yield 하고 PipelineOutcome 으로 끝난다.

        agent-create-wizard §2.2 — `stop_after` 가 주어지면 해당 단계 직후
        멈추고 `tools_proposed`/`prompt_ready` 로 끝난다. 미지정이면 기존
        논스톱 실행(intent→…→bind)과 완전히 동일하다.
        """
        ctx = _Run(
            user_id=user_id,
            user_request=user_request,
            request_id=request_id,
            history=list(history or []),
            answers=list(answers) if answers else None,
            round=PipelinePolicy.clamp_round(round_, self._limits.max_rounds),
            tool_ids=tuple(tool_ids),
            name=name,
            llm_model_id=llm_model_id,
            session_id=session_id,
            stop=stop_after,
            tools_confirmed=tools_confirmed,
            intent_echo=intent_echo,
        )
        self._logger.info(
            "pipeline start",
            request_id=request_id,
            round=ctx.round,
            stop_after=stop_after.value if stop_after else None,
        )
        async for event in self._stage(PipelineStage.INTENT, ctx, self._run_intent):
            yield event
        assert ctx.intent is not None  # _run_intent 가 항상 채운다
        # 되묻기가 정지 지점보다 우선한다 — 물을 것이 남았는데 도구를
        # 추천하면 근거 없는 추천이 된다.
        # prompt-depth G-01 — round/max_rounds 를 넘겨야 "required 는 찼지만
        # optional 축이 남은" 상태에서 한 번 더 물을 수 있다. 상한은 IntentConfig
        # 단일 출처(FR-17)를 그대로 쓴다.
        decision = PipelinePolicy.decide_after_intent(
            ctx.intent, round_=ctx.round, max_rounds=self._limits.max_rounds
        )
        if decision == "ask":
            yield self._need_input_outcome(ctx)
            return
        # 실행 단계 목록은 domain Policy 가 계산한다 — 분기가 흐름 코드에
        # 흩어지면 후속 R1 수렴에서 재사용할 수 없다 (Design Option C).
        runners = {
            PipelineStage.TOOLS: self._run_tools,
            PipelineStage.PROMPT: self._run_prompt,
            PipelineStage.CREATE: self._run_create,
            PipelineStage.BIND: self._run_bind,
        }
        for stage in PipelinePolicy.stages_to_run(ctx.stop):
            async for event in self._stage(stage, ctx, runners[stage]):
                yield event
            if PipelinePolicy.decide_after_stage(stage, ctx.stop) == "stop":
                yield self._stopped_outcome(ctx)
                return
        yield self._created_outcome(ctx)

    # ── 단계 공통 실행기 ────────────────────────────────────────────────────

    async def _stage(
        self,
        stage: PipelineStage,
        ctx: _Run,
        stage_fn: Callable[[_Run], Awaitable[StageRecord]],
    ) -> AsyncIterator[StageEvent]:
        """started 이벤트 → 실행 → elapsed 채워 completed 이벤트."""
        yield StageEvent("stage_started", StageRecord(stage, StageStatus.OK))
        start = time.monotonic()
        record = await stage_fn(ctx)
        record = replace(
            record, elapsed_ms=int((time.monotonic() - start) * 1000)
        )
        ctx.records.append(record)
        yield StageEvent("stage_completed", record)

    # ── 단계별 실행 ─────────────────────────────────────────────────────────

    async def _run_intent(self, ctx: _Run) -> StageRecord:
        # agent-create-wizard D2 — 확정된 의도를 에코백받았으면 LLM 을 다시
        # 돌리지 않는다. 재판정하면 사용자가 도구를 고른 근거였던 의도와
        # 프롬프트 생성에 쓰인 의도가 달라질 수 있다. 신뢰 경계(spec 검증·
        # 계산 필드 재계산)는 Policy 가 처리한다.
        reused = PipelinePolicy.reuse_intent(ctx.intent_echo, self._spec)
        if reused is not None:
            ctx.intent = reused
            return StageRecord(
                PipelineStage.INTENT, StageStatus.OK, "확정된 의도 재사용"
            )
        result = await self._intent.execute(
            message=ctx.user_request,
            spec=self._spec,
            history=ctx.history or None,
            answers=ctx.answers,
            round_=ctx.round,
            request_id=ctx.request_id,
        )
        ctx.intent = result
        if result.degraded:
            return StageRecord(
                PipelineStage.INTENT,
                StageStatus.DEGRADED,
                result.reason or "의도 판정 실패 — 의도 없이 진행",
            )
        return StageRecord(PipelineStage.INTENT, StageStatus.OK)

    async def _run_tools(self, ctx: _Run) -> StageRecord:
        # agent-create-wizard D1 — 사용자가 확정한 목록은 셀렉터를 태우지
        # 않는다. required_ids 로 넘기면 final = 추천 ∪ 확정 이 되어 사용자가
        # 제거한 도구가 되살아난다 (포트 계약상 required 는 항상 보존되므로).
        if ctx.tools_confirmed:
            selection = PipelinePolicy.confirmed_selection(ctx.tool_ids)
            ctx.selection = selection
            return StageRecord(
                PipelineStage.TOOLS, StageStatus.OK, selection.reason
            )
        candidates = await self._candidates.list_active()
        if candidates:
            selection = await self._selector.select(
                PipelinePolicy.build_selector_query(ctx.user_request, ctx.intent),
                candidates,
                required_ids=ctx.tool_ids,
                request_id=ctx.request_id,
            )
        else:
            # 후보 0건이면 LLM 호출 없이 강하한다 (Design §6.1)
            selection = PipelinePolicy.empty_candidate_selection(ctx.tool_ids)
        ctx.selection = selection
        if selection.fallback:
            return StageRecord(
                PipelineStage.TOOLS,
                StageStatus.DEGRADED,
                selection.reason or "도구 추천 실패 — 지정 도구만 사용",
            )
        return StageRecord(PipelineStage.TOOLS, StageStatus.OK)

    async def _run_prompt(self, ctx: _Run) -> StageRecord:
        assert ctx.selection is not None
        intent_payload = (
            ctx.intent.model_dump()
            if ctx.intent is not None and not ctx.intent.degraded
            else None
        )
        result = await self._compose.compose(
            user_id=ctx.user_id,
            user_request=ctx.user_request,
            request_id=ctx.request_id,
            history=[turn.model_dump() for turn in ctx.history],
            intent=intent_payload,
            tool_ids=PipelinePolicy.resolve_tool_ids(ctx.selection),
            session_id=ctx.session_id,
        )
        ctx.compose = result
        if result.prompt.degraded:
            return StageRecord(
                PipelineStage.PROMPT,
                StageStatus.DEGRADED,
                result.prompt.reason or "프롬프트 생성 실패 — 규칙기반 폴백",
            )
        return StageRecord(PipelineStage.PROMPT, StageStatus.OK)

    async def _run_create(self, ctx: _Run) -> StageRecord:
        assert ctx.selection is not None and ctx.compose is not None
        prompt, clamp_reason = PipelinePolicy.clamp_prompt(
            ctx.compose.prompt.assembled
        )
        request = CreateAgentRequest(
            user_request=ctx.user_request[:1000],
            name=PipelinePolicy.resolve_agent_name(
                ctx.name, ctx.intent, ctx.user_request
            ),
            user_id=ctx.user_id,
            llm_model_id=ctx.llm_model_id,
            tool_ids=list(PipelinePolicy.resolve_tool_ids(ctx.selection)),
            system_prompt=prompt,
            visibility="private",  # 공개 범위 승격은 기존 PATCH 경로로 (§7)
        )
        ctx.agent = await self._create.execute(request, ctx.request_id)
        return StageRecord(PipelineStage.CREATE, StageStatus.OK, clamp_reason)

    async def _run_bind(self, ctx: _Run) -> StageRecord:
        assert ctx.compose is not None and ctx.agent is not None
        try:
            await self._compose.bind_agent(
                ctx.compose.session_id, ctx.user_id, ctx.agent.agent_id
            )
        except Exception as e:  # 유일한 흡수 지점 — 생성 성공을 뒤집지 않는다
            self._logger.warning(
                "pipeline bind failed",
                request_id=ctx.request_id,
                session_id=ctx.compose.session_id,
                agent_id=ctx.agent.agent_id,
                exception=e,
            )
            ctx.bind_ok = False
            return StageRecord(PipelineStage.BIND, StageStatus.FAILED, str(e))
        ctx.bind_ok = True
        return StageRecord(PipelineStage.BIND, StageStatus.OK)

    # ── 결과 조립 ───────────────────────────────────────────────────────────

    def _need_input_outcome(self, ctx: _Run) -> PipelineOutcome:
        assert ctx.intent is not None
        return PipelineOutcome(
            status="need_input",
            steps=PipelinePolicy.finalize_steps(ctx.records, _NEED_INPUT),
            questions=tuple(ctx.intent.questions),
            round=ctx.round + 1,
            intent=ctx.intent,
        )

    def _stopped_outcome(self, ctx: _Run) -> PipelineOutcome:
        """정지 지점 결과 조립 — tools_proposed / prompt_ready 공통 (§4.3).

        빌더를 상태별로 쪼개지 않는 이유: 두 응답의 차이는 "compose 가
        끝났는가" 하나뿐이고, 쪼개면 steps·intent·도구 목록 조립이 복사된다.
        """
        assert ctx.stop is not None and ctx.selection is not None
        compose = ctx.compose
        prompt, clamp_reason = (
            PipelinePolicy.clamp_prompt(compose.prompt.assembled)
            if compose is not None
            else (None, None)
        )
        self._logger.info(
            "pipeline stopped for review",
            request_id=ctx.request_id,
            stop_after=ctx.stop.value,
            tool_count=len(ctx.selection.final_ids),
        )
        return PipelineOutcome(
            status=PipelinePolicy.stop_status(ctx.stop),
            steps=PipelinePolicy.finalize_steps(ctx.records, _STOPPED),
            round=ctx.round,
            intent=ctx.intent,
            recommended_tool_ids=ctx.selection.selected_ids,
            final_tool_ids=ctx.selection.final_ids,
            unknown_tool_ids=(
                compose.prompt.unknown_tool_ids if compose is not None else ()
            ),
            session_id=compose.session_id if compose is not None else None,
            version_id=compose.version_id if compose is not None else None,
            assembled_prompt=prompt,
            prompt_clamp_reason=clamp_reason,
            suggested_name=PipelinePolicy.resolve_agent_name(
                ctx.name, ctx.intent, ctx.user_request
            ),
        )

    def _created_outcome(self, ctx: _Run) -> PipelineOutcome:
        assert (
            ctx.selection is not None
            and ctx.compose is not None
            and ctx.agent is not None
        )
        self._logger.info(
            "pipeline created",
            request_id=ctx.request_id,
            agent_id=ctx.agent.agent_id,
            session_id=ctx.compose.session_id,
            bind_ok=ctx.bind_ok,
        )
        return PipelineOutcome(
            status="created",
            steps=PipelinePolicy.finalize_steps(ctx.records, _NOT_REACHED),
            round=ctx.round,
            intent=ctx.intent,
            recommended_tool_ids=ctx.selection.selected_ids,
            final_tool_ids=ctx.selection.final_ids,
            unknown_tool_ids=ctx.compose.prompt.unknown_tool_ids,
            session_id=ctx.compose.session_id,
            version_id=ctx.compose.version_id,
            agent_id=ctx.agent.agent_id,
            agent_name=ctx.agent.name,
            assembled_prompt=ctx.agent.system_prompt,
            bind_ok=ctx.bind_ok,
        )
