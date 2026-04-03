"""Excel Analysis Workflow using LangGraph.

엑셀 파일을 파싱하여 Claude AI로 분석하고,
할루시네이션 검증 후 최대 N회 재시도하는 Self-Corrective 워크플로우.
"""

import re
from datetime import datetime
from typing import Annotated, Sequence, TypedDict

import operator
from langgraph.graph import END, StateGraph

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.policies.analysis_policy import (
    AnalysisQualityThreshold,
    AnalysisRetryPolicy,
)
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

    needs_code_execution: bool
    code_to_execute: str
    code_output: dict

    attempts_history: Annotated[Sequence[dict], operator.add]

    is_complete: bool
    final_status: str
    error_message: str


class ExcelAnalysisWorkflow:
    """엑셀 분석 워크플로우 (LangGraph)."""

    def __init__(
        self,
        excel_parser,
        claude_client,
        tavily_search,
        hallucination_evaluator,
        code_executor,
        logger: LoggerInterface,
        retry_policy: AnalysisRetryPolicy,
        quality_threshold: AnalysisQualityThreshold,
    ) -> None:
        self._excel_parser = excel_parser
        self._claude = claude_client
        self._search = tavily_search
        self._evaluator = hallucination_evaluator
        self._executor = code_executor
        self._logger = logger
        self._retry_policy = retry_policy
        self._quality_threshold = quality_threshold

        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """그래프 구성."""
        workflow = StateGraph(ExcelAnalysisState)

        workflow.add_node("parse_excel", self._parse_excel_node)
        workflow.add_node("analyze_with_claude", self._analyze_node)
        workflow.add_node("web_search", self._web_search_node)
        workflow.add_node("evaluate_hallucination", self._evaluate_node)
        workflow.add_node("execute_code", self._execute_code_node)

        workflow.set_entry_point("parse_excel")
        workflow.add_edge("parse_excel", "analyze_with_claude")

        workflow.add_conditional_edges(
            "analyze_with_claude",
            self._should_search,
            {"search": "web_search", "evaluate": "evaluate_hallucination"},
        )

        workflow.add_edge("web_search", "analyze_with_claude")

        workflow.add_conditional_edges(
            "evaluate_hallucination",
            self._should_retry_or_execute,
            {"retry": "web_search", "execute": "execute_code", "complete": END},
        )

        workflow.add_edge("execute_code", END)

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
        """Claude 분석 노드."""
        request_id = state["request_id"]
        attempt = state["current_attempt"] + 1

        self._logger.info(
            f"Analyzing with Claude (attempt {attempt})",
            request_id=request_id,
        )

        prompt = self._build_analysis_prompt(
            state["user_query"],
            state["excel_data"],
            state.get("web_search_results", ""),
        )

        claude_request = ClaudeRequest(
            model=ClaudeModel.SONNET_4_5,
            messages=[{"role": "user", "content": prompt}],
            request_id=request_id,
            temperature=0.3,
        )

        response = await self._claude.complete(claude_request)
        response_text = response.content

        needs_code = self._detect_code_in_response(response_text)
        code = self._extract_code(response_text) if needs_code else ""

        return {
            "analysis_text": response_text,
            "current_attempt": attempt,
            "needs_code_execution": needs_code,
            "code_to_execute": code,
            "needs_web_search": False,
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

    async def _execute_code_node(self, state: ExcelAnalysisState) -> dict:
        """코드 실행 노드."""
        request_id = state["request_id"]
        self._logger.info("Executing code", request_id=request_id)

        result = self._executor.execute(
            state["code_to_execute"],
            request_id,
        )

        return {
            "code_output": {
                "status": result.status.value,
                "output": result.output,
                "error_message": result.error_message,
            },
            "is_complete": True,
            "final_status": "completed",
        }

    def _should_search(self, state: ExcelAnalysisState) -> str:
        """웹 검색 필요 여부 판단."""
        text = state.get("analysis_text", "")
        if "[SEARCH]" in text or "웹에서 확인" in text:
            return "search"
        return "evaluate"

    def _should_retry_or_execute(self, state: ExcelAnalysisState) -> str:
        """재시도/코드실행/완료 판단."""
        quality_ok = self._quality_threshold.is_acceptable(
            state["confidence_score"],
            state["hallucination_score"],
        )

        if quality_ok:
            if state["needs_code_execution"]:
                return "execute"
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
        self, query: str, excel_data: dict, web_context: str
    ) -> str:
        """분석 프롬프트 생성."""
        return f"""당신은 데이터 분석 전문가입니다.

## 사용자 질문
{query}

## 엑셀 데이터
{excel_data}

## 웹 검색 결과 (있는 경우)
{web_context if web_context else "없음"}

## 지침
1. 데이터를 기반으로 정확하게 분석하세요
2. 추가 정보가 필요하면 [SEARCH] 태그를 포함하세요
3. 그래프/차트가 필요하면 Python 코드를 ```python ``` 블록에 작성하세요
4. 추측하지 말고 데이터에 근거하세요"""

    def _detect_code_in_response(self, response: str) -> bool:
        """응답에 코드 포함 여부."""
        return "```python" in response

    def _extract_code(self, response: str) -> str:
        """코드 블록 추출."""
        match = re.search(r"```python\n(.*?)\n```", response, re.DOTALL)
        return match.group(1) if match else ""

    async def run(self, state: ExcelAnalysisState) -> ExcelAnalysisState:
        """워크플로우 실행."""
        return await self._graph.ainvoke(state)
