# Plan: excel-chart-routing-dedup

> Created: 2026-06-09
> Phase: Plan
> Scope: `idt/` 백엔드 — Supervisor 분석 워커(data_analysis_worker)와 내부 ExcelAnalysisWorkflow 간 차트 라우팅/생성 중복 제거

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | Supervisor 그래프의 분석 워커(`data_analysis_worker`)가 첨부 엑셀을 처리할 때 내부 `ExcelAnalysisWorkflow`를 호출하는데, 이 내부 워크플로우가 자체 `chart_router → chart_builder`를 또 태운다. 그런데 호출부 `_run_excel_analysis`는 결과에서 `analysis_text`만 읽고 내부가 만든 `charts`는 **폐기**한다. 이후 Supervisor 그래프의 **상단** `chart_router → chart_builder`가 동일 텍스트로 차트를 **다시 생성**한다. → 차트 생성 LLM 호출이 **2중 실행 + 한쪽은 버려짐**. |
| **Solution** | 차트 라우팅/생성을 **상단 chart_router 노드로 일원화**한다는 기존 결정에 맞춰, Supervisor가 재사용하는 ExcelAnalysisWorkflow 인스턴스에서는 차트 서브그래프(`chart_router`/`chart_builder`)를 비활성화한다. 내부 워크플로우는 `analysis_text` 산출까지만 책임지고, 시각화 판단·생성은 Supervisor 상단 노드가 전담한다. Standalone `AnalyzeExcelUseCase` 경로는 회귀 없이 유지(또는 후속 일원화). |
| **Function UX Effect** | 엑셀 첨부 분석 시 사용자 응답(텍스트+차트)은 동일하되, 중복 차트 빌드 LLM 호출 1회가 제거되어 응답 지연·토큰 비용↓. 차트 결정 경로가 General Chat·Supervisor와 동일하게 수렴해 예측 가능성↑. |
| **Core Value** | "차트는 상단 노드에서 일원화"라는 아키텍처 결정과의 정합성 회복. 죽은(폐기되는) 차트 생성 경로 제거로 비용·혼란 동시 절감. |

---

## 1. 배경 / 문제 정의

### 1-1. 현재 두 개의 차트 파이프라인이 동시에 존재

**① 내부 ExcelAnalysisWorkflow** (`src/application/workflows/excel_analysis_workflow.py`)

```
parse_excel → analyze_with_claude → (web_search 루프) → evaluate_hallucination
  └ complete → chart_router → chart_builder → END     ← 내부 차트 생성 (chart_builder 주입 시)
```
- `chart_builder`가 주입되면(`main.py:699`, `excel_chart_builder`) `chart_router → chart_builder → END`로 차트를 생성해 `state["charts"]`에 채운다.

**② Supervisor 그래프** (`src/application/agent_builder/workflow_compiler.py::compile`)

```
supervisor → data_analysis_worker(analysis 노드) → chart_router → chart_builder → quality_gate
                     └ _create_analysis_node → _run_excel_analysis(내부 워크플로우 ① 호출)
```
- analysis 카테고리 워커는 직후 **상단** `chart_router`(LLM classifier) → `chart_builder`(LLM) → `quality_gate`로 흐른다 (`workflow_compiler.py:351,355~363`).
- 이 상단 `chart_builder`가 만든 charts가 실제로 캡처·사용된다 (`run_agent_use_case.py:580` 인근).

### 1-2. 중복의 핵심 (코드 근거)

1. **내부 차트 결과가 폐기됨**
   - `workflow_compiler.py:602 _run_excel_analysis`는 내부 워크플로우 실행 후 **`final.get("analysis_text")`만 반환**(L630). 내부가 생성한 `state["charts"]`는 **버려진다**.
2. **상단에서 동일 작업을 재실행**
   - 버려진 `analysis_text`를 받은 Supervisor가 상단 `chart_router → chart_builder`로 **같은 차트 판단·생성을 다시** 수행.
3. **결과적으로**
   - 엑셀 첨부 1건 분석 시 `chart_builder`(with_structured_output LLM 호출)가 **2회** 실행되고, 그중 **내부 1회분은 100% 폐기**. 불필요한 지연 + 토큰 비용 + 로그 노이즈.
   - 내부 `chart_router`는 `classifier=None` 휴리스틱이라 LLM 호출은 없으나(`excel_analysis_workflow.py:110`), 결과(`viz_decision`)는 역시 폐기됨.

### 1-3. 두 소비자(consumer) 구분

| 소비 경로 | 진입점 | 내부 charts 사용 여부 |
|-----------|--------|----------------------|
| **Standalone** | `analysis_router` → `AnalyzeExcelUseCase.execute` | **사용함** — `AnalysisResult.charts = state["charts"]` (`analyze_excel_use_case.py:142`) |
| **Supervisor** | `data_analysis_worker` → `_run_excel_analysis` | **폐기** — `analysis_text`만 사용, 상단 노드가 차트 재생성 |

> ⚠️ 두 경로가 **동일한 단일 워크플로우 인스턴스**(`_analyze_excel_use_case.workflow`, `main.py:548`)를 공유한다. 따라서 내부 차트 노드를 무조건 제거하면 Standalone 경로가 깨진다 → 경로별 분기 필요.
>
> 📌 참고(CC 메모리): "차트 렌더링은 현재 프론트/백엔드 모두 General Chat 경로에만 연결, Excel/Supervisor는 후속." → Standalone Excel 차트가 실제로 프론트에 렌더되는지 Design에서 확인 필요(미사용이면 Option C 일원화 가능).

---

## 2. 목표 / 비목표

### 2-1. 목표
- **G1.** Supervisor(data_analysis_worker) 경로에서 내부 ExcelAnalysisWorkflow의 차트 서브그래프(`chart_router`/`chart_builder`) 실행을 **제거**한다(중복 + 폐기되는 `chart_builder` LLM 호출 제거).
- **G2.** 차트 판단·생성을 **상단 `chart_router` 노드로 일원화**(기존 결정 준수).
- **G3.** Standalone `AnalyzeExcelUseCase` 경로는 **회귀 없이 동작**(또는 Design에서 확인 후 동일 일원화).
- **G4.** 관련 테스트 갱신 + 아키텍처/로깅 검증.

### 2-2. 비목표
- **N1.** 상단 chart_router/chart_builder 자체 로직 변경(이번엔 중복 제거만, 상단 노드는 그대로 사용).
- **N2.** Standalone Excel 차트의 프론트 렌더링 연결(별도 feature, 메모리 기준 후속).
- **N3.** ChartBuilder/VisualizationRoutingPolicy 등 차트 인프라 리팩토링.

---

## 3. 해결 방안 (옵션 비교)

| 옵션 | 내용 | 장점 | 단점 |
|------|------|------|------|
| **A (권장)** | Supervisor 재사용 전용으로 **차트 비활성 워크플로우 인스턴스**를 별도 구성. `get_configured_excel_analysis_workflow()`가 `chart_builder=None`(+ 차트 서브그래프 skip) 인스턴스를 반환. Standalone은 기존 차트 인스턴스 유지. | Standalone 무회귀(리스크 최소). 폐기되던 `chart_builder` LLM 호출 완전 제거. DI/조립 레벨 변경으로 국소적. | 워크플로우 인스턴스 2개 구성(경량). 차트 서브그래프 optional화 소폭 필요. |
| **B** | `ExcelAnalysisState`에 `skip_visualization` 플래그 추가. `_run_excel_analysis`가 True로 세팅 → 내부 라우터가 `complete → END`로 차트 우회. | 단일 인스턴스 유지. | 공유 워크플로우에 호출자 관심사(플래그)가 침투, 그래프 조건 분기 증가. |
| **C** | ExcelAnalysisWorkflow에서 차트 서브그래프를 **완전 제거**하고 Standalone도 상위에서 차트 처리(또는 미사용 확인 후 드롭). | 아키텍처 완전 일원화. | Standalone 차트 동작 변경 → 프론트 사용 여부 확인 전엔 리스크. 범위 확대. |

**권장: Option A.** "상단 일원화" 결정을 Supervisor 경로에 즉시 적용하면서 Standalone 회귀 리스크 0. 추후 Standalone Excel 차트가 미사용으로 확정되면 Option C로 수렴.

---

## 4. 목표 아키텍처 (Option A)

```
[Supervisor 경로 — 차트 비활성 인스턴스]
parse_excel → analyze_with_claude → (web_search 루프) → evaluate_hallucination
   └ complete → END            (analysis_text만 산출, 내부 차트 노드 없음)
         ↑ _run_excel_analysis 가 이 인스턴스 사용
supervisor → data_analysis_worker → chart_router(상단) → chart_builder(상단) → quality_gate
                                     └ 차트 판단·생성 일원화 (유일)

[Standalone 경로 — 기존 차트 인스턴스 유지]
analysis_router → AnalyzeExcelUseCase.execute → (차트 포함 워크플로우) → AnalysisResult.charts
```

### 4-1. 구현 방향
- `ExcelAnalysisWorkflow._build_graph`: 차트 서브그래프를 **선택적**으로 구성하도록 정리.
  - 현재는 `chart_router`가 항상 추가되고 `chart_builder`만 조건부. → 차트 서브그래프 전체를 끌 수 있게 한다(예: `chart_builder is None`이면 `evaluate_hallucination 완료 → END` 직결, `chart_router`도 생략).
  - ⚠️ 단, 현 `chart_builder=None` 동작(`chart_router → END`)에 의존하는 Standalone 케이스가 있는지 Design에서 확인(현재 main.py는 `_default_llm_model` 로드 시 builder 주입 → 통상 builder 존재).
- `main.py`: Supervisor 재사용용 getter가 **차트 비활성 인스턴스**를 반환하도록 분리.
  - 안 A-1: `create_analyze_excel_use_case()`에서 차트 인스턴스(Standalone용)와 차트 비활성 인스턴스(Supervisor용) 2개 구성, getter 분리.
  - 안 A-2: `_run_excel_analysis` 호출 시점에 차트 비활성 변형을 주입(getter 시그니처/조립만 조정).

---

## 5. 영향 범위 (Affected Files)

| 파일 | 변경 |
|------|------|
| `src/application/workflows/excel_analysis_workflow.py` | 차트 서브그래프 선택적 구성(차트 비활성 시 `chart_router`/`chart_builder` 미등록, `evaluate → END` 직결) |
| `src/api/main.py` | `create_analyze_excel_use_case()` / `get_configured_excel_analysis_workflow()` — Supervisor 재사용용 차트 비활성 인스턴스 분리 구성·반환 |
| `src/application/agent_builder/workflow_compiler.py` | (검증 위주) `_run_excel_analysis`가 차트 비활성 인스턴스를 사용하는지 확인. 초기 state의 `viz_decision`/`charts` 키는 무해하므로 유지 가능 |
| **재사용 주의** `AnalyzeExcelUseCase` | Standalone 차트 동작 무회귀 확인(인스턴스 분리로 영향 차단) |

### 5-1. 테스트 영향
- `tests/application/workflows/test_excel_analysis_workflow_charts.py` — 차트 비활성 인스턴스에서 `chart_router`/`chart_builder` 미실행 + `evaluate → END` 검증 추가.
- `tests/application/test_excel_analysis_workflow.py` — 차트 서브그래프 optional 구성 회귀.
- `tests/application/agent_builder/test_analysis_node.py` / `test_workflow_compiler.py` — Supervisor 경로가 차트 비활성 인스턴스를 받고, 상단 chart_router/chart_builder만 차트를 생성하는지 회귀.
- (필요 시) `test_run_agent_use_case_stream.py` — 상단 chart_builder charts 캡처 유지 확인.

### 5-2. Cross-Project (API 계약)
- API 응답 스키마 변경 **없음**(Standalone `AnalysisResponse` 동작 유지). `/api-contract-sync` 불필요 추정 — Design에서 최종 확인.

---

## 6. 작업 분해 (TDD: Red → Green → Refactor)

1. **(Red)** ExcelAnalysisWorkflow 차트 비활성 모드 테스트 작성 — builder 미주입 시 그래프에 `chart_builder` 노드 부재 + 완료 시 `END` 직결, `charts` 빈 리스트.
2. **(Green)** `_build_graph` 차트 서브그래프 선택적 구성 구현.
3. **(Red→Green)** `main.py` Supervisor 재사용용 차트 비활성 인스턴스 분리 + getter 반환 변경.
4. **(회귀)** Supervisor 경로 통합 테스트 — 상단 chart_router/chart_builder만 차트 생성, 내부 chart_builder 미호출 확인(Mock 호출 횟수 단언).
5. **(회귀)** Standalone 경로 — `AnalyzeExcelUseCase.execute` 차트 동작 유지 확인.
6. **(Refactor/verify)** `verify-architecture`, `verify-logging`, 전체 pytest(격리 실행: Windows 이벤트 루프 flakiness 회피).

---

## 7. 리스크 / 주의사항

- **R1. 단일 공유 인스턴스 분기 누락** — Standalone과 Supervisor가 같은 인스턴스를 쓰므로, 인스턴스 분리가 불완전하면 Standalone 차트가 사라지거나 Supervisor 중복이 남는다. → 인스턴스 분리·getter 라우팅을 명확히(테스트로 호출 횟수 단언).
- **R2. `chart_router` 항상 등록 가정** — 현재 그래프는 `chart_router`를 무조건 추가. optional화 시 기존 `chart_builder=None`(→`chart_router→END`) 동작에 의존하는 테스트/경로 회귀 점검 필요.
- **R3. 초기 state 키** — `_run_excel_analysis`/`AnalyzeExcelUseCase` 초기 dict의 `viz_decision`/`charts` 키는 차트 노드 미등록 시에도 무해(미사용). 제거는 선택.
- **R4. 테스트 flakiness** — pytest 교차 실행 시 Windows 이벤트 루프 teardown 산발 실패 → 격리 실행으로 검증.
- **R5. 메모리 정합** — "차트는 General Chat 경로에만 프론트 연결" 메모리와 충돌 없음(상단 Supervisor charts는 별도 캡처 경로). Standalone 프론트 미연결 여부는 Option C 판단 시에만 영향.

---

## 8. Design 단계 Open Questions

1. **Option A vs C 확정** — Standalone Excel 차트(`AnalysisResult.charts`)가 실제 프론트에서 렌더/소비되는가? 미사용이면 C(완전 일원화)로 단순화 가능.
2. **인스턴스 분리 방식** — `main.py`에서 2개 인스턴스(A-1) vs getter 변형 주입(A-2) 중 택.
3. **차트 서브그래프 optional 시그니처** — 기존 `chart_builder=None`(→`chart_router→END`) 의미를 "차트 완전 비활성(→END 직결)"으로 바꿀지, 별도 플래그를 둘지.
4. **초기 state 키 정리** — `viz_decision`/`charts` 키 제거 여부.

---

## 9. 다음 단계

```
/pdca design excel-chart-routing-dedup
```
