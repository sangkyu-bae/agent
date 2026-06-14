# Design: excel-analysis-routing-cleanup

> Created: 2026-06-06
> Phase: Design
> Plan: `docs/01-plan/features/excel-analysis-routing-cleanup.plan.md`
> Scope: `idt/` 백엔드 — Excel 분석 LangGraph 워크플로우 리팩토링

---

## 1. Overview

Excel 분석 워크플로우에서 **죽은 코드-실행 차트 경로를 제거**하고, **웹 검색 필요 판단을 freeform 태그 파싱 → structured 결정으로 전환**한다. 분석 답변(`analysis_text`)은 자연어 텍스트로 유지하고, 모든 완료 경로를 `chart_router`로 일원화한다(실제 차트 빌드는 후속 feature N1).

본 설계는 Plan의 4개 Open Question에 대한 코드 조사 결과를 반영해 확정한다.

### 1-1. Open Question 결정 (코드 근거)

| # | 질문 | 결정 | 근거 |
|---|------|------|------|
| Q1 | search_decision 별도 노드 vs analyze 내부 호출 | **analyze 노드 내부 2차 structured 호출** | 그래프 토폴로지 최소 변경, thin DDD(노드 수 억제). 조건부 엣지 `_should_search`는 `state["needs_web_search"]` bool만 읽음 |
| Q2 | 검색 결정 매 시도 vs 첫 시도 | **첫 검색 전(`web_search_results` 미존재)만 호출** | retry 경로는 `AnalysisRetryPolicy.require_web_search_on_retry=True`로 이미 web_search 강제 → 결정은 첫 패스에만 의미. 호출 1회로 제한 + 검색 루프 방지 |
| Q3 | SandboxExecutor 전면 삭제 | **삭제 금지, 워크플로우 의존만 제거** | `code_executor_tool`(`python_code_executor`)이 `tool_registry` + `db/migration/V008__seed_internal_tools.sql`로 커스텀 에이전트 내부 도구로 정식 등록됨 → 별도 정상 사용처 |
| Q4 | supervisor(analysis-node-agent) 코드 필드 의존 | **소비 의존 없음. 입력 dict만 수정** | `run_agent_use_case._run_excel_analysis`는 출력에서 `analysis_text`만 읽음(L582). 단 initial dict에 코드 필드 3개를 써넣으므로(L569-571) 그 부분만 제거 |

---

## 2. Architecture

### 2-1. 리팩토링 후 그래프

```
parse_excel
  → analyze_with_claude              (analysis_text[텍스트] + needs_web_search[structured] 산출)
  → _should_search (conditional)
       ├ "search"   → web_search → analyze_with_claude
       └ "evaluate" → evaluate_hallucination
  → evaluate_hallucination
  → _should_retry_or_complete (conditional)   ← 'execute' 분기 삭제
       ├ "retry"    → web_search
       └ "complete" → chart_router
  → chart_router (viz_decision 기록)
  → END
```

### 2-2. 레이어 매핑 (Thin DDD)

| 레이어 | 구성요소 |
|--------|---------|
| **domain** | `WebSearchDecision`(VO), `SearchDecisionInterface`(포트), 기존 `AnalysisRetryPolicy`/`AnalysisQualityThreshold` |
| **application** | `ExcelAnalysisWorkflow`(그래프·노드), `AnalyzeExcelUseCase`, `chart_router` 노드 |
| **infrastructure** | `LLMSearchDecisionAdapter`(`with_structured_output`), DI 배선(`main.py`) |
| **interfaces** | `analysis_router`(응답 스키마) |

---

## 3. Detailed Design

### 3-1. 신규 도메인 계약

**`src/domain/search_decision/schemas.py`**
```python
from pydantic import BaseModel, Field


class WebSearchDecision(BaseModel):
    """분석 답변에 외부(웹) 정보 보강이 필요한지에 대한 구조화 판단."""

    needs_web_search: bool = Field(
        description="분석이 엑셀 데이터만으로 불충분해 최신/외부 정보가 필요하면 True"
    )
    reason: str = Field(default="", description="판단 근거(짧게)")
```

**`src/domain/search_decision/interfaces.py`**
```python
from abc import ABC, abstractmethod

from src.domain.search_decision.schemas import WebSearchDecision


class SearchDecisionInterface(ABC):
    """웹 검색 필요 판단 포트. application은 이 인터페이스에만 의존."""

    @abstractmethod
    async def decide(
        self, question: str, analysis_text: str, request_id: str
    ) -> WebSearchDecision:
        """질문 + 분석 텍스트로 웹 검색 필요 여부 판단. 실패 시 보수적으로 False."""
        raise NotImplementedError
```

### 3-2. 신규 인프라 어댑터

**`src/infrastructure/search_decision/adapter.py`** — `HallucinationEvaluatorAdapter` 패턴 미러링.
```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.search_decision.interfaces import SearchDecisionInterface
from src.domain.search_decision.schemas import WebSearchDecision

_SYSTEM = (
    "당신은 데이터 분석 답변이 엑셀 데이터만으로 충분한지 판단하는 라우터입니다.\n"
    "최신 시세/뉴스/외부 통계 등 엑셀에 없는 정보가 답변에 필요하면 needs_web_search=True.\n"
    "엑셀 데이터만으로 답할 수 있으면 False. 보수적으로 판단하세요."
)
_HUMAN = "[질문]\n{question}\n\n[현재 분석 답변]\n{analysis_text}"


class LLMSearchDecisionAdapter(SearchDecisionInterface):
    def __init__(
        self,
        logger: LoggerInterface,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ) -> None:
        self._logger = logger
        llm = ChatOpenAI(model=model_name, temperature=temperature)
        prompt = ChatPromptTemplate.from_messages(
            [("system", _SYSTEM), ("human", _HUMAN)]
        )
        self._chain = prompt | llm.with_structured_output(WebSearchDecision)

    async def decide(
        self, question: str, analysis_text: str, request_id: str
    ) -> WebSearchDecision:
        try:
            return await self._chain.ainvoke(
                {"question": question, "analysis_text": analysis_text}
            )
        except Exception as e:
            self._logger.error(
                "search decision failed, fallback=False",
                exception=e, request_id=request_id,
            )
            return WebSearchDecision(needs_web_search=False)
```

### 3-3. `ExcelAnalysisState` 변경

```python
class ExcelAnalysisState(TypedDict):
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
    viz_decision: str
    # 제거: needs_code_execution, code_to_execute, code_output
```

### 3-4. `ExcelAnalysisWorkflow` 변경

**생성자**: `code_executor` 인자 제거, `search_decision: SearchDecisionInterface` 추가.

```python
def __init__(
    self,
    excel_parser,
    claude_client,
    tavily_search,
    hallucination_evaluator,
    search_decision: SearchDecisionInterface,   # 신규
    logger: LoggerInterface,
    retry_policy: AnalysisRetryPolicy,
    quality_threshold: AnalysisQualityThreshold,
) -> None:
    ...
    self._search_decision = search_decision
    # 제거: self._executor
```

**`_build_graph`** (변경점):
```python
workflow.add_node("parse_excel", self._parse_excel_node)
workflow.add_node("analyze_with_claude", self._analyze_node)
workflow.add_node("web_search", self._web_search_node)
workflow.add_node("evaluate_hallucination", self._evaluate_node)
workflow.add_node("chart_router", create_chart_router_node(
    VisualizationRoutingPolicy(), self._logger, classifier=None))
# 제거: workflow.add_node("execute_code", ...)

workflow.set_entry_point("parse_excel")
workflow.add_edge("parse_excel", "analyze_with_claude")
workflow.add_conditional_edges(
    "analyze_with_claude", self._should_search,
    {"search": "web_search", "evaluate": "evaluate_hallucination"})
workflow.add_edge("web_search", "analyze_with_claude")
workflow.add_conditional_edges(
    "evaluate_hallucination", self._should_retry_or_complete,
    {"retry": "web_search", "complete": "chart_router"})  # 'execute' 제거
workflow.add_edge("chart_router", END)
# 제거: workflow.add_edge("execute_code", END)
```

**`_analyze_node`** (Q1+Q2 반영 — 텍스트 답변 + structured 검색 결정):
```python
async def _analyze_node(self, state: ExcelAnalysisState) -> dict:
    request_id = state["request_id"]
    attempt = state["current_attempt"] + 1
    self._logger.info(f"Analyzing with Claude (attempt {attempt})",
                      request_id=request_id)

    prompt = self._build_analysis_prompt(
        state["user_query"], state["excel_data"],
        state.get("web_search_results", ""))
    claude_request = ClaudeRequest(
        model=ClaudeModel.SONNET_4_5,
        messages=[{"role": "user", "content": prompt}],
        request_id=request_id, temperature=0.3)
    response = await self._claude.complete(claude_request)
    analysis_text = response.content

    # Q2: 아직 웹 검색 전일 때만 1회 구조화 판단 → 루프 방지·비용 제한
    needs_search = False
    if not state.get("web_search_results"):
        decision = await self._search_decision.decide(
            state["user_query"], analysis_text, request_id)
        needs_search = decision.needs_web_search

    return {
        "analysis_text": analysis_text,
        "current_attempt": attempt,
        "needs_web_search": needs_search,
    }
    # 제거: needs_code_execution, code_to_execute 산출
```

**`_should_search`** (regex → bool):
```python
def _should_search(self, state: ExcelAnalysisState) -> str:
    return "search" if state.get("needs_web_search") else "evaluate"
```

**`_should_retry_or_complete`** (구 `_should_retry_or_execute`, execute 분기 제거):
```python
def _should_retry_or_complete(self, state: ExcelAnalysisState) -> str:
    quality_ok = self._quality_threshold.is_acceptable(
        state["confidence_score"], state["hallucination_score"])
    if quality_ok:
        return "complete"
    has_hallucination = (
        state["hallucination_score"]
        > self._quality_threshold.max_hallucination_score)
    if self._retry_policy.should_retry(
        state["current_attempt"], has_hallucination):
        return "retry"
    return "complete"
```

**`_build_analysis_prompt`** (지침 2·3 제거):
```python
## 지침
1. 데이터를 기반으로 정확하게 분석하세요
2. 추측하지 말고 데이터에 근거하세요
# 제거: [SEARCH] 태그 지시(검색은 외부 structured 결정), Python 코드 작성 지시
```

**제거 메서드**: `_execute_code_node`, `_detect_code_in_response`, `_extract_code`.

### 3-5. 연쇄 변경

**`AnalyzeExcelUseCase`** (`analyze_excel_use_case.py`)
- `initial_state`에서 `needs_code_execution`/`code_to_execute`/`code_output` 키 제거.
- `_build_result`: `code_executed`/`executed_code`/`code_output` 로직 제거 → `AnalysisResult(...)`에서 해당 인자 제거.

**`AnalysisResult`** (`src/domain/entities/analysis_result.py`)
- 필드 `executed_code: Optional[str]`, `code_output: Optional[Dict]` 제거.

**`analysis_router.py`**
- `AnalysisResponse`에서 `executed_code`, `code_output` 필드 제거.
- 응답 생성부에서 해당 인자 제거, docstring "코드 실행" 문구 정리.

**`main.py` `create_analyze_excel_use_case`**
```python
# 제거
from src.infrastructure.tools.sandbox_executor import SandboxExecutor
code_executor = SandboxExecutor(logger=app_logger)
# 추가
from src.infrastructure.search_decision.adapter import LLMSearchDecisionAdapter
search_decision = LLMSearchDecisionAdapter(logger=app_logger)
workflow = ExcelAnalysisWorkflow(
    excel_parser=excel_parser,
    claude_client=claude_client,
    tavily_search=tavily_search,
    hallucination_evaluator=hallucination_evaluator,
    search_decision=search_decision,   # code_executor= 대체
    logger=app_logger,
    retry_policy=retry_policy,
    quality_threshold=quality_threshold,
)
```

**`run_agent_use_case._run_excel_analysis`** (supervisor 재사용)
- `initial` dict에서 `needs_code_execution`/`code_to_execute`/`code_output` 키 제거(L569-571). 출력 소비(`analysis_text`)는 변경 없음.

**선택 정리(scope 내 권장)**: `analysis_policy.py`의 `AnalysisStatus` Literal에서 `"code_executing"` 제거 — 미사용. 영향 없음.

### 3-6. 비변경(명시)
- `SandboxExecutor`, `code_executor_tool.py`, `code_executor_policy.py`, `V008__seed_internal_tools.sql`, 관련 테스트는 **그대로 유지**(커스텀 에이전트 `python_code_executor` 도구 사용처).
- `chart_router`는 `viz_decision` 기록까지만(실제 ChartBuilder 연결은 후속 N1).

---

## 4. Data Flow (대표 시나리오)

1. **엑셀만으로 충분 + 환각 없음**: parse → analyze(needs_search=False) → evaluate(OK) → complete → chart_router → END
2. **외부 정보 필요**: parse → analyze(needs_search=True) → web_search → analyze(web_search_results 존재 → 결정 skip, False) → evaluate → complete → chart_router → END
3. **환각으로 retry**: ... evaluate(환각) → retry → web_search → analyze → evaluate(OK) → complete → chart_router → END

검색 결정 LLM 호출은 시나리오당 **최대 1회**(첫 analyze).

---

## 5. Test Design (TDD)

### 5-1. 신규
- `tests/domain/search_decision/test_schemas.py`: `WebSearchDecision` 기본값/검증.
- `tests/infrastructure/search_decision/test_adapter.py`: 정상 파싱 / 예외 시 `needs_web_search=False` graceful.
- 워크플로우:
  - `test_analyze_node_sets_needs_web_search`(decision=True → state 반영).
  - `test_analyze_node_skips_decision_after_search`(web_search_results 존재 시 decide 미호출).
  - `test_should_search_bool`(True→"search", False→"evaluate").
  - `test_full_flow_complete_routes_to_chart_router`(complete → chart_router → END, `viz_decision` 존재).

### 5-2. 삭제
- `test_analyze_node_detects_code`, `test_execute_code_node`,
- `test_should_retry_or_execute_quality_ok_with_code`,
- `test_full_flow_with_code_execution`,
- `test_should_search_with_tag`, `test_should_search_with_korean`(태그 버전).

### 5-3. 갱신
- 모든 `ExcelAnalysisState` 픽스처에서 코드 필드 3개 제거.
- `_create_workflow` 헬퍼: `code_executor` 제거 → `search_decision=Mock()`(또는 AsyncMock decide) 추가.
- `test_should_retry_or_execute_*` → `test_should_retry_or_complete_*`로 개명/조정.
- `test_analyze_excel_use_case.py`: 코드 관련 단언 제거.
- `tests/application/agent_builder/test_analysis_node.py`: initial dict 코드 필드 제거 회귀 확인.

### 5-4. 검증 스킬
- `verify-architecture`(domain→infra 역참조 없음 확인), `verify-logging`(어댑터 예외 로깅), `verify-tdd`.
- 전체 pytest는 **격리 실행**(Windows 이벤트 루프 teardown flakiness 회피).

---

## 6. API 계약 영향

`AnalysisResponse`에서 `executed_code`/`code_output` 제거 → `/api/v1/analysis/excel` 응답 스키마 변경.
- **조치**: 프론트(`idt_front`)가 해당 필드 참조하는지 확인 후, 참조 시 `/api-contract-sync` 적용. 미참조면 백엔드 단독 변경.
- (추정) Excel 분석 응답 차트/코드 필드는 프론트 미연동 상태(메모리: Excel 차트 렌더링 후속) → 영향 낮음, 단 확인 필수.

---

## 7. 구현 순서 (Do 단계 체크리스트)

1. `domain/search_decision/{schemas,interfaces}.py` + 테스트 (Red→Green)
2. `infrastructure/search_decision/adapter.py` + 테스트 (Red→Green)
3. `ExcelAnalysisWorkflow` 리팩토링 + 테스트 갱신/추가
4. `AnalysisResult` / `analyze_excel_use_case` / `analysis_router` 코드 필드 제거
5. `main.py` DI 교체 (`SandboxExecutor`→`LLMSearchDecisionAdapter`)
6. `run_agent_use_case._run_excel_analysis` initial dict 정리
7. supervisor 재사용 회귀 테스트 + 전체 pytest(격리)
8. `verify-architecture` / `verify-logging`

---

## 8. Risks

| ID | 리스크 | 완화 |
|----|--------|------|
| R1 | supervisor initial dict의 코드 필드가 LangGraph 입력 검증에서 키 불일치 유발 | `_run_excel_analysis`에서 키 제거(필수 작업으로 명시) |
| R2 | API 응답 필드 제거로 프론트 파손 | `/api-contract-sync` 선확인 |
| R3 | 검색 결정 LLM +1 호출 비용 | 첫 analyze 1회로 제한(Q2) |
| R4 | 검색 결정 오판(과소 검색) | 보수적 프롬프트 + retry 경로가 web_search 강제로 보완 |

---

## 9. 다음 단계

```
/pdca do excel-analysis-routing-cleanup
```
