"""WorkflowCompiler: WorkflowDefinition → Custom StateGraph CompiledGraph 동적 컴파일."""
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING

from langchain_core.messages import AIMessage
from langchain.agents import create_agent
from langgraph.graph import END, StateGraph

from src.application.agent_builder.message_normalization import ensure_user_tail
from src.application.agent_builder.search_pipeline import (
    create_search_pipeline_node,
    is_search_result as _is_search_result,
    is_worker_output as _is_worker_output,
    latest_user_question,
)
from src.application.deep_search.workflow import create_deep_search_node
from src.domain.deep_search.policies import DeepSearchBudgetPolicy
from src.application.agent_builder.supervisor_hooks import (
    AttachmentRoutingHooks,
    DefaultHooks,
    SupervisorHooks,
)
from src.application.agent_builder.supervisor_nodes import (
    build_initial_state,
    create_quality_gate_node,
    create_supervisor_node,
    route_after_quality,
    route_to_worker,
    route_to_worker_or_final,
)
from src.application.agent_builder.supervisor_state import SupervisorState
from src.application.agent_run.auth_context import get_current_auth_context
from src.application.agent_run.prompt_rendering import (
    WIKI_FOLDER_HEADER_TAG,
    render_datetime_block,
    render_user_context_block,
)
from src.application.visualization.analysis_prompt import (
    ANALYSIS_OUTPUT_GUIDE,
    DATA_GAP_GUIDE,
)
from src.application.visualization.chart_builder_node import (
    create_chart_builder_node,
)
from src.application.visualization.chart_router import (
    create_chart_router_node,
    route_after_chart_router,
)
from src.domain.visualization.analysis_output_policy import (
    ANALYSIS_OUTPUT_SANITIZER,
)
from src.domain.visualization.chart_policy import ChartStylePolicy
from src.domain.visualization.policies import VisualizationRoutingPolicy
from src.infrastructure.visualization.llm_chart_builder import LangChainChartBuilder
from src.infrastructure.visualization.llm_classifier import (
    LangChainVisualizationClassifier,
)
from src.application.agent_run.step_tracking import (
    STEP_OUTPUT_SUMMARY_KEY,
    _summarize_state_input,
    _summarize_state_output,
    track_step,
)
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.auth_context import AuthContext
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import (
    CircularReferencePolicy,
    IterationLimitPolicy,
    NestingDepthPolicy,
    QualityGatePolicy,
    SearchPipelinePolicy,
)
from src.domain.agent_builder.schemas import SupervisorConfig, WorkerDefinition, WorkflowDefinition
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.agent_run.value_objects import NodeType, RunId
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp.exceptions import McpWiringError
from src.domain.tool_catalog.mcp_tool_id import parse_mcp_tool_id
from src.infrastructure.agent_builder.tool_factory import ToolFactory

if TYPE_CHECKING:
    from src.infrastructure.llm.usage_callback import UsageCallback


# search-node-query-pipeline D2: _is_search_result / _is_worker_output 정의는
# search_pipeline 모듈로 이동(메시지 규약 단일 출처). 본 모듈은 alias import로 사용.

# wiki-agentic-navigation D1: wiki_read 워커 react agent에 목차와 함께 주입되는 지시.
_WIKI_WORKER_INSTRUCTION = (
    "위 목차에서 질문과 관련된 문서 id를 골라 wiki_read 도구로 본문을 열람하고, "
    "열람한 본문에 근거해 답하세요. "
    "관련 문서가 없으면 '위키에서 확인되지 않습니다'라고 답하세요.\n"
)

# wiki-folder-summaries D6: 폴더 모드 워커 지시 — 지도→wiki_list→wiki_read 체인.
_WIKI_FOLDER_WORKER_INSTRUCTION = (
    "위 지도에서 질문과 관련된 폴더를 wiki_list 도구로 열어 문서 id를 찾고, "
    "wiki_read 도구로 본문을 열람한 뒤 답하세요. "
    "목록에 없는 내용은 추측하지 말고, 관련 문서가 없으면 "
    "'위키에서 확인되지 않습니다'라고 답하세요.\n"
)


def _instantiate(middleware_plan) -> list:
    """builtin-middleware D6: 워커마다 새 미들웨어 인스턴스 (상태 공유 금지)."""
    if middleware_plan is None:
        return []
    return middleware_plan.instantiate()


def _is_tool_message(msg) -> bool:
    """tool 역할 메시지 판정 — final_answer LLM 입력에서 제외 (고아 tool 400 방어)."""
    if isinstance(msg, dict):
        return msg.get("role") == "tool"
    return getattr(msg, "type", "") == "tool"


def _summarize_charts(charts: list[dict]) -> str:
    """state["charts"] → 프롬프트용 메타 요약(개수·type·title만, DQ5). 키 부재 시 graceful."""
    lines = []
    for i, chart in enumerate(charts, 1):
        chart_type = chart.get("type", "unknown")
        title = (
            ((chart.get("options") or {}).get("plugins") or {}).get("title") or {}
        ).get("text", "") or "(제목 없음)"
        lines.append(f"{i}. {chart_type} — {title}")
    return "\n".join(lines)


# ── deep-search-pipeline 배선 상수 (FR-13/D9) ────────────────────
LEGACY_SEARCH_MODE = "legacy"
DEEP_SEARCH_MODE = "deep"
# AD-3: 1단계 적용 대상은 웹검색뿐. 내부 문서검색은 플래그와 무관하게 legacy.
DEEP_SEARCH_TOOL_ID = "tavily_search"
_SEARCH_MODES = frozenset({LEGACY_SEARCH_MODE, DEEP_SEARCH_MODE})


class WorkflowCompiler:
    """WorkflowDefinition → Custom StateGraph CompiledGraph 동적 컴파일."""

    def __init__(
        self,
        tool_factory: ToolFactory,
        llm_factory: LLMFactoryInterface,
        logger: LoggerInterface,
        hooks: SupervisorHooks | None = None,
        agent_repository: AgentDefinitionRepositoryInterface | None = None,
        llm_model_repository: LlmModelRepositoryInterface | None = None,
        excel_analysis_workflow_getter: Callable[[], Any] | None = None,
        chart_max_count: int = 0,
        pipeline_llm_model: LlmModel | None = None,
        search_compress_threshold: int | None = None,
        search_pipeline_mode: str | None = None,
        document_template_repository=None,
        document_composer=None,
        document_generation_type_repository=None,
        document_generator=None,
        wiki_toc_provider=None,
        middleware_provider=None,
        presentation_generator=None,
        blueprint_repository=None,
        excel_generator=None,
        *,
        agent_timezone: str | None = None,
    ) -> None:
        self._tool_factory = tool_factory
        self._llm_factory = llm_factory
        self._logger = logger
        self._hooks = hooks or DefaultHooks()
        self._agent_repository = agent_repository
        self._llm_model_repository = llm_model_repository
        # analysis-node-agent: 분석 노드의 엑셀 분기에서 재사용할 ExcelAnalysisWorkflow.
        # None이면 엑셀 분기 비활성 → 문맥 분석으로 graceful fallback.
        self._excel_analysis_workflow_getter = excel_analysis_workflow_getter
        # supervisor-chart-builder-node: 차트 최대 개수. 0이면 chart_builder 노드 비활성
        # (chart_router → quality_gate 직결, 하위호환).
        self._chart_max_count = chart_max_count
        # search-node-query-pipeline D3: rewrite/validate/compress용 경량 LLM 모델.
        # None이면 per-run 에이전트 LLM 사용 (하위호환).
        self._pipeline_llm_model = pipeline_llm_model
        self._search_compress_threshold = search_compress_threshold
        # deep-search-pipeline FR-13: 미주입(None)은 하위호환 legacy — 경고 없음.
        # 알 수 없는 값은 생성 시점에 1회 경고하고 legacy로 폴백한다.
        self._search_pipeline_mode = self._normalize_search_mode(search_pipeline_mode)
        self._pipeline_llm_cache = None
        # document-template-extractor Design §4-1: 합성 노드 의존 (미주입 시 안내 노옵).
        self._document_template_repository = document_template_repository
        self._document_composer = document_composer
        # doc-generator §4-4: 생성 노드 의존 (미주입 시 안내 노옵 — D9).
        self._document_generation_type_repository = document_generation_type_repository
        self._document_generator = document_generator
        # wiki-agentic-navigation D1: 위키 목차 블록 공급자 (미주입 시 완전 비활성).
        self._wiki_toc_provider = wiki_toc_provider
        # builtin-middleware D6: 미들웨어 공급자 (미주입 시 미들웨어 0 — 무회귀).
        self._middleware_provider = middleware_provider
        # golden-sample-blueprint §2.1: 발표자료 생성 노드 의존 (미주입 시 안내 노옵).
        self._presentation_generator = presentation_generator
        self._blueprint_repository = blueprint_repository
        # excel-generator-node §2.1: 엑셀 생성 노드 의존 (미주입 시 안내 노옵).
        self._excel_generator = excel_generator
        # runtime-datetime-context D3: [현재 날짜] 블록 기준 타임존 (main.py가
        # settings.agent_timezone 주입). None이면 블록 생략 — 기존 동작·테스트 무회귀.
        self._agent_timezone = agent_timezone

    async def compile(
        self,
        workflow: WorkflowDefinition,
        llm_model: LlmModel,
        request_id: str,
        temperature: float = 0.0,
        supervisor_config: SupervisorConfig | None = None,
        depth: int = 0,
        visited: set[str] | None = None,
        *,
        tracker: Optional[RunTracker] = None,
        callback: Optional["UsageCallback"] = None,
        run_id: Optional[RunId] = None,
        auth_ctx: AuthContext | None = None,
        include_user_context: bool = True,
        agent_id: str | None = None,
    ):
        NestingDepthPolicy.validate_depth(depth)

        config = supervisor_config or SupervisorConfig()
        self._logger.info(
            "WorkflowCompiler compile start",
            request_id=request_id,
            worker_count=len(workflow.workers),
            provider=llm_model.provider,
            model_name=llm_model.model_name,
            depth=depth,
        )
        try:
            llm = self._llm_factory.create(llm_model, temperature)
            policy = QualityGatePolicy()

            # agent-user-context Design §4.4.2:
            # supervisor_prompt 앞에 사용자 컨텍스트 블록 prepend.
            # include_user_context=False면 prepend 생략 (system bot 등).
            # auth_ctx=None이면 render_user_context_block이 빈 문자열 반환 — graceful.
            # rag-auth-filter-fix D5: search 파이프라인에도 동일 게이팅으로 전달.
            user_context_block = (
                render_user_context_block(auth_ctx) if include_user_context else ""
            )
            # Design Ref: runtime-datetime-context §D6/§D7 — 요청당 1회 렌더 후
            # 수퍼바이저·워커·서브에이전트에 배포. include_user_context와 무관
            # (시스템 봇도 날짜는 받는다). 자정 경계에서 한 요청 내 날짜 불일치 방지.
            datetime_block = render_datetime_block(
                self._agent_timezone, logger=self._logger
            )
            # wiki-agentic-navigation D1/D2: wiki_read 워커 선택 + provider 주입 +
            # agent_id 전달(최상위 컴파일만 — sub_agent 재귀 미전달)일 때만 목차 조회.
            # 목차는 supervisor prepend + wiki_read 워커 prompt 이중 주입.
            wiki_toc_block = ""
            has_wiki_read = any(w.tool_id == "wiki_read" for w in workflow.workers)
            if has_wiki_read and self._wiki_toc_provider is not None and agent_id:
                wiki_toc_block = await self._wiki_toc_provider.render_block(
                    agent_id, request_id
                )
            # 블록 순서: 날짜 → 사용자 → wiki 목차 → 본문 (§D6)
            effective_supervisor_prompt = (
                datetime_block + user_context_block + wiki_toc_block
                + workflow.supervisor_prompt
            )

            # ToolFactory가 bind_auth_ctx를 지원하면 현재 auth_ctx 주입.
            # (Phase 5에서 ToolFactory에 메서드 추가됨)
            if hasattr(self._tool_factory, "bind_auth_ctx"):
                self._tool_factory.bind_auth_ctx(auth_ctx)

            # builtin-middleware D6: 적용 플랜 준비 — 최상위(depth=0) 1회.
            # sub_agent 재귀에는 미전달. agent_id 미상이면 enforced만
            # (default_builtin=False — 사용자 opt-out 무시 방지).
            middleware_plan = None
            if depth == 0 and self._middleware_provider is not None:
                middleware_plan = await self._middleware_provider.prepare(
                    agent_id, request_id, default_builtin=False
                )

            worker_map: dict[str, object] = {}
            # search/analysis 처럼 LLM 래핑 없이 직접 실행되는 "함수형 노드" id 집합.
            # 노드 등록 시 _wrap_worker 우회 판별에 사용(취약한 isinstance 휴리스틱 대체).
            function_node_ids: set[str] = set()
            # analysis-chart-router: analysis 카테고리 워커는 직후 chart_router로 보낸다.
            analysis_worker_ids: set[str] = set()
            # Design Ref: fix-mcp-tool-call-not-reaching-server §6.2 —
            # 도구 생성에 실패해 그래프에서 제외된 워커. supervisor 목록에서도 뺀다.
            failed_worker_ids: set[str] = set()

            for worker_def in workflow.workers:
                if worker_def.worker_type == "sub_agent":
                    sub_node = await self._compile_sub_agent(
                        worker_def=worker_def,
                        llm_model=llm_model,
                        request_id=request_id,
                        temperature=temperature,
                        supervisor_config=config,
                        depth=depth + 1,
                        visited=visited or set(),
                        tracker=tracker,
                        callback=callback,
                        run_id=run_id,
                        auth_ctx=auth_ctx,
                        include_user_context=include_user_context,
                    )
                    worker_map[worker_def.worker_id] = sub_node
                    continue

                # document-template-extractor Design §4-1: 전용 합성 노드.
                # ToolFactory 미경유 (단일 툴 react agent 미채택 — Plan §3-3).
                if worker_def.tool_id == "document_extractor":
                    worker_map[worker_def.worker_id] = (
                        self._create_document_extractor_node(
                            llm, worker_def,
                            auth_ctx=auth_ctx, request_id=request_id,
                        )
                    )
                    function_node_ids.add(worker_def.worker_id)
                    continue

                # doc-generator Design §4-4: 전용 생성 노드 (추출기 동형).
                # 조사·분석은 상류 워커 담당 — 노드는 누적 컨텍스트만 소비 (D1).
                if worker_def.tool_id == "document_generator":
                    worker_map[worker_def.worker_id] = (
                        self._create_document_generator_node(
                            llm, worker_def,
                            auth_ctx=auth_ctx, request_id=request_id,
                        )
                    )
                    function_node_ids.add(worker_def.worker_id)
                    continue

                # golden-sample-blueprint §2.2: 발표자료 생성 노드 (문서생성기 동형).
                if worker_def.tool_id == "presentation_generator":
                    worker_map[worker_def.worker_id] = (
                        self._create_presentation_generator_node(
                            llm, worker_def,
                            auth_ctx=auth_ctx, request_id=request_id,
                            callback=callback,
                        )
                    )
                    function_node_ids.add(worker_def.worker_id)
                    continue

                # excel-generator-node §2.1: 엑셀 생성 전용 노드 (문서생성기 동형).
                # ToolFactory 미경유 — 소싱·저장·링크까지 노드가 완결.
                if worker_def.tool_id == "excel_export":
                    worker_map[worker_def.worker_id] = (
                        self._create_excel_generator_node(
                            llm, worker_def,
                            auth_ctx=auth_ctx, request_id=request_id,
                        )
                    )
                    function_node_ids.add(worker_def.worker_id)
                    continue

                category = self._resolve_category(worker_def)

                # analysis 노드는 도구를 직접 쓰지 않으므로 tool 생성을 생략한다.
                if category == "analysis":
                    worker_map[worker_def.worker_id] = self._create_analysis_node(
                        llm, worker_def.worker_id, workflow.supervisor_prompt,
                    )
                    function_node_ids.add(worker_def.worker_id)
                    analysis_worker_ids.add(worker_def.worker_id)
                    continue

                # Design Ref: fix-mcp-tool-call-not-reaching-server §6.1 E6 —
                # 레거시 mcp_{server} 워커는 서버의 도구 전체를 받아야 한다.
                # 첫 도구만 넘기면 나머지는 LLM 도구 목록에 없어 호출이 성립하지
                # 않고 MCP 서버에 요청이 가지 않는다(module-1 실측).
                if parse_mcp_tool_id(worker_def.tool_id) is not None:
                    # Design Ref: §6.2 — MCP 서버 1개 장애가 에이전트 전체를
                    # 죽이지 않도록 워커 단위로 격리한다. tool_registry가 서버
                    # 단위로 쓰는 격리 철학을 워커 레벨에 맞춘 것.
                    # 배선 오류(E1/E2)는 격리 대상이 아니다 — 조용한 실패 재발 방지.
                    try:
                        worker_tools = await self._tool_factory.create_all_async(
                            worker_def.tool_id, request_id,
                            tool_config=worker_def.tool_config,
                        )
                    except McpWiringError:
                        # Design Ref: §6.2 — 배선 누락은 개발자 실수다.
                        # 격리하면 워커만 조용히 사라져 이 사이클의 실패 모드가
                        # 그대로 재발한다. 즉시 드러나도록 전파한다.
                        raise
                    except Exception as e:
                        self._logger.error(
                            "MCP worker tool creation failed",
                            request_id=request_id,
                            worker_id=worker_def.worker_id,
                            tool_id=worker_def.tool_id,
                            exception=e,
                        )
                        failed_worker_ids.add(worker_def.worker_id)
                        continue
                else:
                    worker_tools = [self._tool_factory.create(
                        worker_def.tool_id, request_id,
                        tool_config=worker_def.tool_config,
                    )]
                # search 노드·wiki 분기는 단일 도구 계약을 유지한다.
                tool = worker_tools[0]

                if category == "search":
                    # deep-search-pipeline FR-13: 모드에 따라 legacy/deep 팩토리 선택.
                    worker_map[worker_def.worker_id] = self._create_search_node(
                        worker_id=worker_def.worker_id,
                        tool_id=worker_def.tool_id,
                        tool=tool,
                        llm=llm,
                        user_context_block=user_context_block,
                        datetime_block=datetime_block,  # §D4 (FR-05a)
                    )
                    function_node_ids.add(worker_def.worker_id)
                else:
                    if worker_def.tool_id == "wiki_read" and wiki_toc_block:
                        # D1: 워커 LLM도 목차를 봐야 열람할 문서 id를 고를 수 있다.
                        # wiki-folder-summaries D6: 폴더 지도 모드면 wiki_list를
                        # 동봉해 지도→진입→열람 체인이 한 react 루프에서 완결.
                        is_folder_mode = wiki_toc_block.startswith(
                            WIKI_FOLDER_HEADER_TAG
                        )
                        wiki_tools = [tool]
                        instruction = _WIKI_WORKER_INSTRUCTION
                        if is_folder_mode:
                            instruction = _WIKI_FOLDER_WORKER_INSTRUCTION
                            try:
                                wiki_tools.append(
                                    self._tool_factory.create(
                                        "wiki_list", request_id
                                    )
                                )
                            except ValueError as e:
                                # 미배선 시 동봉 생략 — wiki_read 단독 폴백
                                self._logger.warning(
                                    "wiki_list bundling skipped",
                                    request_id=request_id, exception=e,
                                )
                        worker_agent = create_agent(
                            model=llm, tools=wiki_tools,
                            name=worker_def.worker_id,
                            # §D5: 날짜 → 목차 → 지시
                            system_prompt=datetime_block + wiki_toc_block + instruction,
                            middleware=_instantiate(middleware_plan),
                        )
                    else:
                        # §D5 (FR-05b): 시스템 프롬프트가 없던 일반 워커에 날짜 블록.
                        # 빈 문자열은 넘기지 않는다 — 미배선 시 기존 호출 형태 보존.
                        worker_kwargs = (
                            {"system_prompt": datetime_block} if datetime_block else {}
                        )
                        worker_agent = create_agent(
                            model=llm, tools=worker_tools, name=worker_def.worker_id,
                            middleware=_instantiate(middleware_plan),
                            **worker_kwargs,
                        )
                    worker_map[worker_def.worker_id] = worker_agent

            # final-answer-node D2: answer_agent 가상 워커 방식 제거 —
            # 최종 답변은 supervisor의 선택이 아닌 라우팅(route_to_worker_or_final)이 보장.
            # Design Ref: §6.2 — 도구 생성에 실패한 워커는 supervisor가 라우팅할 수
            # 없다. 전부 실패했다면 빈 그래프를 만드는 대신 실패시킨다(U14).
            workers_for_supervisor = [
                w for w in workflow.workers if w.worker_id not in failed_worker_ids
            ]
            if workflow.workers and not workers_for_supervisor:
                raise ValueError(
                    "All workers failed tool creation — cannot compile workflow "
                    f"(failed: {sorted(failed_worker_ids)})"
                )

            # 첨부/시각화 라우팅: analysis 워커가 있고 외부 주입 훅이 없을(기본) 때만
            # AttachmentRoutingHooks로 대체. 명시적 주입 훅은 존중(테스트/확장).
            # viz_policy는 chart_router와 동일 정책 — 강제 라우팅·prompt·라우터 판단 정렬.
            effective_hooks = self._hooks
            viz_policy = None
            if analysis_worker_ids:
                viz_policy = VisualizationRoutingPolicy()
                if isinstance(self._hooks, DefaultHooks):
                    effective_hooks = AttachmentRoutingHooks(
                        sorted(analysis_worker_ids), viz_policy=viz_policy,
                        logger=self._logger,
                    )

            supervisor_fn = create_supervisor_node(
                llm=llm,
                workers=workers_for_supervisor,
                supervisor_prompt=effective_supervisor_prompt,
                hooks=effective_hooks,
                logger=self._logger,
                analysis_worker_ids=sorted(analysis_worker_ids),
                viz_policy=viz_policy,
                # doc-generator D6: 문서 생성 라우팅 판단 기준 (강제 아님)
                docgen_guidance_block=self._render_docgen_guidance_block(
                    workflow.workers
                ),
            )
            quality_gate_fn = create_quality_gate_node(
                policy=policy, logger=self._logger,
            )

            # M3 (AGENT-OBS-003): 노드 함수를 track_step 컨텍스트 매니저로 감싸
            # ai_run_step 자동 영속화 + ai_tool_call.step_id / ai_llm_call.step_id FK 자동 연결.
            # tracker/callback/run_id 중 하나라도 None이면 원본 fn 그대로 반환 (관측성 비활성).
            _logger = self._logger

            def _wrap_step(
                node_name: str,
                node_type: NodeType,
                fn: Callable[[Any], Awaitable[Any]],
            ) -> Callable[[Any], Awaitable[Any]]:
                if tracker is None or callback is None or run_id is None:
                    return fn

                async def wrapped(state: Any) -> Any:
                    input_summary = _summarize_state_input(state)
                    async with track_step(
                        tracker=tracker,
                        callback=callback,
                        run_id=run_id,
                        node_name=node_name,
                        node_type=node_type,
                        input_summary=input_summary,
                        logger=_logger,
                    ) as step_ctx:
                        result = await fn(state)
                        forced_summary = (
                            result.pop(STEP_OUTPUT_SUMMARY_KEY, None)
                            if isinstance(result, dict) else None
                        )
                        step_ctx.output_summary = (
                            forced_summary or _summarize_state_output(result)
                        )
                        return result
                return wrapped

            graph = StateGraph(SupervisorState)
            graph.add_node(
                "supervisor",
                _wrap_step("supervisor", NodeType.SUPERVISOR, supervisor_fn),
            )
            # agent-instruction-required: 워커 0개(순수 대화형)면 quality_gate로
            # 향하는 진입 간선이 없어 고아 노드가 된다 → 워커가 있을 때만 등록.
            if worker_map:
                graph.add_node(
                    "quality_gate",
                    _wrap_step("quality_gate", NodeType.GATE, quality_gate_fn),
                )

            for worker_id, worker_agent in worker_map.items():
                if worker_id in function_node_ids:
                    graph.add_node(
                        worker_id,
                        _wrap_step(worker_id, NodeType.WORKER, worker_agent),
                    )
                else:
                    graph.add_node(
                        worker_id,
                        _wrap_step(
                            worker_id,
                            NodeType.WORKER,
                            self._wrap_worker(worker_id, worker_agent),
                        ),
                    )

            # final-answer-node D4: 최상위(depth=0) 그래프에만 최종 답변 노드 등록.
            # sub_agent는 원시 결과를 부모에게 그대로 반환(토큰 이중 정제 방지).
            # 프롬프트는 사용자 컨텍스트 블록이 포함된 effective_supervisor_prompt 사용.
            if depth == 0:
                graph.add_node(
                    "final_answer",
                    _wrap_step(
                        "final_answer",
                        NodeType.OTHER,
                        self._create_final_answer_node(
                            llm, effective_supervisor_prompt,
                        ),
                    ),
                )

            # analysis-chart-router: analysis 워커가 있을 때만 라우터 노드 등록.
            if analysis_worker_ids:
                chart_router_fn = create_chart_router_node(
                    policy=VisualizationRoutingPolicy(),
                    logger=self._logger,
                    classifier=LangChainVisualizationClassifier(llm),
                )
                graph.add_node(
                    "chart_router",
                    _wrap_step("chart_router", NodeType.OTHER, chart_router_fn),
                )
                # supervisor-chart-builder-node: chart_max_count>0일 때만 빌더 노드 등록.
                # 빌더는 compile 내 per-run llm으로 생성(에이전트 모델 일관, classifier와 동일).
                if self._chart_max_count > 0:
                    chart_builder = LangChainChartBuilder(
                        llm=llm,
                        logger=self._logger,
                        style_policy=ChartStylePolicy(),
                        max_count=self._chart_max_count,
                    )
                    graph.add_node(
                        "chart_builder",
                        _wrap_step(
                            "chart_builder",
                            NodeType.OTHER,
                            create_chart_builder_node(chart_builder, self._logger),
                        ),
                    )

            graph.set_entry_point("supervisor")

            route_map = {wid: wid for wid in worker_map}
            route_map["__end__"] = END
            if depth == 0:
                # FINISH 시 워커 실행 이력이 있으면 final_answer 필수 경유 (D1).
                route_map["final_answer"] = "final_answer"
                graph.add_conditional_edges(
                    "supervisor", route_to_worker_or_final, route_map,
                )
            else:
                graph.add_conditional_edges("supervisor", route_to_worker, route_map)

            for worker_id in worker_map:
                if worker_id in analysis_worker_ids:
                    # analysis 워커 직후에만 라우터 경유 (그 외 워커는 quality_gate 직결).
                    graph.add_edge(worker_id, "chart_router")
                else:
                    graph.add_edge(worker_id, "quality_gate")

            if analysis_worker_ids:
                if self._chart_max_count > 0:
                    # visualize → chart_builder → quality_gate, text → quality_gate
                    graph.add_conditional_edges(
                        "chart_router",
                        route_after_chart_router,
                        {"visualize": "chart_builder", "text": "quality_gate"},
                    )
                    graph.add_edge("chart_builder", "quality_gate")
                else:
                    # 하위호환: 빌더 비활성 시 라우터는 viz_decision만 기록하고 진행.
                    graph.add_edge("chart_router", "quality_gate")

            if depth == 0:
                # final-answer-node D3: 워커별 quality_gate를 이미 통과했으므로 END 직행.
                graph.add_edge("final_answer", END)

            # quality_gate는 워커가 있을 때만 등록되므로 발신 간선도 동일 조건.
            if worker_map:
                qg_route_map = {"supervisor": "supervisor"}
                for wid in worker_map:
                    qg_route_map[wid] = wid
                graph.add_conditional_edges(
                    "quality_gate", route_after_quality, qg_route_map
                )

            compiled = graph.compile()
            self._logger.info("WorkflowCompiler compile done", request_id=request_id)
            return compiled
        except Exception as e:
            self._logger.error(
                "WorkflowCompiler compile failed", exception=e, request_id=request_id,
            )
            raise

    async def _compile_sub_agent(
        self,
        worker_def: WorkerDefinition,
        llm_model: LlmModel,
        request_id: str,
        temperature: float,
        supervisor_config: SupervisorConfig,
        depth: int,
        visited: set[str],
        *,
        tracker: Optional[RunTracker] = None,
        callback: Optional["UsageCallback"] = None,
        run_id: Optional[RunId] = None,
        auth_ctx: AuthContext | None = None,
        include_user_context: bool = True,
    ):
        if self._agent_repository is None:
            raise ValueError("agent_repository is required for sub_agent compilation")

        ref_id = worker_def.ref_agent_id
        CircularReferencePolicy.validate_no_cycle(ref_id, visited)

        sub_agent = await self._agent_repository.find_by_id(ref_id, request_id)
        if sub_agent is None or sub_agent.status == "deleted":
            raise ValueError(f"서브 에이전트를 찾을 수 없습니다: {ref_id}")

        sub_llm_model = llm_model
        if self._llm_model_repository and sub_agent.llm_model_id != llm_model.id:
            resolved = await self._llm_model_repository.find_by_id(
                sub_agent.llm_model_id, request_id
            )
            if resolved:
                sub_llm_model = resolved

        new_visited = visited | {ref_id}
        sub_workflow = sub_agent.to_workflow_definition()
        # sub_agent 자체의 include_user_context flag도 존중 (부모 false면 자식도 false).
        sub_include = include_user_context and sub_agent.include_user_context
        sub_graph = await self.compile(
            workflow=sub_workflow,
            llm_model=sub_llm_model,
            request_id=request_id,
            temperature=sub_agent.temperature,
            supervisor_config=supervisor_config,
            depth=depth,
            visited=new_visited,
            tracker=tracker,
            callback=callback,
            run_id=run_id,
            auth_ctx=auth_ctx,
            include_user_context=sub_include,
        )

        return self._wrap_sub_agent(worker_def.worker_id, sub_graph)

    def _resolve_category(self, worker_def: WorkerDefinition) -> str:
        """카테고리 결정: DB 오버라이드 → TOOL_REGISTRY → 기본값 "action"."""
        if worker_def.category is not None:
            return worker_def.category
        try:
            meta = get_tool_meta(worker_def.tool_id)
            return meta.category
        except ValueError:
            return "action"

    def _create_final_answer_node(self, llm, system_prompt: str):
        """모든 워커 결과(검색·분석·차트)를 종합하는 필수 최종 답변 노드.

        final-answer-node Design §3-3. 워커가 실행된 런은 route_to_worker_or_final이
        종료 직전 이 노드를 구조적으로 경유시킨다 (depth=0 한정, END 직행).

        FIX-ANSWER-NODE-MULTITURN-CONTEXT 계승:
        워커 산출물 AIMessage(name=worker_id)는 system prompt의 컨텍스트 블록과
        중복되므로 messages 본체에서 제외하고, 나머지 대화 맥락은 모두 LLM에 전달.

        charts 비파괴: state["charts"]는 읽기 전용 메타 참조만 하고 반환 dict에
        포함하지 않는다 → 프론트로 가는 차트 페이로드 보존.
        """
        logger = self._logger

        async def final_answer_node(state: SupervisorState) -> dict:
            messages = state["messages"]
            worker_outputs = [m for m in messages if _is_worker_output(m)]
            search_results = [
                getattr(m, "content", "")
                for m in worker_outputs if _is_search_result(m)
            ]
            work_results = [
                f"[{getattr(m, 'name', '')}]\n{getattr(m, 'content', '')}"
                for m in worker_outputs if not _is_search_result(m)
            ]
            # worker-toolmessage-leak-fix D2: tool 역할 메시지는 선행 tool_calls
            # 짝이 필터로 깨질 수 있어 제외 — OpenAI는 고아 tool에 400을 반환.
            conversation_messages = [
                m for m in messages
                if not _is_worker_output(m) and not _is_tool_message(m)
            ]
            charts = state.get("charts", [])

            blocks: list[str] = []
            if search_results:
                blocks.append(
                    "[수집된 검색 결과]\n" + "\n\n---\n\n".join(search_results)
                )
            if work_results:
                blocks.append(
                    "[워커 작업 결과]\n" + "\n\n---\n\n".join(work_results)
                )
            if charts:
                blocks.append(
                    f"[생성된 차트]\n"
                    f"아래 {len(charts)}개의 차트가 답변과 함께 화면에 표시됩니다. "
                    f"차트 JSON이나 코드블록을 출력하지 말고, "
                    f"답변에서 차트를 자연스럽게 언급하세요.\n"
                    f"{_summarize_charts(charts)}"
                )
            if not blocks:
                logger.warning("final_answer_node: no worker outputs found")
                blocks.append("(수집된 결과 없음)")

            # agent-recursion-limit D7-①: 한도 도달 시 안내 지시 블록 추가.
            limit_notice = ""
            if state.get("limit_reached"):
                limit_notice = (
                    "\n\n[반복 한도 도달 안내]\n"
                    "실행 반복 한도에 도달하여 지금까지 수집된 정보만으로 "
                    "답변합니다. 이 사실을 답변에서 자연스럽게 언급하고, "
                    "수집 정보가 부족한 부분은 추측하지 말고 부족하다고 "
                    "명시하세요."
                )

            answer_prompt = (
                f"{system_prompt}\n\n"
                f"아래 수집된 결과들을 종합하여 사용자의 가장 최근 질문에 "
                f"하나의 완결된 답변을 작성하세요.\n"
                f"수집된 결과에 없는 내용은 추측하지 마세요. "
                f"이전 대화 맥락도 참고하세요.\n\n"
                + "\n\n".join(blocks)
                + limit_notice
            )

            # fix-anthropic-prefill-error: name 없는 assistant-last 방어.
            llm_messages = [
                {"role": "system", "content": answer_prompt},
                *ensure_user_tail(
                    conversation_messages,
                    instruction=(
                        "수집된 결과를 종합하여 마지막 질문에 대한 "
                        "최종 답변을 작성하세요."
                    ),
                ),
            ]

            logger.info(
                "final_answer_node executing",
                search_result_count=len(search_results),
                work_result_count=len(work_results),
                chart_count=len(charts),
                conversation_message_count=len(conversation_messages),
            )

            response = await llm.ainvoke(llm_messages)

            token_delta = len(response.content) // 4 if hasattr(response, "content") else 0

            return {
                "messages": [response],
                "last_worker_id": "final_answer",
                "token_usage": state["token_usage"] + token_delta,
            }

        return final_answer_node

    def _normalize_search_mode(self, mode: str | None) -> str:
        """search 파이프라인 모드 정규화 (deep-search-pipeline FR-13).

        미주입(None)은 하위호환 legacy — 경고하지 않는다.
        알 수 없는 값은 여기서 1회 경고하고 legacy로 폴백한다(조용한 폴백 금지).
        """
        if mode is None:
            return LEGACY_SEARCH_MODE
        normalized = mode.strip().lower()
        if normalized in _SEARCH_MODES:
            return normalized
        self._logger.warning(
            "unknown search_pipeline_mode, falling back to legacy",
            search_pipeline_mode=mode, allowed=sorted(_SEARCH_MODES),
        )
        return LEGACY_SEARCH_MODE

    def _resolve_search_mode(self, tool_id: str) -> str:
        """이 도구에 적용할 파이프라인 결정 (D9).

        AD-3을 코드가 강제한다 — deep은 웹검색 도구에만 적용되며, 내부 문서검색은
        플래그와 무관하게 legacy를 탄다.
        """
        if self._search_pipeline_mode == DEEP_SEARCH_MODE and tool_id == DEEP_SEARCH_TOOL_ID:
            return DEEP_SEARCH_MODE
        return LEGACY_SEARCH_MODE

    def _deep_search_policy(self) -> DeepSearchBudgetPolicy:
        """deep 파이프라인 예산 정책 — 상수는 도메인에 있다."""
        return DeepSearchBudgetPolicy()

    def _create_search_node(
        self,
        worker_id: str,
        tool_id: str,
        tool,
        llm,
        user_context_block: str = "",
        datetime_block: str = "",
    ):
        """search 워커 노드 생성. 두 팩토리는 시그니처·반환 계약이 동일하다 (AD-1)."""
        pipeline_llm = self._resolve_pipeline_llm(llm)
        if self._resolve_search_mode(tool_id) == DEEP_SEARCH_MODE:
            return create_deep_search_node(
                worker_id=worker_id,
                tool=tool,
                pipeline_llm=pipeline_llm,
                policy=self._deep_search_policy(),
                logger=self._logger,
                user_context_block=user_context_block,
                datetime_block=datetime_block,
            )
        # search-node-query-pipeline: rewrite → search → validate → compress
        return create_search_pipeline_node(
            worker_id=worker_id,
            tool=tool,
            pipeline_llm=pipeline_llm,
            policy=SearchPipelinePolicy(self._search_compress_threshold),
            logger=self._logger,
            user_context_block=user_context_block,
            datetime_block=datetime_block,
        )

    def _resolve_pipeline_llm(self, run_llm):
        """search 파이프라인용 경량 LLM 해석 (search-node-query-pipeline D3).

        - pipeline_llm_model 미주입(None) → per-run LLM 그대로 (하위호환)
        - 생성 성공 시 인스턴스 캐시 (compile 재귀·반복 호출 간 재사용)
        - 생성 실패(API 키 부재 등) → warning 로그 + per-run LLM fallback
        """
        if self._pipeline_llm_model is None:
            return run_llm
        if self._pipeline_llm_cache is not None:
            return self._pipeline_llm_cache
        try:
            self._pipeline_llm_cache = self._llm_factory.create(
                self._pipeline_llm_model, 0.0,
            )
            return self._pipeline_llm_cache
        except Exception as e:
            self._logger.warning(
                "search pipeline llm creation failed, falling back to run llm",
                provider=self._pipeline_llm_model.provider,
                model_name=self._pipeline_llm_model.model_name,
                error=str(e),
            )
            return run_llm

    def _create_document_extractor_node(
        self, llm, worker_def: WorkerDefinition, *, auth_ctx, request_id: str,
    ):
        """문서추출기 전용 합성 노드 (document-template-extractor Design §4-2).

        지정 템플릿 로드 → 누적 컨텍스트(근거+대화) → Composer(합성 LLM 1회 +
        순수 토큰 치환 + MCP html→pdf/doc) → 다운로드 참조 AIMessage 반환.
        가드 실패(미배선/템플릿 부재)는 안내 노옵 — 그래프 비중단 (§4-4 하위호환).
        """
        logger = self._logger
        repo = self._document_template_repository
        composer = self._document_composer
        worker_id = worker_def.worker_id
        tool_config = worker_def.tool_config or {}
        owner_user_id = str(auth_ctx.user_id) if auth_ctx is not None else ""

        def _reply(state: SupervisorState, content: str) -> dict:
            from langchain_core.messages import AIMessage

            return {
                "messages": [AIMessage(content=content, name=worker_id)],
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + len(content) // 4,
            }

        async def document_extractor_node(state: SupervisorState) -> dict:
            from src.domain.document_extractor.exceptions import (
                ComposeError,
                McpConversionError,
            )
            from src.domain.document_extractor.tool_config import (
                DocumentExtractorToolConfig,
            )

            if repo is None or composer is None:
                return _reply(state, (
                    "문서추출기가 아직 구성되지 않았습니다 "
                    "(document_template_repository/composer 미배선)."
                ))
            template_id = tool_config.get("template_id", "")
            if not template_id:
                return _reply(state, (
                    "등록된 문서 템플릿이 없습니다. "
                    "에이전트 편집에서 양식을 업로드해 등록해주세요."
                ))
            template = await repo.find_by_id(template_id, request_id)
            if template is None or template.status != "active":
                return _reply(state, (
                    "문서 템플릿을 찾을 수 없습니다(삭제되었을 수 있음). "
                    "에이전트 편집에서 양식을 다시 등록해주세요."
                ))

            evidence_block, conversation_block = self._split_fill_context(
                state["messages"]
            )
            try:
                config = DocumentExtractorToolConfig(**tool_config)
                result = await composer.compose(
                    llm=llm,
                    template=template,
                    tool_config=config,
                    evidence_block=evidence_block,
                    conversation_block=conversation_block,
                    owner_user_id=owner_user_id,
                    request_id=request_id,
                )
            except (ComposeError, McpConversionError, ValueError) as e:
                logger.error(
                    "document_extractor_node compose failed",
                    exception=e,
                    request_id=request_id,
                    template_id=template_id,
                )
                return _reply(state, f"문서 생성 실패: {e}")

            logger.info(
                "document_extractor_node done",
                request_id=request_id,
                template_id=template_id,
                file_id=result.file_id,
                unfilled_count=len(result.unfilled_labels),
            )
            return _reply(state, self._render_compose_summary(template, result))

        return document_extractor_node

    def _create_document_generator_node(
        self, llm, worker_def: WorkerDefinition, *, auth_ctx, request_id: str,
    ):
        """문서생성기 전용 생성 노드 (doc-generator Design §4-4, 추출기 동형).

        지정 문서 유형 로드 → 누적 컨텍스트(모든 워커 산출물+대화, D1) →
        DocumentGenerator(작성 LLM 1회+커버리지 재시도 + MCP html→pdf/doc) →
        다운로드 참조 AIMessage 반환. 가드 실패는 안내 노옵 — 그래프 비중단 (D9).
        """
        logger = self._logger
        repo = self._document_generation_type_repository
        generator = self._document_generator
        worker_id = worker_def.worker_id
        tool_config = worker_def.tool_config or {}
        owner_user_id = str(auth_ctx.user_id) if auth_ctx is not None else ""

        def _reply(state: SupervisorState, content: str) -> dict:
            from langchain_core.messages import AIMessage

            return {
                "messages": [AIMessage(content=content, name=worker_id)],
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + len(content) // 4,
            }

        async def document_generator_node(state: SupervisorState) -> dict:
            from src.domain.document_extractor.exceptions import (
                McpConversionError,
                McpToolNotConfiguredError,
            )
            from src.domain.document_generator.exceptions import GenerateError
            from src.domain.document_generator.tool_config import (
                DocumentGeneratorToolConfig,
            )

            if repo is None or generator is None:
                return _reply(state, (
                    "문서생성기가 아직 구성되지 않았습니다 "
                    "(document_generation_type_repository/generator 미배선)."
                ))
            type_id = tool_config.get("type_id", "")
            if not type_id:
                return _reply(state, (
                    "등록된 문서 유형이 없습니다. "
                    "에이전트 편집에서 문서 유형을 등록해주세요."
                ))
            gen_type = await repo.find_by_id(type_id, request_id)
            if gen_type is None or gen_type.status != "active":
                return _reply(state, (
                    "문서 유형을 찾을 수 없습니다(삭제되었을 수 있음). "
                    "에이전트 편집에서 문서 유형을 다시 등록해주세요."
                ))

            evidence_block, conversation_block = self._split_fill_context(
                state["messages"]
            )
            try:
                config = DocumentGeneratorToolConfig(**tool_config)
                result = await generator.generate(
                    llm=llm,
                    gen_type=gen_type,
                    tool_config=config,
                    evidence_block=evidence_block,
                    conversation_block=conversation_block,
                    owner_user_id=owner_user_id,
                    request_id=request_id,
                )
            except (
                GenerateError,
                McpConversionError,
                McpToolNotConfiguredError,
                ValueError,
            ) as e:
                logger.error(
                    "document_generator_node generate failed",
                    exception=e,
                    request_id=request_id,
                    type_id=type_id,
                )
                return _reply(state, f"문서 생성 실패: {e}")

            logger.info(
                "document_generator_node done",
                request_id=request_id,
                type_id=type_id,
                file_id=result.file_id,
                missing_count=len(result.missing_sections),
            )
            return _reply(state, self._render_generate_summary(gen_type, result))

        return document_generator_node

    @staticmethod
    def _render_generate_summary(gen_type, result) -> str:
        """생성 결과 AIMessage 본문 (D8) — 근거 사용 여부·누락 섹션 안내."""
        lines = [
            f"문서 「{gen_type.name}」 생성 완료 ({result.filename})",
            (
                f"다운로드: [{result.filename}]"
                f"(/api/v1/document-extractor/files/{result.file_id})"
            ),
        ]
        if not result.used_evidence:
            lines.append("(외부 근거 없이 대화 문맥 기반으로 작성됨)")
        if result.missing_sections:
            lines.append(
                "[누락 섹션(재시도 후에도 미포함 — 직접 확인 필요)] "
                + ", ".join(result.missing_sections)
            )
        return "\n".join(lines)

    def _create_excel_generator_node(
        self, llm, worker_def: WorkerDefinition, *, auth_ctx, request_id: str,
    ):
        """엑셀 생성 전용 노드 (excel-generator-node §2.1, 문서생성기 D9 동형).

        소스 수집(analysis_source·첨부·누적 컨텍스트) → ExcelGenerator
        (시트 계획 LLM 1회 + raw 무손실 복사/llm 상한 절단 + 저장) →
        다운로드 링크 AIMessage. 실패는 안내 노옵 — 그래프 비중단 (§6.1).
        """
        logger = self._logger
        generator = self._excel_generator
        worker_id = worker_def.worker_id
        owner_user_id = str(auth_ctx.user_id) if auth_ctx is not None else ""

        def _reply(state: SupervisorState, content: str) -> dict:
            from langchain_core.messages import AIMessage

            return {
                "messages": [AIMessage(content=content, name=worker_id)],
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + len(content) // 4,
            }

        async def excel_generator_node(state: SupervisorState) -> dict:
            from src.domain.excel_generator.exceptions import (
                ExcelGenerateError,
                NoExcelDataError,
            )

            if generator is None:
                return _reply(state, (
                    "엑셀 생성기가 아직 구성되지 않았습니다 "
                    "(excel_generator 미배선)."
                ))

            evidence_block, conversation_block = self._split_fill_context(
                state["messages"]
            )
            logger.info(
                "excel_generator_node start",
                request_id=request_id,
                worker_id=worker_id,
                analysis_source_count=len(state.get("analysis_source", [])),
                attachment_count=len(state.get("attachments", [])),
            )
            try:
                result = await generator.generate(
                    llm=llm,
                    analysis_source=state.get("analysis_source", []),
                    attachments=state.get("attachments", []),
                    evidence_block=evidence_block,
                    conversation_block=conversation_block,
                    owner_user_id=owner_user_id,
                    request_id=request_id,
                )
            except NoExcelDataError:
                return _reply(state, (
                    "엑셀로 정리할 데이터를 찾지 못했습니다. "
                    "먼저 데이터를 수집하거나 첨부해주세요."
                ))
            except (ExcelGenerateError, ValueError) as e:
                logger.error(
                    "excel_generator_node generate failed",
                    exception=e,
                    request_id=request_id,
                    worker_id=worker_id,
                )
                return _reply(state, f"엑셀 생성 실패: {e}")

            logger.info(
                "excel_generator_node done",
                request_id=request_id,
                worker_id=worker_id,
                file_id=result.file_id,
                sheet_count=result.sheet_count,
                total_rows=result.total_rows,
                truncated=result.truncated,
            )
            return _reply(state, self._render_excel_summary(result))

        return excel_generator_node

    @staticmethod
    def _render_excel_summary(result) -> str:
        """엑셀 생성 결과 AIMessage 본문 (excel-generator-node §4.3)."""
        from src.domain.excel_generator.policies import MAX_LLM_STRUCTURED_ROWS

        lines = [
            (
                f"엑셀 「{result.filename}」 생성 완료 "
                f"(시트 {result.sheet_count}개, {result.total_rows}행)"
            ),
            (
                f"다운로드: [{result.filename}]"
                f"(/api/v1/document-extractor/files/{result.file_id})"
            ),
        ]
        if result.truncated:
            lines.append(
                f"⚠️ 일부 데이터가 행 상한({MAX_LLM_STRUCTURED_ROWS}행)으로 "
                "축약되었습니다."
            )
        return "\n".join(lines)

    def _create_presentation_generator_node(
        self, llm, worker_def: WorkerDefinition, *, auth_ctx, request_id: str,
        callback=None,
    ):
        """발표자료 생성 노드 (golden-sample-blueprint §2.2, 문서생성기 D9 동형).

        blueprint 로드(inactive → 안내) → 누적 컨텍스트(근거/대화) →
        PresentationGenerationUseCase(계획·작성·렌더·저장·PDF) → 다운로드 참조 AIMessage.
        가드 실패는 안내 노옵 — 그래프 비중단.
        """
        logger = self._logger
        repo = self._blueprint_repository
        generator = self._presentation_generator
        worker_id = worker_def.worker_id
        tool_config = worker_def.tool_config or {}
        owner_user_id = str(auth_ctx.user_id) if auth_ctx is not None else ""

        def _reply(state: SupervisorState, content: str) -> dict:
            from langchain_core.messages import AIMessage

            return {
                "messages": [AIMessage(content=content, name=worker_id)],
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + len(content) // 4,
            }

        async def presentation_generator_node(state: SupervisorState) -> dict:
            from src.domain.blueprint.errors import PresentationGenerateError
            from src.domain.blueprint.tool_config import (
                PresentationGeneratorToolConfig,
            )

            if repo is None or generator is None:
                return _reply(state, (
                    "발표자료생성기가 아직 구성되지 않았습니다 "
                    "(blueprint_repository/presentation_generator 미배선)."
                ))
            blueprint_id = tool_config.get("blueprint_id", "")
            if not blueprint_id:
                return _reply(state, (
                    "선택된 양식(blueprint)이 없습니다. "
                    "에이전트 편집에서 발표자료 양식을 선택해주세요."
                ))
            blueprint = await repo.find_by_id(blueprint_id)
            if blueprint is None or blueprint.status != "active":
                return _reply(state, (
                    "양식(blueprint)을 찾을 수 없거나 비활성 상태입니다. "
                    "에이전트 편집에서 양식을 다시 선택해주세요."
                ))
            evidence_block, conversation_block = self._split_fill_context(
                state["messages"]
            )
            try:
                result = await generator.generate(
                    llm=llm,
                    blueprint=blueprint,
                    assets=await repo.load_assets(blueprint_id),
                    tool_config=PresentationGeneratorToolConfig(**tool_config),
                    evidence_block=evidence_block,
                    conversation_block=conversation_block,
                    user_instruction=_last_human_text(state["messages"]),
                    owner_user_id=owner_user_id,
                    request_id=request_id,
                    # Plan FR-17: UsageCallback 전달 → ai_llm_call 사용량 영속(관측 활성 시)
                    callbacks=[callback] if callback is not None else None,
                )
            except (PresentationGenerateError, ValueError) as e:
                logger.error(
                    "presentation_generator_node generate failed",
                    exception=e,
                    request_id=request_id,
                    blueprint_id=blueprint_id,
                )
                return _reply(state, f"발표자료 생성 실패: {e}")
            logger.info(
                "presentation_generator_node done",
                request_id=request_id,
                blueprint_id=blueprint_id,
                file_id=result.file_id,
                slide_count=result.slide_count,
                warnings=len(result.warnings),
            )
            return _reply(state, _render_presentation_summary(blueprint, result))

        return presentation_generator_node

    def _render_docgen_guidance_block(
        self, workers: list[WorkerDefinition]
    ) -> str:
        """문서 생성 라우팅 판단 기준 블록 (D6 — 순서 강제 아님).

        주입 조건: generator 워커 존재 and 그 외 워커 1개 이상.
        """
        generator_ids = [
            w.worker_id for w in workers
            if w.worker_type == "tool"
            and w.tool_id in ("document_generator", "presentation_generator")
        ]
        others = [w for w in workers if w.worker_id not in generator_ids]
        if not generator_ids or not others:
            return ""
        search_ids = [
            w.worker_id for w in others
            if w.worker_type == "tool" and self._resolve_category(w) == "search"
        ]
        analysis_ids = [
            w.worker_id for w in others
            if w.worker_type == "tool" and self._resolve_category(w) == "analysis"
        ]
        gen_list = ", ".join(generator_ids)
        lines = [
            "\n\n[문서 생성 처리 기준]",
            (
                f"문서 생성 요청 시: 문서 아웃라인을 채우는 데 필요한 정보가 "
                f"대화와 보유 데이터에 충분하면 다른 워커를 거치지 말고 바로 "
                f"문서생성 워커({gen_list})로 위임하세요"
                f"(예: 날짜·사유가 대화에 명시된 신청서류)."
            ),
        ]
        if search_ids:
            lines.append(
                f"외부/내부 근거 조사가 필요하면 검색 워커"
                f"({', '.join(search_ids)})를 먼저 호출해 수집한 뒤 위임하세요."
            )
        if analysis_ids:
            lines.append(
                f"데이터 분석이 필요하면 분석 워커"
                f"({', '.join(analysis_ids)})를 먼저 호출한 뒤 위임하세요."
            )
        lines.append(
            "문서생성 워커는 이전 워커들의 산출물 전체를 근거로 사용합니다."
        )
        return "\n".join(lines)

    @staticmethod
    def _split_fill_context(messages: list) -> tuple[str, str]:
        """누적 state.messages → (근거 블록, 대화 블록) 분리 (GB2).

        근거 = 상류 워커 산출물(AIMessage name=worker_id 규약), 대화 = 나머지.
        """
        worker_outputs = [m for m in messages if _is_worker_output(m)]
        conversation = [m for m in messages if not _is_worker_output(m)]
        evidence_block = "\n\n---\n\n".join(
            f"[{getattr(m, 'name', '')}]\n{getattr(m, 'content', '')}"
            for m in worker_outputs
        )
        conversation_block = "\n".join(
            str(getattr(m, "content", m)) for m in conversation
        )
        return evidence_block, conversation_block

    @staticmethod
    def _render_compose_summary(template, result) -> str:
        """합성 결과 AIMessage 본문 (Design §4-2) — 채운 값 병기(R3) + 공란 안내(GB6)."""
        lines = [
            f"문서 「{template.name}」 생성 완료 ({result.filename})",
            (
                f"다운로드: [{result.filename}]"
                f"(/api/v1/document-extractor/files/{result.file_id})"
            ),
        ]
        if result.filled_slots:
            filled = " · ".join(
                f"{label}={value}" for label, value in result.filled_slots.items()
            )
            lines.append(f"[채운 항목] {filled}")
        if result.unfilled_labels:
            lines.append(
                "[공란(근거 없음 — 직접 확인 필요)] "
                + ", ".join(result.unfilled_labels)
            )
        return "\n".join(lines)

    def _create_analysis_node(self, llm, worker_id: str, system_prompt: str):
        """분석 전용 노드.

        - attachments에 엑셀이 있고 getter가 주입돼 있으면 ExcelAnalysisWorkflow 래핑 호출.
        - 그 외에는 직전 검색결과(있으면)/전체 대화 문맥(없으면)을 질문 기준으로 LLM 분석.
        분석 결과만 AIMessage(name=worker_id)로 반환하고 supervisor로 복귀(quality_gate 경유).
        """
        logger = self._logger
        get_excel_wf = self._excel_analysis_workflow_getter

        async def analysis_node(state: SupervisorState) -> dict:
            from langchain_core.messages import AIMessage

            messages = state["messages"]
            question = latest_user_question(messages)
            attachments = state.get("attachments", [])
            excel = next(
                (a for a in attachments if a.get("type") == "excel"), None
            )

            wf = get_excel_wf() if (excel and get_excel_wf is not None) else None
            source_items: list[dict] = []
            if wf is not None:
                branch = "excel"
                analysis_text, raw = await self._run_excel_analysis(
                    wf, question, excel, logger,
                )
                # analysis-source-preservation: 파싱 원천을 상태 채널로 노출.
                if raw is not None:
                    source_items = [
                        {"origin": worker_id, "kind": "raw_source", "excel": raw}
                    ]
            else:
                branch = "context"
                analysis_text = await self._analyze_context(
                    llm, system_prompt, question, messages,
                )

            logger.info(
                "analysis_node executing",
                worker_id=worker_id,
                branch=branch,
                question_length=len(question),
            )

            token_delta = len(analysis_text) // 4
            result = {
                "messages": [AIMessage(content=analysis_text, name=worker_id)],
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + token_delta,
            }
            # context 분기는 키 미포함 → SupervisorState.analysis_source 빈 배열 유지.
            if source_items:
                result["analysis_source"] = source_items
            return result

        return analysis_node

    async def _run_excel_analysis(
        self, wf, question: str, excel: dict, logger,
    ) -> tuple[str, dict | None]:
        """기존 ExcelAnalysisWorkflow 래핑 호출.

        Returns:
            (analysis_text, raw_excel_dict|None) — 원천은 파싱 성공분(sheets 키)만.
            예외 시 (에러 메시지, None) 반환(그래프 비중단).
        """
        initial = {
            "request_id": "",
            "user_query": question,
            "excel_data": {
                "file_path": excel.get("file_path", ""),
                "user_id": excel.get("user_id", ""),
            },
            "current_attempt": 0,
            "max_attempts": 3,
            "analysis_text": "",
            "confidence_score": 0.0,
            "hallucination_score": 0.0,
            "needs_web_search": False,
            "web_search_results": "",
            "attempts_history": [],
            "is_complete": False,
            "final_status": "pending",
            "error_message": "",
            "viz_decision": "",
            "charts": [],
            # analyze-user-context: ContextVar(run_agent_use_case에서 세팅됨) 기반 사용자 블록.
            "user_context_block": render_user_context_block(
                get_current_auth_context()
            ),
        }
        try:
            final = await wf.run(initial)
        except Exception as e:
            logger.error("analysis_node excel workflow failed", exception=e)
            return (f"엑셀 분석 실패: {e}", None)
        text = final.get("analysis_text", "") or "(엑셀 분석 결과 없음)"
        raw = final.get("excel_data")
        # 파싱 성공분만 원천으로 인정 (sheets = to_dict 결과). 미파싱 {file_path}는 제외.
        raw = raw if isinstance(raw, dict) and "sheets" in raw else None
        return (text, raw)

    async def _analyze_context(
        self, llm, system_prompt: str, question: str, messages: list
    ) -> str:
        """검색결과(있으면)/전체 대화 문맥(없으면)을 데이터로 질문에 대한 분석 수행."""
        search_results = [
            getattr(m, "content", "") for m in messages if _is_search_result(m)
        ]
        if search_results:
            context = "\n\n---\n\n".join(search_results)
            source_hint = "아래 검색 결과를 데이터로 삼아"
        else:
            context = "(별도 검색 결과 없음 — 전체 대화 문맥을 분석 대상으로 함)"
            source_hint = "아래 전체 대화 문맥을 데이터로 삼아"

        # fix-anthropic-prefill-error: 비검색 워커 출력이 마지막이면 user로 교정.
        conversation = ensure_user_tail(
            [m for m in messages if not _is_search_result(m)],
            instruction="위 데이터를 바탕으로 분석을 수행하세요.",
        )
        # analyze-user-context: ContextVar 기반 사용자 블록을 system prompt 앞에 prepend.
        # 미인증이면 ""라 기존 동작과 동일.
        user_block = render_user_context_block(get_current_auth_context())
        # Design Ref: runtime-datetime-context §D6 — 별도 호출 시점이라 재렌더.
        datetime_block = render_datetime_block(
            self._agent_timezone, logger=self._logger
        )
        # 분석 노드는 자연어 텍스트만 생성. 차트 생성은 chart_builder가 전담하므로
        # 공용 가이드로 출력 형식/범위를 못박는다(excel 분석 노드와 일원화).
        analysis_prompt = (
            f"{datetime_block}{user_block}{system_prompt}\n\n"
            f"당신은 데이터 분석가입니다. {source_hint} 사용자의 질문에 답합니다.\n\n"
            f"{ANALYSIS_OUTPUT_GUIDE}\n\n{DATA_GAP_GUIDE}\n\n"
            f"[분석 대상 데이터]\n{context}\n\n[질문]\n{question}"
        )
        response = await llm.ainvoke(
            [{"role": "system", "content": analysis_prompt}, *conversation]
        )
        content = response.content if hasattr(response, "content") else str(response)
        # 새어 나온 코드블록/JSON 제거 → chart_router/품질검증이 깨끗한 텍스트 수신.
        return ANALYSIS_OUTPUT_SANITIZER.strip(content)

    def _wrap_worker(self, worker_id: str, worker_agent):
        async def wrapped(state: SupervisorState) -> dict:
            # fix-anthropic-prefill-error: 직전 워커 AIMessage-last 상태로
            # react agent에 진입하면 Claude 4.6+ 가 prefill 거부(400).
            result = await worker_agent.ainvoke(
                {
                    "messages": ensure_user_tail(
                        state["messages"],
                        instruction=(
                            "위 대화 맥락과 이전 단계 결과를 참고하여 "
                            "당신의 역할에 해당하는 작업을 수행하세요."
                        ),
                    )
                }
            )
            result_messages = result.get("messages", [])

            # worker-toolmessage-leak-fix D1: 워커 규약은 최종 AIMessage(name) 1건.
            # react agent 내부 트레이스(tool_calls·ToolMessage)를 state로 유출하면
            # final_answer_node 필터가 짝을 깨 고아 tool 메시지가 됨 (OpenAI 400).
            answer_content = ""
            if result_messages:
                last = result_messages[-1]
                answer_content = (
                    last.content if hasattr(last, "content") else str(last)
                )

            answer_msg = AIMessage(content=answer_content, name=worker_id)
            token_delta = (
                len(answer_content) // 4 if isinstance(answer_content, str) else 0
            )

            return {
                "messages": [answer_msg],
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + token_delta,
            }

        return wrapped

    def _wrap_sub_agent(self, worker_id: str, sub_graph):
        async def wrapped(state: SupervisorState) -> dict:
            last_msg = state["messages"][-1]
            task_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            # agent-recursion-limit D8: 반복 한도는 부모의 절반(정책 상수, 하한 보장).
            # 기존 state(키 부재) 하위호환을 위해 get + 정책 기본값.
            sub_limit = IterationLimitPolicy.sub_agent_limit(
                state.get("max_iterations", IterationLimitPolicy.DEFAULT)
            )
            sub_initial = build_initial_state(
                messages=[{"role": "user", "content": task_content}],
                config=SupervisorConfig(
                    max_iterations=sub_limit,
                    token_limit=state["token_limit"] // 2,
                ),
                available_workers=[],
            )

            # 서브 그래프도 config 미전달 시 기본 recursion_limit(25 스텝)에
            # 걸리는 동일 결함이 있어 파생값을 함께 전달한다 (D8).
            result = await sub_graph.ainvoke(
                sub_initial,
                config={
                    "recursion_limit": IterationLimitPolicy.derive_recursion_limit(
                        sub_limit
                    ),
                },
            )
            sub_messages = result.get("messages", [])

            answer_content = ""
            if sub_messages:
                last = sub_messages[-1]
                answer_content = last.content if hasattr(last, "content") else str(last)

            from langchain_core.messages import AIMessage
            answer_msg = AIMessage(content=answer_content, name=worker_id)
            sub_token_usage = result.get("token_usage", 0)

            return {
                "messages": [answer_msg],
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + sub_token_usage,
            }

        return wrapped


def _last_human_text(messages: list) -> str:
    """사용자 지시 = 마지막 HumanMessage 본문 (없으면 빈 문자열)."""
    for m in reversed(messages):
        if getattr(m, "type", "") == "human":
            content = getattr(m, "content", "")
            return content if isinstance(content, str) else str(content)
    return ""


def _render_presentation_summary(blueprint, result) -> str:
    """발표자료 생성 결과 AIMessage 본문 — 다운로드 링크 + 경고."""
    lines = [
        f"발표자료 「{blueprint.name}」 생성 완료 ({result.filename}, "
        f"{result.slide_count}장, 차트 {result.chart_count}개)",
        (
            f"다운로드: [{result.filename}]"
            f"(/api/v1/document-extractor/files/{result.file_id})"
        ),
    ]
    if result.pdf_file_id:
        lines.append(
            f"PDF: [{blueprint.name}.pdf]"
            f"(/api/v1/document-extractor/files/{result.pdf_file_id})"
        )
    if result.warnings:
        lines.append("[주의] " + " / ".join(result.warnings[:5]))
    return "\n".join(lines)
