# Completion Report: excel-analysis-routing-cleanup

> Report Date: 2026-06-06 | Phase: Report (PDCA 완료)
> Scope: `idt/` 백엔드 — Excel 분석 LangGraph 워크플로우 리팩토링

---

## 1. Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| Feature | excel-analysis-routing-cleanup |
| 기간 | 2026-06-06 (Plan→Design→Do→Check→Report, 단일 세션) |
| Match Rate | **100%** |
| 레벨 | Dynamic (백엔드 단독) |

### 1.2 Results Summary

| 지표 | 값 |
|------|-----|
| Match Rate | 100% (검증 포인트 7/7 PASS) |
| 신규 파일 | 5 (도메인 2 + 인프라 1 + 테스트 2) |
| 수정 파일 | 8 (코드 8 + 테스트 4) |
| 테스트 | 64건 PASS (신규 5 + workflow 14 + usecase/router 11 + result + supervisor 34) |
| Gap | 누락 0 / 추가 0 / 변경 0 |
| 아키텍처 위반 | 0건 (신규 코드 기준) |

### 1.3 Value Delivered

| 관점 | 전달된 가치 (실제 결과) |
|------|------------------------|
| **Problem** | Excel 워크플로우가 matplotlib 금지 샌드박스에 차트 코드를 생성·실행시키는 **동작 불가한 죽은 경로**를 갖고 있었고, `execute_code → END`로 분리된 `chart_router`를 우회했으며, `[SEARCH]`/```python``` 태그를 regex로 파싱해 코드베이스 표준과 어긋났다. |
| **Solution** | 코드 생성/실행 노드·상태·DI를 **완전 제거**하고, 모든 완료 경로를 `chart_router`로 일원화했으며, 웹검색 판단을 `SearchDecisionInterface`/`WebSearchDecision` **structured 결정**으로 전환했다(답변 텍스트는 유지). |
| **Function UX Effect** | 사용자 응답 동작은 동일하게 유지하면서, 죽은 경로 제거로 동작 예측 가능성↑. 검색 라우팅이 태그 누락에 취약하지 않게 견고화됨(structured). 검색 결정 LLM 호출은 요청당 **최대 1회**로 비용 제한. |
| **Core Value** | 분리해 둔 차트 라우팅 아키텍처(General Chat과 동일 경로)와의 **정합성 회복**. analysis-chart-router에서 deferred했던 죽은 코드 정리를 마무리. 후속 N1(chart_router → ChartBuilder 실제 연결)의 토대 마련. |

---

## 2. PDCA Cycle Summary

```
[Plan] ✅ → [Design] ✅ → [Do] ✅ → [Check] ✅ (100%) → [Report] ✅
```

| Phase | 산출물 | 핵심 |
|-------|--------|------|
| Plan | `docs/01-plan/features/excel-analysis-routing-cleanup.plan.md` | 죽은 경로/표준 위반 진단, 3개 결정(코드제거/라우팅정리/structured), 4개 Open Q |
| Design | `docs/02-design/features/excel-analysis-routing-cleanup.design.md` | Open Q 4건 코드 근거로 확정, 신규 계약·그래프·연쇄변경 명세 |
| Do | 구현 + 테스트 | 8단계 TDD 체크리스트 수행 |
| Check | `docs/03-analysis/excel-analysis-routing-cleanup.analysis.md` | gap-detector Match Rate 100% |
| Report | 본 문서 | — |

---

## 3. Key Decisions (코드 근거 확정)

| # | 결정 | 근거 |
|---|------|------|
| Q1 | 검색 결정을 analyze 노드 내부 structured 호출 | 그래프 토폴로지 최소 변경, thin DDD |
| Q2 | `web_search_results` 미존재 시에만 1회 호출 | retry가 web_search 강제 → 중복 불필요, 비용 1회 + 루프 방지 |
| Q3 | SandboxExecutor/`python_code_executor` 유지 | `tool_registry`+`V008__seed_internal_tools.sql`로 커스텀 에이전트 정식 도구 |
| Q4 | supervisor는 입력 dict만 정리 | `_run_excel_analysis`는 출력 `analysis_text`만 소비 |

---

## 4. Implementation Detail

### 4.1 신규
- `src/domain/search_decision/schemas.py` — `WebSearchDecision`(VO)
- `src/domain/search_decision/interfaces.py` — `SearchDecisionInterface`(포트)
- `src/infrastructure/search_decision/adapter.py` — `LLMSearchDecisionAdapter`(`with_structured_output`, 실패 시 False graceful)
- 테스트 2종

### 4.2 리팩토링
- `excel_analysis_workflow.py` — `execute_code` 노드/`execute` 분기/코드 상태 3필드/`_detect_code`·`_extract_code`·태그 `_should_search` 제거; `_analyze_node`가 텍스트+structured 검색결정; `_should_retry_or_complete`로 개명; 프롬프트 코드/`[SEARCH]` 지시 제거
- 연쇄: `AnalysisResult`·`analyze_excel_use_case`·`analysis_router`(코드 필드 제거) / `main.py`(`SandboxExecutor`→`LLMSearchDecisionAdapter`) / `workflow_compiler._run_excel_analysis` / `analysis_policy`(`code_executing` 제거)
- 부수: 워킹트리에 있던 router의 `langsmith` import 누락 버그를 application 레이어(use_case)로 이동 — 아키텍처 위반 회피

---

## 5. Verification

- **gap-detector**: Match Rate 100%, 검증 포인트 7/7 PASS
- **테스트**: 64건 PASS (격리 실행으로 Windows 이벤트 루프 flakiness 회피)
- **verify-architecture**: 신규 도메인/인프라 위반 0건 (domain→infra 역참조 없음, infra Policy 없음, routes→infra 직접참조 없음)
- **API 계약**: 프론트가 `executed_code`/`code_output` 미참조(grep 0건) → 추가 조치 불필요

---

## 6. Follow-ups

| ID | 후속 작업 | 비고 |
|----|----------|------|
| N1 | `chart_router` viz_decision → `ChartBuilder`(ChartConfig) 실제 연결 | 별도 Plan. 백엔드 `ChartBuilderInterface`/`ChartStylePolicy` 재사용 |
| N2 | 프론트 Excel 차트 렌더링 (`agent_answer_completed.charts` 신설 + `/api-contract-sync`) | N1 이후 |
| Doc | `src/claude/task/task-excel-analysis-agent.md` deprecated 표기 | 코드 영향 없음 (선택) |

---

## 7. Lessons Learned

- 아카이브 문서(`analysis-chart-router`)가 "죽은 경로, 코드는 남기되 분리"로 명시해 둔 덕에 이번 정리의 범위가 명확했다. **deferred 결정은 근거와 함께 문서화**하면 후속이 빠르다.
- 샌드박스 **허용 모듈 화이트리스트**(matplotlib 부재)가 차트-코드 경로를 사실상 죽게 만든 근본 원인 — 기능 설계 시 실행 환경 제약을 먼저 확인해야 한다.
- 리팩토링 중 발견한 무관한 기존 버그(router langsmith import 누락)는 **아키텍처적으로 올바른 위치(application)** 로 고쳐 verify-architecture 위반을 만들지 않았다.

---

## 8. 다음 단계

```
/pdca archive excel-analysis-routing-cleanup
```
완료 문서(plan/design/analysis/report)를 `docs/archive/2026-06/`로 아카이브.
