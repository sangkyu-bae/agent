"""ComposeAgentUseCase: 자연어 → 에이전트 초안 조합 (무저장).

nl-agent-composer: 후보 수집(내부 TOOL_REGISTRY + MCP tool_catalog, D6) →
AgentComposer LLM 1회 → 서버 측 보정(drop/매핑/clamp, D7) → 초안 응답.
DB 쓰기 없음 — 저장은 기존 POST /agents(tool_ids 명시)로 수행된다.
"""
from src.application.agent_composer.composer import AgentComposer, _ComposeOutput
from src.application.agent_composer.interfaces import PlannerInterface, PlanResult
from src.application.agent_composer.schemas import (
    ClarifyingQuestionDto,
    ComposeAgentDraftResponse,
    ComposeAgentRequest,
    MissingCapabilityDto,
)
from src.application.agent_builder.schemas import WorkerInfo
from src.domain.agent_builder.policies import AgentBuilderPolicy
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.agent_builder.tool_registry import get_all_tools
from src.domain.agent_composer.policies import ComposePolicy, PlannerPolicy
from src.domain.agent_composer.schemas import (
    CandidateTool,
    ClarificationAnswer,
    ComposedDraft,
    MissingCapability,
)
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface

_FALLBACK_NOTE = "MCP 도구 카탈로그 동기화 전 — 서버 단위 정보로 제안되었습니다."


class ComposeAgentUseCase:
    def __init__(
        self,
        composer: AgentComposer,
        tool_catalog_repo: ToolCatalogRepositoryInterface,
        mcp_server_repo: MCPServerRegistryRepositoryInterface,
        llm_model_repository: LlmModelRepositoryInterface,
        logger: LoggerInterface,
        planner: PlannerInterface | None = None,
    ) -> None:
        # fix-agent-planner-hitl: planner 미주입 시 기존 단발 compose와 동일 동작
        self._composer = composer
        self._planner = planner
        self._tool_catalog_repo = tool_catalog_repo
        self._mcp_server_repo = mcp_server_repo
        self._llm_model_repository = llm_model_repository
        self._logger = logger

    async def execute(
        self, request: ComposeAgentRequest, request_id: str
    ) -> ComposeAgentDraftResponse:
        self._logger.info("ComposeAgentUseCase start", request_id=request_id)
        try:
            llm_model_id = await self._resolve_llm_model_id(
                request.llm_model_id, request_id
            )
            candidates, fallback_note = await self._collect_candidates(request_id)
            history = (
                ComposePolicy.clamp_history(request.history)
                if request.history
                else None
            )
            round_ = PlannerPolicy.clamp_round(request.clarification_round)
            plan_result = await self._try_plan(
                request, candidates, history, request_id, round_
            )
            clarification = self._maybe_clarification(
                round_, plan_result, request, llm_model_id, request_id
            )
            if clarification is not None:
                return clarification
            plan = plan_result.plan if plan_result else None
            output = await self._composer.compose(
                request.user_request,
                candidates,
                request_id,
                current_config=request.current_config,
                history=history,
                plan=plan,
            )
            draft = self._assemble_draft(
                output, candidates, fallback_note, request_id
            )
            self._logger.info(
                "ComposeAgentUseCase done",
                request_id=request_id,
                coverage=draft.coverage,
                worker_count=len(draft.workers),
            )
            return self._to_response(
                request, draft, llm_model_id,
                plan_summary=plan.plan_summary if plan else "",
            )
        except Exception as e:
            self._logger.error(
                "ComposeAgentUseCase failed", exception=e, request_id=request_id
            )
            raise

    # ── Planner 오케스트레이션 (fix-agent-planner-hitl) ───────────

    async def _try_plan(
        self,
        request: ComposeAgentRequest,
        candidates: list[CandidateTool],
        history: list[dict] | None,
        request_id: str,
        round_: int,
    ) -> PlanResult | None:
        """Planner 호출. 미주입/실패 시 None — 기존 단발 compose로 폴백 (FR-08)."""
        if self._planner is None:
            return None
        answers = [
            ClarificationAnswer(
                question_id=a.question_id, question=a.question, answer=a.answer
            )
            for a in request.clarification_answers or []
        ]
        try:
            return await self._planner.plan(
                request.user_request,
                candidates,
                request_id,
                current_config=request.current_config,
                history=history,
                answers=answers or None,
                round_=round_,
            )
        except Exception as e:
            self._logger.warning(
                "AgentPlanner failed — fallback to direct compose",
                request_id=request_id,
                exception=e,
            )
            return None

    def _maybe_clarification(
        self,
        round_: int,
        plan_result: PlanResult | None,
        request: ComposeAgentRequest,
        llm_model_id: str,
        request_id: str,
    ) -> ComposeAgentDraftResponse | None:
        """질문 필요 판정 → needs_clarification 응답 또는 None(진행)."""
        if plan_result is None:
            return None
        questions = PlannerPolicy.clamp_questions(plan_result.questions)
        if not PlannerPolicy.should_ask(
            plan_result.plan.confidence, len(questions), round_
        ):
            return None
        self._logger.info(
            "ComposeAgentUseCase needs_clarification",
            request_id=request_id,
            round=round_,
            question_count=len(questions),
            confidence=plan_result.plan.confidence,
        )
        return ComposeAgentDraftResponse(
            status="needs_clarification",
            questions=[
                ClarifyingQuestionDto(
                    id=f"q{round_}-{i + 1}",
                    question=q.question,
                    options=q.options,
                    allow_free_text=q.allow_free_text,
                )
                for i, q in enumerate(questions)
            ],
            plan_summary=plan_result.plan.plan_summary,
            coverage="none",
            name_suggestion=request.name or "",
            llm_model_id=llm_model_id,
            notes="추가 정보가 필요합니다.",
        )

    # ── 후보 수집 (D6 + D2 폴백) ──────────────────────────────────

    async def _collect_candidates(
        self, request_id: str
    ) -> tuple[list[CandidateTool], str]:
        candidates = [
            CandidateTool(
                tool_id=m.tool_id,
                name=m.name,
                description=m.description,
                source="internal",
            )
            for m in get_all_tools()
        ]
        entries = await self._tool_catalog_repo.list_active(request_id)
        mcp_entries = [e for e in entries if e.source == "mcp"]
        if mcp_entries:
            candidates += [
                CandidateTool(
                    tool_id=e.tool_id,
                    name=e.name,
                    description=e.description,
                    source="mcp",
                    mcp_server_id=e.mcp_server_id,
                )
                for e in mcp_entries
            ]
            return candidates, ""
        return await self._fallback_server_candidates(candidates, request_id)

    async def _fallback_server_candidates(
        self, candidates: list[CandidateTool], request_id: str
    ) -> tuple[list[CandidateTool], str]:
        """D2: 카탈로그에 MCP 항목이 없으면 서버 단위 메타로 폴백."""
        registrations = await self._mcp_server_repo.find_all_active(request_id)
        if not registrations:
            return candidates, ""
        self._logger.warning(
            "MCP tool catalog empty — falling back to server-level meta",
            request_id=request_id,
            server_count=len(registrations),
        )
        candidates += [
            CandidateTool(
                tool_id=reg.tool_id,
                name=reg.name,
                description=reg.description,
                source="mcp",
                mcp_server_id=reg.id,
                server_level=True,
            )
            for reg in registrations
        ]
        return candidates, _FALLBACK_NOTE

    # ── 초안 조립 (D7) ────────────────────────────────────────────

    def _assemble_draft(
        self,
        output: _ComposeOutput,
        candidates: list[CandidateTool],
        fallback_note: str,
        request_id: str,
    ) -> ComposedDraft:
        candidates_by_id = {c.tool_id: c for c in candidates}
        notes = [n for n in (output.notes, fallback_note) if n]

        workers, modified = self._sanitize_workers(
            output, candidates_by_id, notes, request_id
        )

        prompt, truncated = ComposePolicy.clamp_system_prompt(
            output.system_prompt, AgentBuilderPolicy.MAX_SYSTEM_PROMPT_LENGTH
        )
        if truncated:
            notes.append(
                f"system_prompt가 {AgentBuilderPolicy.MAX_SYSTEM_PROMPT_LENGTH}자로 "
                "절단되었습니다."
            )

        missing = [
            MissingCapability(
                capability=c.capability, reason=c.reason, suggestion=c.suggestion
            )
            for c in output.capabilities
            if not c.matched_tool_ids
        ]
        coverage = ComposePolicy.derive_coverage(len(workers), missing)
        flow_hint = (
            " → ".join(w.tool_id for w in workers)
            if modified
            else output.flow_hint
        )
        return ComposedDraft(
            coverage=coverage,
            name_suggestion=output.agent_name,
            system_prompt=prompt,
            workers=workers,
            flow_hint=flow_hint,
            missing_capabilities=missing,
            notes="; ".join(notes),
        )

    def _sanitize_workers(
        self,
        output: _ComposeOutput,
        candidates_by_id: dict[str, CandidateTool],
        notes: list[str],
        request_id: str,
    ) -> tuple[list[WorkerDefinition], bool]:
        """drop(FR-06) → MCP 매핑/병합(FR-05) → clamp(D7) → sort_order 재부여.

        notes 리스트에 보정 사유를 추가하고 (최종 워커, 변경 여부)를 반환한다.
        """
        workers = [
            WorkerDefinition(
                tool_id=w.tool_id,
                worker_id=w.worker_id,
                description=w.description,
                sort_order=w.sort_order,
                instruction=w.instruction,
            )
            for w in output.workers
        ]
        kept, dropped = ComposePolicy.drop_unknown_tools(
            workers, set(candidates_by_id)
        )
        if dropped:
            self._logger.warning(
                "Composer hallucinated tool_ids dropped",
                request_id=request_id,
                dropped=dropped,
            )
            notes.append(f"후보에 없는 도구 제외: {', '.join(dropped)}")

        mapped, mapping_changed = self._dedupe_workers(kept)

        clamped, cut = ComposePolicy.clamp_tool_count(
            mapped, AgentBuilderPolicy.MAX_TOOLS
        )
        if cut:
            notes.append(
                f"도구 수 상한({AgentBuilderPolicy.MAX_TOOLS}개) 초과로 제외: "
                f"{', '.join(cut)}"
            )

        final_workers = sorted(clamped, key=lambda w: w.sort_order)
        for i, w in enumerate(final_workers):
            w.sort_order = i
        return final_workers, bool(dropped) or bool(cut) or mapping_changed

    @staticmethod
    def _dedupe_workers(
        workers: list[WorkerDefinition],
    ) -> tuple[list[WorkerDefinition], bool]:
        """FR-05: 동일 tool_id 워커 병합.

        MCP는 개별 도구 단위(`mcp:{srv}:{tool}`)를 그대로 유지한다 — 같은
        서버라도 도구가 다르면 별개 워커다. 서버 단위로 접으면 실행 시
        어느 도구를 바인딩할지 특정할 수 없다.
        """
        result: list[WorkerDefinition] = []
        by_tool_id: dict[str, WorkerDefinition] = {}
        changed = False
        for w in workers:
            existing = by_tool_id.get(w.tool_id)
            if existing is not None:
                existing.description = f"{existing.description}; {w.description}"
                if w.instruction:
                    existing.instruction = (
                        f"{existing.instruction}; {w.instruction}"
                        if existing.instruction
                        else w.instruction
                    )
                existing.sort_order = min(existing.sort_order, w.sort_order)
                changed = True
                continue
            by_tool_id[w.tool_id] = w
            result.append(w)
        return result, changed

    # ── 응답 조립 ────────────────────────────────────────────────

    @staticmethod
    def _to_response(
        request: ComposeAgentRequest,
        draft: ComposedDraft,
        llm_model_id: str,
        plan_summary: str = "",
    ) -> ComposeAgentDraftResponse:
        missing = [
            MissingCapabilityDto(
                capability=m.capability, reason=m.reason, suggestion=m.suggestion
            )
            for m in draft.missing_capabilities
        ]
        name = request.name or draft.name_suggestion
        if draft.coverage == "none":
            return ComposeAgentDraftResponse(
                coverage="none",
                name_suggestion=name,
                llm_model_id=llm_model_id,
                missing_capabilities=missing,
                notes=draft.notes,
                plan_summary=plan_summary,
            )
        return ComposeAgentDraftResponse(
            coverage=draft.coverage,
            name_suggestion=name,
            plan_summary=plan_summary,
            system_prompt=draft.system_prompt,
            tool_ids=[w.tool_id for w in draft.workers],
            workers=[
                WorkerInfo(
                    tool_id=w.tool_id,
                    worker_id=w.worker_id,
                    description=w.description,
                    sort_order=w.sort_order,
                    tool_config=w.tool_config,
                    instruction=w.instruction,
                )
                for w in draft.workers
            ],
            flow_hint=draft.flow_hint,
            llm_model_id=llm_model_id,
            missing_capabilities=missing,
            notes=draft.notes,
        )

    async def _resolve_llm_model_id(
        self, llm_model_id: str | None, request_id: str
    ) -> str:
        """요청에 model_id가 없으면 기본 모델 사용 (초안 에이전트의 실행 모델, D5)."""
        if llm_model_id:
            found = await self._llm_model_repository.find_by_id(
                llm_model_id, request_id
            )
            if found is None:
                raise ValueError(f"LLM 모델을 찾을 수 없습니다: {llm_model_id}")
            return found.id
        default = await self._llm_model_repository.find_default(request_id)
        if default is None:
            raise ValueError("기본 LLM 모델이 설정되지 않았습니다.")
        return default.id
