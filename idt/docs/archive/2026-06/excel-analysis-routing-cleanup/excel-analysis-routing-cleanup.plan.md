# Plan: excel-analysis-routing-cleanup

> Created: 2026-06-06
> Phase: Plan
> Scope: `idt/` 백엔드 — Excel 분석 LangGraph 워크플로우 리팩토링

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | Excel 분석 워크플로우가 Claude에게 ```python``` 차트 코드를 생성시켜 샌드박스에서 실행하지만, 샌드박스는 `math/statistics`만 허용(matplotlib 금지)이라 차트가 실제로 만들어지지 않고, 결과는 `ChartConfig`가 아니어서 프론트 렌더 불가. 게다가 `execute_code → END`로 분리된 `chart_router`를 건너뛴다. 제어 신호도 `[SEARCH]`/```python``` 태그를 regex로 파싱해 코드베이스 표준(`with_structured_output`)과 어긋난다. |
| **Solution** | (1) 코드 생성/실행 노드·상태·의존성을 **완전 제거**, (2) 모든 완료 경로를 `chart_router`로 **일원화**(라우팅 구조만 정리, 실제 차트 빌드는 후속), (3) 웹 검색 필요 판단을 freeform 태그 → **structured 결정**으로 전환(분석 답변 자체는 텍스트 유지). |
| **Function UX Effect** | 사용자 응답 동작은 동일하되, 죽은 차트-코드 경로 제거로 예측 가능성↑. 시각화 판단이 General Chat과 동일 경로로 수렴해 후속 차트 렌더 연결 준비 완료. |
| **Core Value** | 분리해 둔 차트 라우팅 아키텍처와의 정합성 회복 + 라우팅 견고성(태그 파싱 → 구조화 결정). 죽은 코드/오해 소지 제거. |

---

## 1. 배경 / 문제 정의

### 1-1. 현재 구조 (`src/application/workflows/excel_analysis_workflow.py`)

```
parse_excel → analyze_with_claude
  ├ [SEARCH] 태그 발견? → web_search → analyze (재분석)
  └ → evaluate_hallucination
        ├ 품질 OK & needs_code_execution → execute_code → END   ← chart_router 우회
        ├ 품질 OK & no code            → chart_router → END
        └ 품질 미달 → retry(web_search) | complete
```

### 1-2. 확인된 문제점 (코드 근거)

1. **차트-코드 경로가 동작 불가 + 분리된 라우팅과 충돌**
   - `_build_analysis_prompt`는 "그래프/차트가 필요하면 Python 코드를 ```python``` 블록에" 라고 지시.
   - 그러나 `CodeExecutorPolicy.ALLOWED_MODULES = {math, statistics, decimal, fractions, datetime, json, re, collections, itertools, functools}` → **matplotlib/pandas 금지**. 차트 코드는 실행 불가.
   - 실행돼도 결과는 stdout 문자열(`code_output`)일 뿐 프론트가 렌더할 `ChartConfig`가 아님.
   - `execute_code → END`라 코드 경로는 `chart_router`(시각화 판단)를 **아예 우회**.

2. **freeform 텍스트 + regex 파싱이 코드베이스 표준과 불일치**
   - `_should_search`: 답변 텍스트에서 `[SEARCH]`/"웹에서 확인"을 grep.
   - `_detect_code_in_response`/`_extract_code`: ```python``` 블록을 regex 추출.
   - 반면 이 코드베이스는 ChartBuilder·hallucination·query rewrite·research router 등 **전부 `with_structured_output`**로 표준화됨.

3. **정착된 시각화 파이프라인이 이미 존재**(General Chat 사용 중, `GeneralChatUseCase._maybe_build_charts`)
   ```
   VisualizationRoutingPolicy → ChartBuilderInterface(with_structured_output(ChartDraftList))
     → ChartStylePolicy(색상·options) → ChartConfig(= 프론트 ChartPayload)
   ```
   Excel은 이 자산을 재사용하지 않고 별도 코드-실행 메커니즘을 둠.

---

## 2. 목표 / 비목표

### 2-1. 목표 (이번 작업 범위)
- **G1.** 코드 생성/실행 노드·상태 필드·DI 의존성을 워크플로우에서 완전 제거.
- **G2.** 모든 완료 경로가 `chart_router`로 수렴하도록 그래프 일원화 (구조 정리).
- **G3.** 웹 검색 필요 판단을 태그 파싱 → structured 결정으로 전환. **분석 답변(`analysis_text`)은 텍스트 유지.**
- **G4.** 연쇄 영향(엔티티/라우터/DI/재사용 노드) 정리 + 테스트 갱신.

### 2-2. 비목표 (후속 task)
- **N1.** Excel `chart_router → ChartBuilder` 실제 차트 빌드 연결 (이번엔 `viz_decision` 기록까지만). → 별도 feature.
- **N2.** 프론트 Excel 차트 렌더링 연결. → N1 이후.
- **N3.** `SandboxExecutor`/`code_executor_tool` 자체 삭제 (다른 곳에서 쓰일 수 있으므로 워크플로우 의존만 제거; 전면 삭제 여부는 Design에서 사용처 확인 후 결정).

---

## 3. 결정 사항 (사용자 확정)

| # | 질문 | 결정 |
|---|------|------|
| D1 | 샌드박스 코드 실행 처리 | **완전 제거** (차트는 structured 파이프라인, 계산은 LLM이 직접) |
| D2 | 이번 차트 연결 범위 | **라우팅 구조만 정리** (실제 차트 빌드는 후속) |
| D3 | analyze 노드 structured 깊이 | **답변은 텍스트, 제어 결정만 structured** |

---

## 4. 목표 아키텍처

### 4-1. 리팩토링 후 그래프

```
parse_excel → analyze_with_claude        (analysis_text = 자연어 텍스트만 반환)
  → search_decision (structured)          needs_web_search? (분리된 결정)
       ├ true  → web_search → analyze_with_claude
       └ false → evaluate_hallucination
  → evaluate_hallucination
  → _should_retry_or_complete             (retry | complete) — 'execute' 분기 삭제
       ├ retry    → web_search
       └ complete → chart_router
  → chart_router (viz_decision만 기록)
  → END
```

### 4-2. D3 구현 방향 (웹 검색 결정)
- 분석 답변은 기존처럼 일반 텍스트 completion (`analysis_text`).
- 검색 필요 여부는 **별도 structured 결정**으로 산출:
  - 도메인: `WebSearchDecision(needs_web_search: bool, reason: str = "")` (예시 스키마, 명칭은 Design에서 확정).
  - 포트: `SearchDecisionInterface` (application/domain) — `chart_router`의 classifier 패턴과 동일하게 application은 인터페이스에만 의존.
  - 인프라 어댑터: `with_structured_output(WebSearchDecision)` 사용, 실패 시 보수적으로 `needs_web_search=False` graceful degrade.
  - `_should_search` 조건부 엣지는 `state["needs_web_search"]`를 읽도록 변경(regex 제거).
- ⚠️ 트레이드오프: 결정용 LLM 호출 +1회. 완화책(첫 시도에만 호출 / 설정 플래그)은 Design에서 확정.

### 4-3. 제거 대상
- 노드: `_execute_code_node`, 엣지 `execute_code → END`, 조건부 `execute` 분기.
- 메서드: `_detect_code_in_response`, `_extract_code`, `_should_search`(태그 버전).
- 상태 필드: `needs_code_execution`, `code_to_execute`, `code_output`.
- 프롬프트: `_build_analysis_prompt`의 "Python 코드 작성" 지시(3항) + `[SEARCH]` 태그 지시(2항, structured로 대체).
- 생성자 인자: `code_executor`.

---

## 5. 영향 범위 (Affected Files)

| 파일 | 변경 |
|------|------|
| `src/application/workflows/excel_analysis_workflow.py` | 핵심 리팩토링 (노드/상태/엣지/프롬프트) |
| `src/application/use_cases/analyze_excel_use_case.py` | `_build_result`의 `code_executed`/`executed_code`/`code_output` 제거, 초기 state에서 코드 필드 제거 |
| `src/domain/entities/analysis_result.py` | `AnalysisResult.executed_code`, `code_output` 필드 제거 |
| `src/api/routes/analysis_router.py` | `AnalysisResponse.executed_code`, `code_output` 제거 + docstring 문구 정리 |
| `src/api/main.py` | `create_analyze_excel_use_case()`에서 `SandboxExecutor`/`code_executor=` 제거, 신규 SearchDecision 어댑터 DI 추가 |
| (신규) `src/domain/.../search_decision` 스키마·포트 | D3용 structured 결정 계약 |
| (신규) `src/infrastructure/.../search_decision_adapter.py` | `with_structured_output` 어댑터 |
| **재사용 주의** `get_configured_excel_analysis_workflow()` (analysis-node-agent) | `_analyze_node` 반환 shape 변경 영향 — 사용처(supervisor/agent_builder) 회귀 확인 필요 |

### 5-1. 테스트 영향
- `tests/application/test_excel_analysis_workflow.py`:
  - 삭제: `test_analyze_node_detects_code`, `test_execute_code_node`, `test_should_retry_or_execute_quality_ok_with_code`, `test_full_flow_with_code_execution`, `test_should_search_*`(태그 버전).
  - 신규: search_decision structured 분기 테스트, `complete → chart_router → END` 통합 테스트, 코드 필드 부재 검증.
  - 갱신: 모든 `ExcelAnalysisState` 픽스처에서 코드 필드 제거, `_create_workflow`에서 `code_executor` 제거.
- `tests/application/test_analyze_excel_use_case.py`: `_build_result` 코드 관련 단언 제거.
- `tests/application/agent_builder/test_analysis_node.py`: analyze 노드 재사용 회귀 확인.

### 5-2. Cross-Project (API 계약)
- `AnalysisResponse`에서 필드 2개 제거 → **API 계약 변경**. 프론트가 `/api/v1/analysis/excel` 응답의 `executed_code`/`code_output`을 참조하는지 확인 후 `/api-contract-sync` 적용 (미사용으로 추정되나 검증 필요).

---

## 6. 작업 분해 (TDD: Red → Green → Refactor)

1. **계약 정의 (Red)** — `WebSearchDecision` 스키마 + `SearchDecisionInterface` 포트 테스트 작성.
2. **인프라 어댑터 (Red→Green)** — `with_structured_output` 어댑터 + 실패 graceful degrade 테스트.
3. **워크플로우 리팩토링 (Red→Green)** — 코드 노드/상태/프롬프트 제거, search_decision 노드 추가, 그래프 재배선. 기존 테스트 갱신.
4. **연쇄 정리** — `AnalysisResult`/`analyze_excel_use_case`/`analysis_router` 코드 필드 제거.
5. **DI 배선** — `main.py`에서 `code_executor` 제거 + SearchDecision 어댑터 주입.
6. **재사용 회귀** — analysis-node-agent 경로(supervisor) 테스트 통과 확인.
7. **Refactor / verify** — `verify-architecture`, `verify-logging`, 전체 pytest(격리 실행: Windows 이벤트 루프 flakiness 회피).

---

## 7. 리스크 / 주의사항

- **R1. analysis-node-agent 재사용** — `_analyze_node` 반환에서 `needs_code_execution`/`code_to_execute` 제거 시 supervisor 분석 노드가 해당 키를 참조하면 깨짐. → Design에서 사용처 grep 후 처리.
- **R2. API 계약 파괴** — 응답 필드 제거. 프론트 참조 여부 확인 필수(`/api-contract-sync`).
- **R3. LLM 호출 +1** — search_decision 분리 호출 비용. 첫 시도 한정/설정화로 완화 (Design 확정).
- **R4. `SandboxExecutor` 잔존** — 워크플로우에서만 의존 제거. 전면 삭제는 다른 사용처 확인 후(N3).
- **R5. 테스트 flakiness** — pytest 교차 실행 시 Windows 이벤트 루프 teardown 산발 실패 → 격리 실행으로 검증.

---

## 8. Design 단계 Open Questions

1. search_decision를 **별도 노드**로 둘지, `_analyze_node` 내부 2차 호출로 합칠지.
2. `WebSearchDecision` 호출을 **첫 시도에만** 할지 매 시도 할지.
3. `SandboxExecutor`/`code_executor_tool`/`code_executor_policy` 전면 삭제 여부 (사용처 조사 결과에 따라).
4. analysis-node-agent(supervisor) 경로의 코드 필드 의존 여부 확정.

---

## 9. 다음 단계

```
/pdca design excel-analysis-routing-cleanup
```
