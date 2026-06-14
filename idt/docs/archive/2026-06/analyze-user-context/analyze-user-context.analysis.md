# Gap Analysis: analyze-user-context

> 분석일: 2026-06-10
> Phase: Check (gap-detector)
> Design: `docs/02-design/features/analyze-user-context.design.md`
> Plan: `docs/01-plan/features/analyze-user-context.plan.md`

---

## 1. 분석 개요

| 항목 | 내용 |
|------|------|
| 분석 대상 | analyze-user-context (분석 노드 사용자·부서 컨텍스트 주입) |
| Design | `docs/02-design/features/analyze-user-context.design.md` |
| Implementation | `excel_analysis_workflow.py`, `analyze_excel_use_case.py`, `workflow_compiler.py` |
| Tests | `tests/application/test_analyze_user_context.py` |
| 분석일 | 2026-06-10 |

---

## 2. 전체 점수

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% | ✅ |
| Architecture Compliance | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| **Overall (conservative)** | **96.2%** | ✅ |

> 검증 항목 13개 중 Full Match 12 / Partial 1 / Missing 0 → (12 + 0.5×1)/13 = **96.2%**. 90% 게이트 초과.

---

## 3. 항목별 검증

### Item 1 — `src/application/workflows/excel_analysis_workflow.py`

| # | Design 항목 | 결과 | 근거 |
|---|-------------|:----:|------|
| 1-a | import `get_current_auth_context` + `render_user_context_block` | Match | L21-22 |
| 1-b | `ExcelAnalysisState.user_context_block: str` 필드 | Match | L70-72 |
| 1-c | `_analyze_node` state 우선 / ContextVar 폴백 후 `user_block=` 전달 | Match | L200-208 |
| 1-d | `_build_analysis_prompt(... user_block: str="")` 맨 앞 prepend | Match | L311-323 |

### Item 2 — `src/application/use_cases/analyze_excel_use_case.py` (forward-compat, 라우터 미변경)

| # | Design 항목 | 결과 | 근거 |
|---|-------------|:----:|------|
| 2-a | import `render_user_context_block` + `AuthContext` | Match | L9, L11 |
| 2-b | `execute` keyword-only `*, auth_ctx: AuthContext \| None = None` | Match | L50-51 |
| 2-c | `initial_state["user_context_block"] = render_user_context_block(auth_ctx)` | Match | L98-99 |
| D2 | `analysis_router.py` 미변경 (auth_ctx 미전달) | Match | `analysis_router.py:10, 66-70` (import·호출 모두 auth_ctx 없음) |

### Item 3 — `src/application/agent_builder/workflow_compiler.py`

| # | Design 항목 | 결과 | 근거 |
|---|-------------|:----:|------|
| 3-a | import `get_current_auth_context` 추가 | Match | L20 (render_user_context_block L21, AuthContext L46 기존) |
| 3-b | `_run_excel_analysis` initial state에 블록 주입 | Match | L625-628 |
| 3-c | `_analyze_context` `analysis_prompt` 앞에 `{user_block}` prepend | Match | L654, L657-662 |

### Item 4 — 테스트 (TDD)

| # | Design §5 케이스 | 결과 | 근거 |
|---|------------------|:----:|------|
| 5-1 | 프롬프트 회귀 (prepend + 빈 기본값) | Match | `TestBuildAnalysisPromptUserBlock` L105-122 |
| 5-2 | 블록 소스 우선순위 (state > ContextVar > none) | Match | `TestAnalyzeNodeBlockResolution` L128-174 |
| 5-3 | use case auth_ctx 전달 vs 미전달 | Match | `TestUseCaseAuthCtxInjection` L208-237 |
| 5-4 | 경로 ② excel + `_analyze_context` 블록 주입 | Match | `TestSupervisorAnalysisUserBlock` L251-294 |
| 파일 구성 | Design은 3개 분리 파일 명시, 실제 단일 파일 통합 | **Partial** | 모든 케이스 커버. 파일명만 상이 |

### 보안 불변식

| 항목 | 결과 | 근거 |
|------|:----:|------|
| 노출 화이트리스트 미확장 (이름·대표부서·역할 라벨·권한 라벨만) | Match | `prompt_rendering.py:31-62` — 렌더러 미변경, user_id/사번/이메일 미노출. 이번 작업은 호출만 |

---

## 4. 발견된 Gap

### 🔴 Missing — 없음
### 🟡 Added — 없음
### 🔵 Partial

| 항목 | Design | 구현 | 영향 |
|------|--------|------|:----:|
| 테스트 파일 구성 | §5 — `test_excel_analysis_prompt.py` / `test_analyze_excel_use_case.py` / workflow_compiler 테스트 (분리) | 단일 `tests/application/test_analyze_user_context.py`에 4개 클래스로 통합 (§5-1~5-4 전부 커버) | Low |

**상세:** 모든 Design 테스트 케이스(프롬프트 회귀, state>ContextVar 우선순위, 빈 기본값 회귀, 경로 ① auth_ctx 전달/미전달, 경로 ② excel + `_analyze_context`)가 존재하고 커버리지 공백 없음. 파일이 기능별 분리가 아닌 feature별 단일 파일로 통합된 점만 Design 문구와 상이.

---

## 5. 권장 조치

### 즉시 — 없음
구현이 Design 전 코드 항목과 일치. D2(라우터 미변경)·보안 불변식(화이트리스트 미확장) 모두 준수. 아키텍처(application 레이어 내부 참조, domain→infra 누수 없음)·컨벤션(snake_case, 명시적 타입, print 없음) 준수.

### 선택(문서 다듬기)
1. (권장) Design §5의 파일명을 단일 통합 경로 `tests/application/test_analyze_user_context.py`로 갱신 — 코드가 진실(CLAUDE.md). 또는 팀 컨벤션이 파일-per-concern을 강제할 경우 3개 파일로 분리.

---

## 6. 결론

Design ↔ 구현 일치도 **96.2%** (90% 게이트 초과). 기능 동기화 불필요(Partial은 테스트 파일 구성 문구만). `/pdca report analyze-user-context` 진행 가능.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-10 | Initial gap analysis | gap-detector |
