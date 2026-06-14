"""Excel Analysis Workflow using LangGraph.

엑셀 파일을 파싱하여 Claude AI로 분석하고,
할루시네이션 검증 후 최대 N회 재시도하는 Self-Corrective 워크플로우.

시각화는 분리된 chart_router로 일원화하며(viz_decision 기록), 웹 검색 필요 판단은
freeform 태그 파싱이 아닌 structured 결정(SearchDecisionInterface)으로 수행한다.
분석 답변(analysis_text)은 자연어 텍스트로 유지한다.
"""

from datetime import datetime
from typing import Annotated, Sequence, TypedDict

import operator
from langgraph.graph import END, StateGraph

from src.application.visualization.chart_builder_node import (
    create_chart_builder_node,
)
from src.application.visualization.analysis_prompt import ANALYSIS_OUTPUT_GUIDE
from src.application.agent_run.auth_context import get_current_auth_context
from src.application.agent_run.prompt_rendering import render_user_context_block
from src.application.visualization.chart_router import (
    create_chart_router_node,
    route_after_chart_router,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.visualization.analysis_output_policy import (
    ANALYSIS_OUTPUT_SANITIZER,
)
from src.domain.policies.analysis_policy import (
    AnalysisQualityThreshold,
    AnalysisRetryPolicy,
)
from src.domain.search_decision.interfaces import SearchDecisionInterface
from src.domain.visualization.interfaces import ChartBuilderInterface
from src.domain.visualization.policies import VisualizationRoutingPolicy
from src.infrastructure.llm.schemas import ClaudeModel, ClaudeRequest


class ExcelAnalysisState(TypedDict):
    """워크플로우 상태."""

    request_id: str
    user_query: str
    excel_data: dict

    current_attempt: int
    max_attempts: int

    analysis_text: str
    confidence_score: float
    hallucination_score: float

    needs_web_search: bool
    web_search_results: str

    attempts_history: Annotated[Sequence[dict], operator.add]

    is_complete: bool
    final_status: str
    error_message: str

    # analysis-chart-router: 분석 직후 라우터 판단 결과 ("visualize" | "text" | "").
    viz_decision: str

    # supervisor-chart-builder-node: chart_builder가 생성한 Chart.js config 리스트.
    charts: list

    # analyze-user-context: 분석 프롬프트 앞에 prepend할 렌더 완료 사용자 컨텍스트 블록.
    # 빈 문자열이면 미인증/미주입 → 프롬프트 변화 없음(회귀 0).
    user_context_block: str


class ExcelAnalysisWorkflow:
    """엑셀 분석 워크플로우 (LangGraph)."""

    def __init__(
        self,
        excel_parser,
        claude_client,
        tavily_search,
        hallucination_evaluator,
        search_decision: SearchDecisionInterface,
        logger: LoggerInterface,
        retry_policy: AnalysisRetryPolicy,
        quality_threshold: AnalysisQualityThreshold,
        chart_builder: ChartBuilderInterface | None = None,
        enable_visualization: bool = True,
    ) -> None:
        self._excel_parser = excel_parser
        self._claude = claude_client
        self._search = tavily_search
        self._evaluator = hallucination_evaluator
        self._search_decision = search_decision
        self._logger = logger
        self._retry_policy = retry_policy
        self._quality_threshold = quality_threshold
        # supervisor-chart-builder-node: None이면 chart_router→END 하위호환.
        self._chart_builder = chart_builder
        # excel-chart-routing-dedup: False면 차트 서브그래프(chart_router/chart_builder)를
        # 아예 등록하지 않고 evaluate_hallucination 완료 시 바로 END로 종료한다.
        # Supervisor 재사용 경로에서 시각화는 상위 chart_router가 전담하므로 중복 제거.
        self._enable_visualization = enable_visualization

        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """그래프 구성."""
        workflow = StateGraph(ExcelAnalysisState)

        workflow.add_node("parse_excel", self._parse_excel_node)
        workflow.add_node("analyze_with_claude", self._analyze_node)
        workflow.add_node("web_search", self._web_search_node)
        workflow.add_node("evaluate_hallucination", self._evaluate_node)
        # excel-chart-routing-dedup: 시각화 비활성 시 차트 노드를 등록하지 않는다.
        if self._enable_visualization:
            # analysis-chart-router: 품질 통과(complete) 직후 시각화/텍스트 판단.
            # Excel은 classifier=None → 휴리스틱만 사용(애매구간은 보수적으로 text).
            workflow.add_node(
                "chart_router",
                create_chart_router_node(
                    VisualizationRoutingPolicy(), self._logger, classifier=None
                ),
            )
            # supervisor-chart-builder-node: 빌더 주입 시에만 차트 생성 노드 등록.
            if self._chart_builder is not None:
                workflow.add_node(
                    "chart_builder",
                    create_chart_builder_node(self._chart_builder, self._logger),
                )

        workflow.set_entry_point("parse_excel")
        workflow.add_edge("parse_excel", "analyze_with_claude")

        workflow.add_conditional_edges(
            "analyze_with_claude",
            self._should_search,
            {"search": "web_search", "evaluate": "evaluate_hallucination"},
        )

        workflow.add_edge("web_search", "analyze_with_claude")

        # excel-chart-routing-dedup: complete 목적지는 시각화 ON이면 chart_router, OFF면 END.
        complete_target = "chart_router" if self._enable_visualization else END
        workflow.add_conditional_edges(
            "evaluate_hallucination",
            self._should_retry_or_complete,
            {"retry": "web_search", "complete": complete_target},
        )

        if self._enable_visualization:
            # supervisor-chart-builder-node: 빌더 주입 시 visualize 분기에서 차트 생성.
            if self._chart_builder is not None:
                workflow.add_conditional_edges(
                    "chart_router",
                    route_after_chart_router,
                    {"visualize": "chart_builder", "text": END},
                )
                workflow.add_edge("chart_builder", END)
            else:
                workflow.add_edge("chart_router", END)  # 하위호환

        return workflow.compile()

    async def _parse_excel_node(self, state: ExcelAnalysisState) -> dict:
        """엑셀 파싱 노드."""
        request_id = state["request_id"]
        self._logger.info("Parsing excel file", request_id=request_id)

        file_path = state["excel_data"].get("file_path", "")
        user_id = state["excel_data"].get("user_id", "")

        parsed_data = self._excel_parser.parse(file_path, user_id)

        return {
            "excel_data": parsed_data.to_dict(),
            "current_attempt": 0,
            "max_attempts": self._retry_policy.max_retries,
        }

    async def _analyze_node(self, state: ExcelAnalysisState) -> dict:
        """Claude 분석 노드.

        답변은 자연어 텍스트(analysis_text)로 받고, 웹 검색 필요 여부는
        아직 검색 전(web_search_results 미존재)일 때만 1회 structured 결정으로 판단한다.
        (재시도 경로는 retry_policy가 web_search를 강제하므로 중복 판단 불필요.)
        """
        request_id = state["request_id"]
        attempt = state["current_attempt"] + 1

        self._logger.info(
            f"Analyzing with Claude (attempt {attempt})",
            request_id=request_id,
        )

        web_results = state.get("web_search_results", "")
        # analyze-user-context: state 명시 주입 우선, 없으면 ContextVar 폴백.
        # render_user_context_block(None|anonymous) → "" → 프롬프트 변화 없음.
        user_block = state.get("user_context_block") or render_user_context_block(
            get_current_auth_context()
        )
        prompt = self._build_analysis_prompt(
            state["user_query"],
            state["excel_data"],
            web_results,
            user_block=user_block,
        )

        claude_request = ClaudeRequest(
            model=ClaudeModel.SONNET_4_5,
            messages=[{"role": "user", "content": prompt}],
            request_id=request_id,
            temperature=0.3,
        )

        response = await self._claude.complete(claude_request)
        # 분석 노드는 자연어 텍스트만 유지. 새어 나온 코드블록/JSON을 제거해
        # 하류(evaluate_hallucination / chart_router)가 깨끗한 텍스트만 받게 한다.
        response_text = ANALYSIS_OUTPUT_SANITIZER.strip(response.content)

        needs_search = False
        if not web_results:
            decision = await self._search_decision.decide(
                state["user_query"], response_text, request_id
            )
            needs_search = decision.needs_web_search

        return {
            "analysis_text": response_text,
            "current_attempt": attempt,
            "needs_web_search": needs_search,
        }

    async def _web_search_node(self, state: ExcelAnalysisState) -> dict:
        """웹 검색 노드."""
        request_id = state["request_id"]
        self._logger.info("Performing web search", request_id=request_id)

        query = state["user_query"]
        results = self._search.get_search_context(
            query=query,
            request_id=request_id,
        )

        return {
            "web_search_results": results,
            "needs_web_search": False,
        }

    async def _evaluate_node(self, state: ExcelAnalysisState) -> dict:
        """할루시네이션 평가 노드."""
        request_id = state["request_id"]
        self._logger.info("Evaluating hallucination", request_id=request_id)

        documents = [str(state["excel_data"])]
        web_results = state.get("web_search_results", "")
        if web_results:
            documents.append(web_results)

        eval_result = await self._evaluator.evaluate(
            documents=documents,
            generation=state["analysis_text"],
            request_id=request_id,
        )

        is_hallucinated = eval_result.is_hallucinated
        confidence = 0.0 if is_hallucinated else 1.0
        hallucination = 1.0 if is_hallucinated else 0.0

        attempt_record = {
            "attempt_number": state["current_attempt"],
            "analysis_text": state["analysis_text"],
            "confidence_score": confidence,
            "hallucination_score": hallucination,
            "used_web_search": bool(web_results),
            "timestamp": datetime.utcnow().isoformat(),
        }

        return {
            "confidence_score": confidence,
            "hallucination_score": hallucination,
            "attempts_history": [attempt_record],
        }

    def _should_search(self, state: ExcelAnalysisState) -> str:
        """웹 검색 필요 여부 판단 (structured 결정 결과 기반)."""
        return "search" if state.get("needs_web_search") else "evaluate"

    def _should_retry_or_complete(self, state: ExcelAnalysisState) -> str:
        """재시도/완료 판단."""
        quality_ok = self._quality_threshold.is_acceptable(
            state["confidence_score"],
            state["hallucination_score"],
        )

        if quality_ok:
            return "complete"

        has_hallucination = (
            state["hallucination_score"]
            > self._quality_threshold.max_hallucination_score
        )
        if self._retry_policy.should_retry(
            state["current_attempt"], has_hallucination
        ):
            return "retry"

        return "complete"

    def _build_analysis_prompt(
        self, query: str, excel_data: dict, web_context: str, user_block: str = ""
    ) -> str:
        """분석 프롬프트 생성.

        분석 노드는 자연어 분석 텍스트만 생성한다(차트 생성은 chart_builder 전담).
        출력 형식·범위 제약은 공용 ANALYSIS_OUTPUT_GUIDE로 일원화한다.

        analyze-user-context: user_block(렌더 완료 사용자 컨텍스트)이 있으면 맨 앞에
        prepend한다. render_user_context_block 반환값은 끝에 '---' 구분자를 포함하므로
        추가 개행이 필요 없다. user_block이 ''이면(미인증) 기존 프롬프트와 동일.
        """
        return f"""{user_block}당신은 데이터 분석 결과를 자연어 텍스트로만 작성하는 분석가입니다.
차트·그래프·시각화의 "생성"은 당신의 역할이 아닙니다.

## 사용자 질문
{query}

## 엑셀 데이터
{excel_data}

## 웹 검색 결과
{web_context if web_context else "없음"}

{ANALYSIS_OUTPUT_GUIDE}"""

    async def run(self, state: ExcelAnalysisState) -> ExcelAnalysisState:
        """워크플로우 실행."""
        return await self._graph.ainvoke(state)
