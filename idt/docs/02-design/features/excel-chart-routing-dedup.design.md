# Design: excel-chart-routing-dedup

> Created: 2026-06-09
> Phase: Design
> Plan: `docs/01-plan/features/excel-chart-routing-dedup.plan.md`
> Scope: `idt/` 백엔드 — Supervisor 분석 워커와 내부 ExcelAnalysisWorkflow 간 차트 중복 제거

---

## 0. 확정된 설계 결정 (Plan Open Questions 답변)

| # | Open Question | 결정 |
|---|---------------|------|
| **D1** | Option A vs C | **Option A 확정.** Standalone 경로는 차트 인스턴스 유지 — 사용자가 "최종 답변을 받아 화면에서 chart를 그린다"고 확정. → Standalone Excel 차트는 사용/렌더되므로 제거 불가. |
| **D2** | 인스턴스 분리 방식 | **A-1 확정.** `main.py`에서 워크플로우 인스턴스를 2개(Standalone용 차트 ON / Supervisor 재사용용 차트 OFF) 구성하고 getter를 분리. |
| **D3** | 차트 서브그래프 처리 | **노드 자체 제거.** Supervisor용 인스턴스는 `chart_router`/`chart_builder` 노드를 그래프에 등록하지 않는다. `evaluate_hallucination` 통과(`complete`) 시 **바로 `END`** → 반환된 `analysis_text`를 받은 **상위 Supervisor `chart_router`가 시각화 전담**. |
| **D4** | 초기 state 키 정리 | **그대로 둔다.** `ExcelAnalysisState`의 `viz_decision`/`charts` 키 및 호출부 초기 dict 키는 유지(차트 노드 미등록 시 무해한 미사용 passthrough). |

---

## 1. 설계 개요

### 1-1. 핵심 아이디어
ExcelAnalysisWorkflow에 **`enable_visualization` 플래그**를 도입해 차트 서브그래프(`chart_router`/`chart_builder`)를 **선택적으로 구성**한다.
- **Standalone**(`AnalyzeExcelUseCase`): `enable_visualization=True` + `chart_builder` 주입 → 기존 동작 그대로(`evaluate → chart_router → chart_builder → END`).
- **Supervisor 재사용**(`get_configured_excel_analysis_workflow`): `enable_visualization=False` → 차트 노드 미등록, `evaluate → END`. 차트는 상위 Supervisor 노드가 전담.

### 1-2. 목표 그래프

```
[Standalone — enable_visualization=True, chart_builder 주입]  (변경 없음)
parse_excel → analyze_with_claude → (web_search 루프) → evaluate_hallucination
   └ complete → chart_router → chart_builder → END

[Supervisor 재사용 — enable_visualization=False]  (신규)
parse_excel → analyze_with_claude → (web_search 루프) → evaluate_hallucination
   └ complete → END           ← 차트 노드 없음. analysis_text만 산출

상위 Supervisor 그래프 (변경 없음, 유일한 차트 경로):
supervisor → data_analysis_worker → chart_router → chart_builder → quality_gate
                  └ _run_excel_analysis(차트 OFF 인스턴스 호출 → analysis_text 반환)
```

---

## 2. 변경 상세

### 2-1. `src/application/workflows/excel_analysis_workflow.py`

**(a) 생성자에 `enable_visualization` 추가**

```python
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
    enable_visualization: bool = True,   # ★ 신규: False면 차트 서브그래프 미등록
) -> None:
    ...
    self._chart_builder = chart_builder
    self._enable_visualization = enable_visualization
    self._graph = self._build_graph()
```

**(b) `_build_graph` — 차트 서브그래프 선택적 구성**

핵심 변경: `evaluate_hallucination`의 `complete` 분기 목적지와 chart_router/chart_builder 노드 등록을 `enable_visualization`로 분기.

```python
def _build_graph(self) -> StateGraph:
    workflow = StateGraph(ExcelAnalysisState)
    workflow.add_node("parse_excel", self._parse_excel_node)
    workflow.add_node("analyze_with_claude", self._analyze_node)
    workflow.add_node("web_search", self._web_search_node)
    workflow.add_node("evaluate_hallucination", self._evaluate_node)

    # D3: 시각화 비활성 시 차트 노드를 아예 등록하지 않는다.
    if self._enable_visualization:
        workflow.add_node(
            "chart_router",
            create_chart_router_node(
                VisualizationRoutingPolicy(), self._logger, classifier=None
            ),
        )
        if self._chart_builder is not None:
            workflow.add_node(
                "chart_builder",
                create_chart_builder_node(self._chart_builder, self._logger),
            )

    workflow.set_entry_point("parse_excel")
    workflow.add_edge("parse_excel", "analyze_with_claude")
    workflow.add_conditional_edges(
        "analyze_with_claude", self._should_search,
        {"search": "web_search", "evaluate": "evaluate_hallucination"},
    )
    workflow.add_edge("web_search", "analyze_with_claude")

    # complete 목적지: 시각화 ON이면 chart_router, OFF면 END.
    complete_target = "chart_router" if self._enable_visualization else END
    workflow.add_conditional_edges(
        "evaluate_hallucination", self._should_retry_or_complete,
        {"retry": "web_search", "complete": complete_target},
    )

    if self._enable_visualization:
        if self._chart_builder is not None:
            workflow.add_conditional_edges(
                "chart_router", route_after_chart_router,
                {"visualize": "chart_builder", "text": END},
            )
            workflow.add_edge("chart_builder", END)
        else:
            workflow.add_edge("chart_router", END)  # 기존 하위호환 유지

    return workflow.compile()
```

> **하위호환 보존:** `enable_visualization` 기본값 `True`이므로 기존 호출부(`chart_builder=None → chart_router→END` 포함)는 동작 불변.

### 2-2. `src/api/main.py` — A-1 인스턴스 분리

**(a) 모듈 전역 추가** (`_analyze_excel_use_case` 인근, L468 근처)

```python
_analyze_excel_use_case: Optional[AnalyzeExcelUseCase] = None
_supervisor_excel_workflow: Optional[ExcelAnalysisWorkflow] = None  # ★ 신규: 차트 OFF
```

**(b) `create_analyze_excel_use_case()` — 두 인스턴스 구성**

기존 의존성(parser/claude/tavily/evaluator/search_decision)을 공유해 차트 OFF 인스턴스를 추가 생성하고 전역에 보관한다.

```python
def create_analyze_excel_use_case() -> AnalyzeExcelUseCase:
    global _supervisor_excel_workflow
    ...
    # (기존) Standalone용 — 차트 ON
    workflow = ExcelAnalysisWorkflow(
        excel_parser=excel_parser,
        claude_client=claude_client,
        tavily_search=tavily_search,
        hallucination_evaluator=hallucination_evaluator,
        search_decision=search_decision,
        logger=app_logger,
        retry_policy=retry_policy,
        quality_threshold=quality_threshold,
        chart_builder=excel_chart_builder,
        enable_visualization=True,
    )

    # (신규) Supervisor 재사용용 — 차트 OFF (상위 chart_router가 전담)
    _supervisor_excel_workflow = ExcelAnalysisWorkflow(
        excel_parser=excel_parser,
        claude_client=claude_client,
        tavily_search=tavily_search,
        hallucination_evaluator=hallucination_evaluator,
        search_decision=search_decision,
        logger=app_logger,
        retry_policy=retry_policy,
        quality_threshold=quality_threshold,
        chart_builder=None,
        enable_visualization=False,
    )

    return AnalyzeExcelUseCase(
        workflow=workflow, logger=app_logger,
        retry_policy=retry_policy, quality_threshold=quality_threshold,
    )
```

**(c) `get_configured_excel_analysis_workflow()` — 차트 OFF 인스턴스 반환**

```python
def get_configured_excel_analysis_workflow():
    """analysis-node-agent(Supervisor) 재사용용 — 차트 OFF 인스턴스.

    차트 시각화는 상위 Supervisor chart_router/chart_builder가 전담하므로
    내부 워크플로우는 analysis_text까지만 산출(중복 제거).
    미초기화 시 None → 분석 노드가 문맥 분석으로 graceful fallback.
    """
    return _supervisor_excel_workflow
```

**(d) shutdown 정리** (L2385 인근)

```python
    _analyze_excel_use_case = None
    _supervisor_excel_workflow = None   # ★ 추가
```

### 2-3. `src/application/agent_builder/workflow_compiler.py`

**변경 없음(검증만).** `_run_excel_analysis`는 이미 `analysis_text`만 소비하고 초기 dict의 `viz_decision`/`charts` 키는 D4에 따라 유지. 차트 OFF 인스턴스가 해당 키를 읽지 않으므로 무해.

---

## 3. 레이어 / 아키텍처 적합성

| 항목 | 판정 | 근거 |
|------|------|------|
| `enable_visualization` 플래그 추가 | ✅ Application 흐름 제어 | 그래프 구성 분기일 뿐 비즈니스 규칙 아님 |
| 인스턴스 2개 구성 | ✅ Composition Root(`main.py`) | DI/조립 책임은 main.py가 보유 |
| 의존성 공유 | ✅ | parser/claude/evaluator 등 stateless 재사용 안전 |
| domain→infra 참조 | ✅ 없음 | 워크플로우는 인터페이스(`ChartBuilderInterface`,`SearchDecisionInterface`)에만 의존 |
| 로깅 | ✅ | 기존 노드 로깅 유지, 신규 print 없음 |

---

## 4. 영향 범위 & 회귀

| 파일 | 변경 | 회귀 위험 |
|------|------|-----------|
| `workflows/excel_analysis_workflow.py` | `enable_visualization` 추가 + `_build_graph` 분기 | 기본값 True → 기존 동작 불변 |
| `api/main.py` | 전역 1개 추가 + 인스턴스 2개 구성 + getter 반환 변경 + shutdown 정리 | getter 소비자는 supervisor 컴파일러 1곳(L1818)뿐 → 영향 국소 |
| `use_cases/analyze_excel_use_case.py` | 변경 없음 | Standalone 차트 동작 유지(D1) |

### 4-1. getter 소비자 확인
- `get_configured_excel_analysis_workflow` 사용처: `main.py:1818`(WorkflowCompiler 와이어링) **단 1곳**. → 반환 인스턴스 교체가 Standalone에 영향 없음(검증 완료).

---

## 5. 테스트 설계 (TDD)

### 5-1. 단위 — ExcelAnalysisWorkflow 그래프 구성
`tests/application/workflows/test_excel_analysis_workflow_charts.py` (+ 보강)

| # | 케이스 | 단언 |
|---|--------|------|
| T1 | `enable_visualization=False` | 컴파일된 그래프에 `chart_router`/`chart_builder` 노드 **부재** |
| T2 | `enable_visualization=False` 실행 | `complete` 도달 시 `END` 직결, `chart_builder` mock **호출 0회**, 반환에 `analysis_text` 존재 |
| T3 | `enable_visualization=True` + builder | 기존 `chart_router→chart_builder→END` 동작 유지(회귀) |
| T4 | `enable_visualization=True` + builder=None | 기존 `chart_router→END` 하위호환 유지 |

### 5-2. 통합 — Supervisor 경로 중복 제거
`tests/application/agent_builder/test_analysis_node.py` / `test_run_agent_use_case_stream.py`

| # | 케이스 | 단언 |
|---|--------|------|
| T5 | 엑셀 첨부 → data_analysis_worker | 내부 워크플로우 `chart_builder` **미호출**, 상위 `chart_builder`만 1회 호출되어 charts 캡처 |
| T6 | getter 반환 | `get_configured_excel_analysis_workflow()`가 `enable_visualization=False` 인스턴스 반환 |

### 5-3. 회귀 — Standalone
`tests/application/test_analyze_excel_use_case.py`
- T7: `AnalyzeExcelUseCase.execute` 결과 `AnalysisResult.charts`가 기존대로 채워짐(D1).

### 5-4. 검증 스킬
- `verify-architecture`, `verify-logging`, 전체 pytest **격리 실행**(Windows 이벤트 루프 flakiness 회피).

---

## 6. 구현 순서 (Do 단계)

1. **(Red)** T1·T2 작성 → `enable_visualization` 미구현이라 실패 확인.
2. **(Green)** `ExcelAnalysisWorkflow.__init__` + `_build_graph` 분기 구현 → T1·T2 통과.
3. **(회귀)** T3·T4 통과 확인(기존 동작 불변).
4. **(Green)** `main.py` 전역/인스턴스 2개/ getter/shutdown 수정.
5. **(통합)** T5·T6 작성·통과 — Supervisor 내부 chart_builder 미호출 단언.
6. **(회귀)** T7 — Standalone 차트 유지 확인.
7. **(verify)** verify-architecture / verify-logging / 전체 pytest 격리 실행.

---

## 7. 리스크 / 주의

- **R1.** `main.py` getter가 `_analyze_excel_use_case.workflow`(차트 ON)를 더 이상 반환하지 않음 → 반드시 `_supervisor_excel_workflow`(차트 OFF) 반환으로 교체. 누락 시 중복 잔존.
- **R2.** `_supervisor_excel_workflow`는 `create_analyze_excel_use_case()` 호출 시 함께 생성됨 → init 순서상 `_default_llm_model` 로드 후 호출(L2379)이라 안전. (차트 OFF 인스턴스는 chart_builder 불필요하므로 LLM 모델 미로드여도 무관.)
- **R3.** 테스트 flakiness — 격리 실행으로 검증.

---

## 8. 다음 단계

```
/pdca do excel-chart-routing-dedup
```
