# ANALYSIS-CHART-ROUTER: 분석 노드 직후 시각화 vs 텍스트 라우팅 + 프론트 차트 스펙 생성

> 상태: Plan
> 연관 Task: CHART-ROUTE-001
> 작성일: 2026-06-05
> 우선순위: High

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 분석 노드가 답변 텍스트를 생성한 뒤, 그 결과를 **그래프/차트로 보여줘야 할지 텍스트로만 답할지**를 판단하는 단계가 없다. 현재는 `_detect_code_in_response()`가 응답에 ```` ```python ```` 블록이 있는지만 보고 `execute_code`로 넘기지만, `SandboxExecutor`는 matplotlib·file I/O가 차단돼 실제 차트를 못 그린다. 즉 "~에 대한 그래프 그려줘" 같은 명시 요청도, 수치 데이터를 보고 자동 시각화해야 할 상황도 일관되게 처리되지 못한다. |
| **Solution** | 분석 노드 직후에 **공용 시각화 라우터(`chart_router`)** 를 둔다. 하이브리드 판단(키워드/데이터 휴리스틱 → 애매하면 LLM)으로 `visualize` / `text` 2분기. `visualize`면 **`chart_builder`** 가 LLM structured output으로 **프론트 렌더링용 ChartSpec(JSON)** 을 생성해 상태/메시지에 실어 반환한다. ExcelAnalysisWorkflow와 agent_builder Supervisor **양쪽에서 재사용**하되, Supervisor는 analysis 워커를 타고 나온 경우에만 라우터로 진입시킨다. |
| **Function UX Effect** | 사용자가 "매출 추이 그래프 그려줘"처럼 명시 요청하면 차트 스펙이 내려오고, 수치 위주 분석 결과는 자동으로 차트 후보가 된다. 텍스트로 충분한 질문은 그대로 텍스트 답변. 프론트는 ChartSpec JSON을 받아 ECharts/Recharts 등으로 렌더링. |
| **Core Value** | RAG/에이전트 분석 결과의 **표현 형식을 의도에 맞게 자동 선택** → "데이터를 봤는데 표/숫자만 나온다"는 답답함 제거. 백엔드는 라이브러리 비종속 스펙만 책임지고, 렌더링은 프론트가 담당해 관심사 분리. |

---

## 1. 문제 정의 (Problem Statement)

분석 노드(아래 두 군데)는 모두 **분석 텍스트(AIMessage / analysis_text)** 만 생성하고 끝난다.

```
[사용자] "2023~2025 매출 추이 그래프로 보여줘"
   → 분석 노드: "2023년 100억, 2024년 130억, 2025년 160억으로 증가 추세입니다." (텍스트)
   → 끝. 차트는 안 나옴.
```

말씀하신 두 가지 상황을 구분해 처리할 판단 지점이 없다:

1. **명시 요청** — "~에 대한 그래프/차트 그려줘" (사용자가 직접 시각화를 요구)
2. **데이터 기반 자동 판단** — 사용자가 시각화를 명시하지 않아도, 분석 결과가 시계열/카테고리별 수치라 차트가 더 적절한 경우

현재 동작:
- `ExcelAnalysisWorkflow`: `_detect_code_in_response()`가 ```` ```python ```` 유무만 검사 → `execute_code`. 그러나 `SandboxExecutor`는 `math/statistics/json/re/...` 만 허용하고 **file I/O·matplotlib·plotly 차단** → 실제 차트 이미지 생성 불가. 사실상 죽은 경로.
- `agent_builder Supervisor`: `_create_analysis_node()`가 분석 텍스트 AIMessage만 반환 → `quality_gate` → `supervisor` 복귀. 시각화 판단 전무.

---

## 2. 현재 구조 분석 (Current State)

### 2-1. ExcelAnalysisWorkflow (`src/application/workflows/excel_analysis_workflow.py`)

```
parse_excel → analyze_with_claude
  → [_should_search] → web_search(루프) / evaluate_hallucination
evaluate_hallucination
  → [_should_retry_or_execute] → web_search(retry) / execute_code / END
execute_code → END
```

- 시각화 판단 = `_should_retry_or_execute()` 안에서 `needs_code_execution`(= ```` ```python ```` 검출) 분기 (line 245)
- `execute_code` 노드(line 210)는 `SandboxExecutor`로 실행 → 차트 렌더 불가

### 2-2. agent_builder Supervisor (`src/application/agent_builder/workflow_compiler.py`)

```
supervisor → [route_to_worker] → {각 worker} / answer_agent / END
{worker} → quality_gate → [route_after_quality] → supervisor / {worker}
```

- 분석 워커는 `_create_analysis_node()` (line 462)로 생성, `function_node_ids`에 등록
- 모든 worker는 `graph.add_edge(worker_id, "quality_gate")` (line 286)로 quality_gate에 직결
- `last_worker_id`로 직전 실행 워커 식별 가능 → **analysis 워커 직후만 라우터로 보내는 분기 가능**
- analysis 워커 식별: `_resolve_category(worker_def) == "analysis"` (컴파일 시점에 알 수 있음 → 해당 worker_id를 set으로 보관)

### 2-3. 핵심 제약

- `SandboxExecutor`는 차트 라이브러리 미허용 → **백엔드 이미지 생성 경로는 채택하지 않음** (답변 ③: 프론트 렌더링용 스펙 JSON)
- DDD 레이어 규칙: 판단 **규칙**은 domain Policy, **워크플로우 배선**은 application, **LLM 호출**은 infrastructure 경유

---

## 3. 수정 범위 (Scope)

| # | 위치 | 내용 | 레이어 | 우선순위 |
|---|------|------|--------|----------|
| 1 | `src/domain/visualization/schemas.py` (신규) | `ChartSpec`, `ChartType`(enum), `ChartSeries` pydantic 모델 = 프론트 계약 | domain | High |
| 2 | `src/domain/visualization/policies.py` (신규) | `VisualizationRoutingPolicy` — 키워드/데이터 휴리스틱 1차 판단 | domain | High |
| 3 | `src/application/visualization/chart_router.py` (신규) | `chart_router` 노드 팩토리 (하이브리드: 휴리스틱 → 애매하면 LLM 분류) | application | High |
| 4 | `src/application/visualization/chart_builder.py` (신규) | `chart_builder` 노드 팩토리 (LLM structured output → ChartSpec) | application | High |
| 5 | `excel_analysis_workflow.py` | 그래프에 `chart_router`/`chart_builder` 노드·엣지 삽입 | application | High |
| 6 | `workflow_compiler.py` | analysis 워커 직후 라우터 배선 + 상태 필드 소비 | application | High |
| 7 | `supervisor_state.py` | `viz_decision`, `chart_spec` 상태 필드 추가 | application | High |
| 8 | `tests/...` | 라우터/빌더/배선 단위·통합 테스트 (TDD) | - | High |
| 9 | (별도) `idt_front/src/types/` | `ChartSpec` 타입 동기화 — `/api-contract-sync` | front | Medium |

**범위 외 (별도 처리)**:
- 백엔드 이미지(PNG) 생성 및 `SandboxExecutor` 확장
- 차트 타입 세분화 라우팅(막대/선/파이 자동 선택은 `chart_builder` LLM에 위임, 별도 라우팅 분기는 만들지 않음 — 답변 ②: 2분기 유지)
- 프론트 실제 차트 렌더링 컴포넌트 구현

---

## 4. 설계 (Solution Design)

### 4-1. 라우팅 흐름 (2분기, 공용)

```
                ┌─ visualize → chart_builder → (다음 단계)
analysis 결과 → chart_router ┤
                └─ text ───────────────────→ (다음 단계: 그대로 종료/복귀)
```

- 답변 ②에 따라 **분기는 정확히 2개** (`visualize` / `text`)
- 차트 종류(막대/선/파이)는 분기 대상이 아니라 `chart_builder` 내부 LLM이 ChartSpec.chart_type으로 결정

### 4-2. ChartSpec — 프론트 렌더링용 스펙 (답변 ③)

라이브러리 비종속 **중립 스키마**를 채택한다 (ECharts option을 그대로 박지 않음 → 프론트 자유도 확보).

```python
# src/domain/visualization/schemas.py
from enum import Enum
from pydantic import BaseModel, Field

class ChartType(str, Enum):
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"
    AREA = "area"

class ChartSeries(BaseModel):
    name: str = Field(description="시리즈 이름 (예: '매출')")
    data: list[float] = Field(description="x_labels와 같은 길이의 값 배열")

class ChartSpec(BaseModel):
    chart_type: ChartType
    title: str = Field(default="", description="차트 제목")
    x_labels: list[str] = Field(description="x축 카테고리/라벨 (예: ['2023','2024','2025'])")
    series: list[ChartSeries] = Field(description="1개 이상의 데이터 시리즈")
    x_axis_name: str = Field(default="")
    y_axis_name: str = Field(default="")
    note: str = Field(default="", description="데이터 출처/주의 (선택)")
```

> ⚠️ **확정 필요(프론트 합의)**: idt_front가 쓰는 차트 라이브러리(ECharts / Recharts / Chart.js)에 따라 필드 매핑이 달라질 수 있다. Design 단계에서 `idt_front`의 차트 컴포넌트 유무를 확인하고 스키마를 최종 고정한다. 현재는 위 중립 스키마를 기본 제안으로 둔다.

### 4-3. VisualizationRoutingPolicy — 하이브리드 1차 판단 (답변 ④)

```python
# src/domain/visualization/policies.py
class VisualizationRoutingPolicy:
    """시각화 라우팅 규칙. 키워드 + 데이터 형태 휴리스틱."""

    VISUALIZE_KEYWORDS = ("그래프", "차트", "시각화", "그려", "plot", "chart", "graph", "추이", "비교")

    def explicit_request(self, question: str) -> bool:
        q = question.lower()
        return any(kw.lower() in q for kw in self.VISUALIZE_KEYWORDS)

    def data_suggests_chart(self, analysis_text: str) -> bool:
        """수치+카테고리 신호 휴리스틱 (간단 규칙, 과하지 않게)."""
        # 숫자 토큰 N개 이상 + 표/나열 신호 등. 임계값은 config화.
        ...

    def decide(self, question: str, analysis_text: str) -> str | None:
        """'visualize' | 'text' | None(애매 → LLM 위임)."""
        if self.explicit_request(question):
            return "visualize"
        if self.data_suggests_chart(analysis_text):
            return None  # 데이터는 차트 후보지만 확신 부족 → LLM 확인
        return "text"
```

판단 우선순위(하이브리드):
1. **명시 키워드 있으면 즉시 `visualize`** (LLM 호출 없이, 비용↓)
2. **데이터 신호는 있으나 명시 없음 → `None` 반환 → 라우터가 LLM 분류 호출** (애매구간만 LLM)
3. **둘 다 아니면 `text`** (LLM 호출 없이)

### 4-4. chart_router 노드 (application)

```python
# src/application/visualization/chart_router.py
def create_chart_router_node(llm, policy: VisualizationRoutingPolicy, logger):
    async def chart_router(state) -> dict:
        question = _latest_user_question(state)         # 기존 헬퍼 재사용
        analysis_text = _latest_analysis_text(state)
        decision = policy.decide(question, analysis_text)
        if decision is None:                            # 애매구간만 LLM
            decision = await _classify_with_llm(llm, question, analysis_text)
        logger.info("chart_router decided", decision=decision)
        return {"viz_decision": decision}
    return chart_router

def route_after_chart_router(state) -> str:
    return "visualize" if state.get("viz_decision") == "visualize" else "text"
```

- LLM 분류는 `with_structured_output`(Literal["visualize","text"]) 사용 → 파싱 안정성
- 실패/예외 시 `text`로 graceful fallback (시각화 실패가 본 답변을 막지 않음)

### 4-5. chart_builder 노드 (application)

```python
# src/application/visualization/chart_builder.py
def create_chart_builder_node(llm, logger):
    async def chart_builder(state) -> dict:
        analysis_text = _latest_analysis_text(state)
        try:
            spec = await llm.with_structured_output(ChartSpec).ainvoke(
                _build_spec_prompt(analysis_text)
            )
            chart_spec = spec.model_dump()
        except Exception as e:
            logger.error("chart_builder failed, fallback to text", exception=e)
            return {"chart_spec": None}   # 텍스트만으로 진행
        return {"chart_spec": chart_spec}
    return chart_builder
```

- 분석 텍스트(+필요 시 excel_data/검색결과)에서 수치를 LLM이 추출해 ChartSpec으로 구조화
- 결과는 `state["chart_spec"]`에 저장 → 응답 직렬화 시 프론트로 전달

### 4-6. ExcelAnalysisWorkflow 배선 변경

```python
# 기존 evaluate → execute_code/END 경로를 라우터 경유로 교체
workflow.add_node("chart_router", chart_router)
workflow.add_node("chart_builder", chart_builder)

# evaluate 통과(complete) 시 execute_code 대신 chart_router로
workflow.add_conditional_edges(
    "evaluate_hallucination",
    self._should_retry_or_route,                 # 기존 _should_retry_or_execute 개명/확장
    {"retry": "web_search", "route": "chart_router", "complete": END},
)
workflow.add_conditional_edges(
    "chart_router", route_after_chart_router,
    {"visualize": "chart_builder", "text": END},
)
workflow.add_edge("chart_builder", END)
```

- `ExcelAnalysisState`에 `viz_decision: str`, `chart_spec: dict | None` 추가
- 기존 `execute_code`/`_detect_code_in_response` 경로는 제거 또는 비활성 (범위 외 SandboxExecutor와 분리)

### 4-7. Supervisor 배선 변경 (analysis 직후만 라우터)

답변 ①: "supervisor에서 analysis 타고 나왔으면 라우터쪽으로".

```python
# workflow_compiler.compile() 내부
analysis_worker_ids: set[str] = set()   # category=="analysis"인 worker_id 수집(루프에서)

graph.add_node("chart_router", _wrap_step("chart_router", NodeType.OTHER, chart_router_fn))
graph.add_node("chart_builder", _wrap_step("chart_builder", NodeType.OTHER, chart_builder_fn))

for worker_id in worker_map:
    if worker_id in analysis_worker_ids:
        # analysis 워커는 quality_gate 대신 chart_router로
        graph.add_edge(worker_id, "chart_router")
    else:
        graph.add_edge(worker_id, "quality_gate")

graph.add_conditional_edges(
    "chart_router", route_after_chart_router,
    {"visualize": "chart_builder", "text": "quality_gate"},
)
graph.add_edge("chart_builder", "quality_gate")   # 차트 생성 후에도 품질검증/복귀 흐름 유지
```

- 차트 분기든 텍스트 분기든 **결국 quality_gate → supervisor 복귀** 흐름은 보존 (기존 멀티워커 오케스트레이션 안 깨짐)
- `chart_spec`은 `SupervisorState`에 누적되어 최종 응답 직렬화 시 함께 반환

### 4-8. 상태 필드 추가 (`supervisor_state.py`)

```python
class SupervisorState(TypedDict):
    ...
    attachments: list[dict]
    # analysis-chart-router
    viz_decision: str            # "visualize" | "text" | ""
    chart_spec: dict | None      # 프론트 렌더링용 ChartSpec(JSON) 또는 None
```

`build_initial_state()`에 기본값(`viz_decision=""`, `chart_spec=None`) 추가.

---

## 5. 테스트 계획 (TDD)

### 5-1. VisualizationRoutingPolicy 단위 테스트 (domain)
- `explicit_request("매출 그래프 그려줘")` → True
- `explicit_request("매출 알려줘")` → False
- `decide(명시 키워드, _)` → "visualize"
- `decide(키워드 없음, 비수치 텍스트)` → "text"
- `decide(키워드 없음, 수치 다수 텍스트)` → None (LLM 위임)

### 5-2. chart_router 노드 테스트 (application, FakeLLM)
- 명시 요청 → LLM 호출 없이 `viz_decision == "visualize"`
- 애매구간 → FakeLLM이 "visualize" 반환 → `viz_decision == "visualize"`
- LLM 예외 → `viz_decision == "text"` (graceful)

### 5-3. chart_builder 노드 테스트 (application, FakeLLM)
- 정상: FakeLLM이 ChartSpec 반환 → `state["chart_spec"]`이 dict이고 `chart_type/x_labels/series` 키 존재
- 예외: `chart_spec is None`, 흐름 비중단

### 5-4. ExcelAnalysisWorkflow 통합 테스트
- "그래프 그려줘" 질의 → 최종 state에 `chart_spec` 존재
- 일반 텍스트 질의 → `chart_spec is None`, 기존 텍스트 답변 보존

### 5-5. WorkflowCompiler 배선 테스트
- analysis 워커 노드의 다음 엣지가 `chart_router`인지 (그래프 구조 검증)
- 비-analysis 워커는 여전히 `quality_gate` 직결
- `visualize` 분기: chart_router → chart_builder → quality_gate 경로 확인

> 모든 신규 모듈은 **테스트 먼저 작성(RED) → 구현(GREEN)** (CLAUDE.md TDD 필수).

---

## 6. 영향 범위 / 리스크

| 항목 | 영향 | 비고 |
|------|------|------|
| `ExcelAnalysisState` / `SupervisorState` 필드 추가 | 기존 키 불변, 신규 키만 추가 | reducer/직렬화 호환 |
| Supervisor 그래프 배선 | analysis 워커 후속 엣지 변경 | 비-analysis 워커 경로 보존 |
| 토큰 비용 | 애매구간 + visualize 시 LLM 추가 호출 | 명시/명백 케이스는 휴리스틱으로 LLM 회피 |
| 응답 스키마 | `chart_spec` 필드 추가 → **API 계약 변경** | `/api-contract-sync` 필수, 프론트 타입 동기화 |
| 기존 `execute_code` 경로 | 제거/비활성 | 실제로 차트 못 그리던 죽은 경로라 회귀 위험 낮음 |
| 관측성(track_step) | 신규 노드 2개 step으로 노출 | NodeType.OTHER로 래핑 |

---

## 7. 구현 순서

1. `src/domain/visualization/schemas.py` (ChartSpec) + 테스트(5-1 일부)
2. `src/domain/visualization/policies.py` (VisualizationRoutingPolicy) + 테스트 5-1
3. `src/application/visualization/chart_router.py` + 테스트 5-2
4. `src/application/visualization/chart_builder.py` + 테스트 5-3
5. `supervisor_state.py` 필드 추가 + `build_initial_state` 기본값
6. `excel_analysis_workflow.py` 배선 + 테스트 5-4
7. `workflow_compiler.py` analysis 워커 라우터 배선 + 테스트 5-5
8. 응답 스키마에 `chart_spec` 노출 + `/api-contract-sync`로 `idt_front` 타입 동기화
9. Gap 분석(`/pdca analyze`) → Report

---

## 8. 미해결 / 후속 이슈 (Design에서 확정)

- **ChartSpec 최종 스키마**: `idt_front` 차트 라이브러리 확인 후 필드 고정 (4-2 ⚠️)
- **data_suggests_chart 휴리스틱 임계값**: 숫자 토큰 수/표 신호 기준을 config화 (`src/config.py` 또는 analysis_config)
- **다중 시리즈/축 데이터 추출 정확도**: chart_builder LLM이 분석 텍스트만으로 수치를 정확히 못 뽑는 경우 → excel_data 원본을 컨텍스트로 추가 전달할지 Design에서 결정
- **차트 + 텍스트 동시 응답**: visualize 시에도 텍스트 답변은 함께 내려가는지(권장) 응답 직렬화 규칙 확정
