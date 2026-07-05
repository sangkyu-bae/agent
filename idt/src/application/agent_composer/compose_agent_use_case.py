"""ComposeAgentUseCase: 자연어 → 에이전트 초안 조합 (무저장).

nl-agent-composer: 후보 수집(내부 TOOL_REGISTRY + MCP tool_catalog, D6) →
AgentComposer LLM 1회 → 서버 측 보정(drop/매핑/clamp, D7) → 초안 응답.
DB 쓰기 없음 — 저장은 기존 POST /agents(tool_ids 명시)로 수행된다.
"""
from src.application.agent_composer.composer import AgentComposer, _ComposeOutput
from src.application.agent_composer.schemas import (
    ComposeAgentDraftResponse,
    ComposeAgentRequest,
    MissingCapabilityDto,
)
from src.application.agent_builder.schemas import WorkerInfo
from src.domain.agent_builder.policies import AgentBuilderPolicy
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.agent_builder.tool_registry import get_all_tools
from src.domain.agent_composer.policies import ComposePolicy
from src.domain.agent_composer.schemas import (
    CandidateTool,
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
    ) -> None:
        self._composer = composer
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
            output = await self._composer.compose(
                request.user_request,
                candidates,
                request_id,
                current_config=request.current_config,
                history=history,
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
            return self._to_response(request, draft, llm_model_id)
        except Exception as e:
            self._logger.error(
                "ComposeAgentUseCase failed", exception=e, request_id=request_id
            )
            raise

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

        mapped, mapping_changed = self._map_mcp_workers(kept, candidates_by_id)

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
    def _map_mcp_workers(
        workers: list[WorkerDefinition],
        candidates_by_id: dict[str, CandidateTool],
    ) -> tuple[list[WorkerDefinition], bool]:
        """FR-05: mcp:{srv}:{tool} → mcp_{srv} 매핑 + 동일 tool_id 병합."""
        result: list[WorkerDefinition] = []
        by_tool_id: dict[str, WorkerDefinition] = {}
        changed = False
        for w in workers:
            target_id = w.tool_id
            cand = candidates_by_id.get(w.tool_id)
            if cand and cand.source == "mcp" and not cand.server_level:
                target_id = f"mcp_{cand.mcp_server_id}"
                changed = True
            existing = by_tool_id.get(target_id)
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
            mapped = WorkerDefinition(
                tool_id=target_id,
                worker_id=f"{target_id}_worker" if target_id != w.tool_id else w.worker_id,
                description=w.description,
                sort_order=w.sort_order,
                instruction=w.instruction,
            )
            by_tool_id[target_id] = mapped
            result.append(mapped)
        return result, changed

    # ── 응답 조립 ────────────────────────────────────────────────

    @staticmethod
    def _to_response(
        request: ComposeAgentRequest,
        draft: ComposedDraft,
        llm_model_id: str,
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
            )
        return ComposeAgentDraftResponse(
            coverage=draft.coverage,
            name_suggestion=name,
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
