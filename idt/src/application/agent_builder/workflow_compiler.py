"""WorkflowCompiler: WorkflowDefinition → Custom StateGraph CompiledGraph 동적 컴파일."""
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent

from src.application.agent_builder.message_normalization import ensure_user_tail
from src.application.agent_builder.search_pipeline import (
    create_search_pipeline_node,
    is_search_result as _is_search_result,
    is_worker_output as _is_worker_output,
    latest_user_question,
)
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
from src.application.agent_run.prompt_rendering import render_user_context_block
from src.application.visualization.analysis_prompt import ANALYSIS_OUTPUT_GUIDE
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
from src.infrastructure.agent_builder.tool_factory import ToolFactory

if TYPE_CHECKING:
    from src.infrastructure.llm.usage_callback import UsageCallback


# search-node-query-pipeline D2: _is_search_result / _is_worker_output 정의는
# search_pipeline 모듈로 이동(메시지 규약 단일 출처). 본 모듈은 alias import로 사용.


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
        self._pipeline_llm_cache = None

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
            effective_supervisor_prompt = workflow.supervisor_prompt
            if include_user_context:
                block = render_user_context_block(auth_ctx)
                if block:
                    effective_supervisor_prompt = block + workflow.supervisor_prompt

            # ToolFactory가 bind_auth_ctx를 지원하면 현재 auth_ctx 주입.
            # (Phase 5에서 ToolFactory에 메서드 추가됨)
            if hasattr(self._tool_factory, "bind_auth_ctx"):
                self._tool_factory.bind_auth_ctx(auth_ctx)

            worker_map: dict[str, object] = {}
            # search/analysis 처럼 LLM 래핑 없이 직접 실행되는 "함수형 노드" id 집합.
            # 노드 등록 시 _wrap_worker 우회 판별에 사용(취약한 isinstance 휴리스틱 대체).
            function_node_ids: set[str] = set()
            # analysis-chart-router: analysis 카테고리 워커는 직후 chart_router로 보낸다.
            analysis_worker_ids: set[str] = set()

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

                category = self._resolve_category(worker_def)

                # analysis 노드는 도구를 직접 쓰지 않으므로 tool 생성을 생략한다.
                if category == "analysis":
                    worker_map[worker_def.worker_id] = self._create_analysis_node(
                        llm, worker_def.worker_id, workflow.supervisor_prompt,
                    )
                    function_node_ids.add(worker_def.worker_id)
                    analysis_worker_ids.add(worker_def.worker_id)
                    continue

                if worker_def.tool_id.startswith("mcp_"):
                    tool = await self._tool_factory.create_async(
                        worker_def.tool_id, request_id,
                        tool_config=worker_def.tool_config,
                    )
                else:
                    tool = self._tool_factory.create(
                        worker_def.tool_id, request_id,
                        tool_config=worker_def.tool_config,
                    )

                if category == "search":
                    # search-node-query-pipeline: rewrite → search → validate → compress
                    worker_map[worker_def.worker_id] = create_search_pipeline_node(
                        worker_id=worker_def.worker_id,
                        tool=tool,
                        pipeline_llm=self._resolve_pipeline_llm(llm),
                        policy=SearchPipelinePolicy(self._search_compress_threshold),
                        logger=self._logger,
                    )
                    function_node_ids.add(worker_def.worker_id)
                else:
                    worker_agent = create_react_agent(
                        llm, tools=[tool], name=worker_def.worker_id,
                    )
                    worker_map[worker_def.worker_id] = worker_agent

            # final-answer-node D2: answer_agent 가상 워커 방식 제거 —
            # 최종 답변은 supervisor의 선택이 아닌 라우팅(route_to_worker_or_final)이 보장.
            workers_for_supervisor = list(workflow.workers)

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
                    )

            supervisor_fn = create_supervisor_node(
                llm=llm,
                workers=workers_for_supervisor,
                supervisor_prompt=effective_supervisor_prompt,
                hooks=effective_hooks,
                logger=self._logger,
                analysis_worker_ids=sorted(analysis_worker_ids),
                viz_policy=viz_policy,
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

            qg_route_map = {"supervisor": "supervisor"}
            for wid in worker_map:
                qg_route_map[wid] = wid
            graph.add_conditional_edges("quality_gate", route_after_quality, qg_route_map)

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
            conversation_messages = [
                m for m in messages if not _is_worker_output(m)
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

            answer_prompt = (
                f"{system_prompt}\n\n"
                f"아래 수집된 결과들을 종합하여 사용자의 가장 최근 질문에 "
                f"하나의 완결된 답변을 작성하세요.\n"
                f"수집된 결과에 없는 내용은 추측하지 마세요. "
                f"이전 대화 맥락도 참고하세요.\n\n"
                + "\n\n".join(blocks)
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
            if wf is not None:
                branch = "excel"
                analysis_text = await self._run_excel_analysis(
                    wf, question, excel, logger,
                )
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
            return {
                "messages": [AIMessage(content=analysis_text, name=worker_id)],
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + token_delta,
            }

        return analysis_node

    async def _run_excel_analysis(self, wf, question: str, excel: dict, logger) -> str:
        """기존 ExcelAnalysisWorkflow 래핑 호출. 예외 시 에러 메시지 반환(그래프 비중단)."""
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
            return f"엑셀 분석 실패: {e}"
        return final.get("analysis_text", "") or "(엑셀 분석 결과 없음)"

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
        # 분석 노드는 자연어 텍스트만 생성. 차트 생성은 chart_builder가 전담하므로
        # 공용 가이드로 출력 형식/범위를 못박는다(excel 분석 노드와 일원화).
        analysis_prompt = (
            f"{user_block}{system_prompt}\n\n"
            f"당신은 데이터 분석가입니다. {source_hint} 사용자의 질문에 답합니다.\n\n"
            f"{ANALYSIS_OUTPUT_GUIDE}\n\n"
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
            new_messages = result.get("messages", [])

            token_delta = sum(
                len(getattr(m, "content", "")) // 4
                for m in new_messages
                if hasattr(m, "content")
            )

            return {
                "messages": new_messages,
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + token_delta,
            }

        return wrapped

    def _wrap_sub_agent(self, worker_id: str, sub_graph):
        async def wrapped(state: SupervisorState) -> dict:
            last_msg = state["messages"][-1]
            task_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            sub_initial = build_initial_state(
                messages=[{"role": "user", "content": task_content}],
                config=SupervisorConfig(
                    token_limit=state["token_limit"] // 2,
                ),
                available_workers=[],
            )

            result = await sub_graph.ainvoke(sub_initial)
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
