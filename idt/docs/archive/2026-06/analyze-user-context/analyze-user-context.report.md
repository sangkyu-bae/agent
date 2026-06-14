# ANALYZE_USER_CONTEXT: 분석 노드 사용자·부서 컨텍스트 주입 완료 보고서

> 상태: Report (완료)
> 연관 Task: ANALYZE-USERCTX-001
> 보고일: 2026-06-10
> 소스:
> - Plan: `docs/01-plan/features/analyze-user-context.plan.md`
> - Design: `docs/02-design/features/analyze-user-context.design.md`
> - Analysis: `docs/03-analysis/analyze-user-context.analysis.md`

---

## Executive Summary

### 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **기능** | 분석 노드(`_analyze_node`)의 프롬프트에 로그인 사용자 신원(이름·대표부서·역할·권한 라벨) 컨텍스트 블록 주입. "나의 휴가는 며칠 남았어?"처럼 1인칭 질의가 정상 동작하도록 개선 |
| **기간** | 설계 ~ 검증: 2026-06-09 ~ 2026-06-10 (2일) |
| **소유자** | 배상규 (AI Agent Platform 팀) |
| **선행 작업** | `analyze_with_claude` 노드(프롬프트 엄격화·차트 분리) — archived 2026-06 |

### 결과 요약

| 지표 | 결과 |
|------|------|
| **설계 일치도** | 96.2% (90% 게이트 초과) ✅ |
| **검증 항목** | 13개: 12 Full Match / 1 Partial / 0 Missing |
| **변경 파일** | 4개 (3 source + 1 test) |
| **테스트 커버리지** | 전체 케이스(프롬프트 회귀·상태 우선순위·2경로) 검증 완료 |

**변경 파일 목록:**
- `src/application/workflows/excel_analysis_workflow.py` (프롬프트 + state 필드 + 노드 로직)
- `src/application/use_cases/analyze_excel_use_case.py` (forward-compatible 키워드 추가)
- `src/application/agent_builder/workflow_compiler.py` (경로 ② 블록 주입)
- `tests/application/test_analyze_user_context.py` (4개 케이스 통합)

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem (해결한 문제)** | 분석 노드가 "나의 ~" 1인칭 자기지칭 질의를 처리할 수 없었음. 프롬프트에 로그인 사용자 신원 정보가 없어서 모델이 엑셀/도구 결과에서 본인의 행(行)을 특정할 근거가 없었음 |
| **Solution (해결 방법)** | 기존 `render_user_context_block` 렌더러(이미 `general_chat` 경로에서 사용 중)를 분석 노드 프롬프트 맨 앞에 prepend. 두 진입 경로(①단독 엑셀 ②Supervisor 재사용)에 동일 적용. 미인증/미주입 시 빈 문자열로 기존 동작 그대로 유지(회귀 0) |
| **Function/UX Effect (기능 영향)** | "나의 휴가 며칠 남았어?", "내 부서 실적 알려줘" 등 1인칭 질문이 정상 작동. 모델이 "나 = 배상규/여신관리부"로 매핑한 뒤 엑셀·도구 데이터에서 본인 행을 정확히 골라 답변 가능. 미인증 호출은 블록 공백으로 처리되어 기존 기능 미영향 |
| **Core Value (핵심 가치)** | 분석 경로와 대화 경로(general_chat)의 사용자 컨텍스트 일관성 확보. RAG·엑셀 분석이 개인화된 답변을 제공할 수 있게 함. 화이트리스트 렌더러 재사용으로 사번·이메일·user_id 등 민감정보 누출 없이 신원만 제공(보안 강화) |

---

## PDCA 사이클 요약

### Plan

**문서:** `docs/01-plan/features/analyze-user-context.plan.md`

**목표:** 분석 노드의 프롬프트에 로그인 사용자 신원 정보를 주입하여, "내 ~" 자기지칭 질의가 정상 동작하는 분석 경로 확보

**예상 기간:** 2일

---

### Design

**문서:** `docs/02-design/features/analyze-user-context.design.md`

**주요 설계 결정:**

| 결정 ID | 이슈 | 결정 | 근거 |
|--------|------|------|------|
| **D1** | state에 문자열 vs `AuthContext` 객체 | **렌더 완료 문자열 `user_context_block: str`** 보관 | 워크플로우가 렌더 책임에서 분리. 직렬화·테스트 단순화 |
| **D2** | 경로 ① 단독 라우터 인증 정책 | **현재대로 유지** — 라우터 변경 제외 | supervisor 경로(②)가 실제 "내 휴가" 질의 경로. ① 단독은 forward-compatible optional 파라미터만 추가 |
| **D3** | supervisor 두 분기 블록 계산 공용화 | **ContextVar 폴백 1줄 통일** | `run_agent_use_case.py:209`에서 이미 ContextVar 세팅. 별도 배선 불필요 |

**변경 상세:**

| 위치 | 변경 내용 |
|------|----------|
| `excel_analysis_workflow.py` | `ExcelAnalysisState.user_context_block: str` 필드 추가 / `_analyze_node` state 우선→ContextVar 폴백 / `_build_analysis_prompt` 시그니처 + prepend |
| `analyze_excel_use_case.py` | `execute(..., *, auth_ctx=None)` 키워드 추가 / initial_state에 블록 주입(기본 None → `""`) |
| `workflow_compiler.py` | `_run_excel_analysis` initial 블록 주입 / `_analyze_context` prompt 앞 prepend |
| `analysis_router.py` | **변경 없음**(D2 결정) |

---

### Do

**구현 범위:**

| 항목 | 파일 | 상태 |
|------|------|------|
| 프롬프트 회귀 + 필드 추가 | `excel_analysis_workflow.py` | ✅ L21-22 (import), L70-72 (state), L200-208 (_analyze_node), L311-323 (_build_analysis_prompt) |
| forward-compatible 시그니처 | `analyze_excel_use_case.py` | ✅ L9, L11 (import), L50-51 (execute 시그니처), L98-99 (initial_state) |
| 경로 ② 블록 주입 | `workflow_compiler.py` | ✅ L20 (import), L625-628 (_run_excel_analysis), L654, L657-662 (_analyze_context) |
| 테스트 (TDD) | `tests/application/test_analyze_user_context.py` | ✅ 4개 클래스: TestBuildAnalysisPromptUserBlock, TestAnalyzeNodeBlockResolution, TestUseCaseAuthCtxInjection, TestSupervisorAnalysisUserBlock |

**실제 소요 기간:** 1일

---

### Check

**문서:** `docs/03-analysis/analyze-user-context.analysis.md`

**분석 결과:**

| 항목 | 결과 |
|------|------|
| 설계 일치도 | 100% (Design 코드 항목 완전 준수) |
| 아키텍처 준수 | 100% (application 레이어 내부 참조, domain→infrastructure 누수 없음) |
| 컨벤션 준수 | 100% (snake_case, 명시적 타입, print 없음) |
| **전체 일치도 (보수)** | **96.2%** (12 Full / 1 Partial / 0 Missing) ✅ |

**검증 항목:**

| 항목 | 상태 | 근거 |
|------|:----:|------|
| 프롬프트 회귀 (prepend + 빈 기본값) | ✅ | `TestBuildAnalysisPromptUserBlock` L105-122 |
| 블록 소스 우선순위 (state > ContextVar > none) | ✅ | `TestAnalyzeNodeBlockResolution` L128-174 |
| use case auth_ctx 전달 vs 미전달 | ✅ | `TestUseCaseAuthCtxInjection` L208-237 |
| 경로 ② excel + `_analyze_context` 블록 주입 | ✅ | `TestSupervisorAnalysisUserBlock` L251-294 |
| D2 준수 (라우터 미변경, forward-compat) | ✅ | `analysis_router.py:10, 66-70` (auth_ctx 없음) |
| 보안 불변식 (화이트리스트 미확장) | ✅ | 렌더러 미변경, user_id/사번/이메일 미노출 |

**발견된 Gap:**

🔵 **Partial (비즈니스 영향 없음)** — 테스트 파일 구성

| 설계 예상 | 구현 실제 | 영향도 |
|-----------|-----------|--------|
| §5의 3개 분리 파일 (`test_excel_analysis_prompt.py`, `test_analyze_excel_use_case.py`, workflow_compiler 테스트) | 단일 `tests/application/test_analyze_user_context.py`에 4개 클래스 통합 | Low |

**상세:** 모든 Design 테스트 케이스(프롬프트 회귀, 우선순위, 회귀 검증, 경로 ① auth_ctx, 경로 ② excel+context) 100% 커버. 파일 구성만 기능별 분리가 아닌 feature별 단일 통합.

---

## 구현 요약

### 파일별 변경 내역

#### 1. `src/application/workflows/excel_analysis_workflow.py`

**추가 import:**
```python
from src.application.agent_run.auth_context import get_current_auth_context
from src.application.agent_run.prompt_rendering import render_user_context_block
```

**ExcelAnalysisState 필드 추가:**
```python
user_context_block: str  # 분석 프롬프트 앞에 prepend할 렌더 완료 사용자 블록
```

**_analyze_node 로직:**
```python
user_block = state.get("user_context_block") or render_user_context_block(
    get_current_auth_context()
)
# state 필드 우선 → ContextVar 폴백
```

**_build_analysis_prompt 시그니처 + 본문:**
```python
def _build_analysis_prompt(
    self, query: str, excel_data: dict, web_context: str, user_block: str = ""
) -> str:
    return f"""{user_block}당신은 데이터 분석 결과를...
    # user_block 맨 앞 prepend (빈 값이면 기존과 동일)
```

#### 2. `src/application/use_cases/analyze_excel_use_case.py`

**추가 import:**
```python
from src.application.agent_run.prompt_rendering import render_user_context_block
from src.domain.agent_run.auth_context import AuthContext
```

**execute 시그니처 (forward-compatible):**
```python
async def execute(
    self,
    excel_file_path: str,
    user_query: str,
    user_id: str,
    request_id: str | None = None,
    *,
    auth_ctx: AuthContext | None = None,  # 기본 None (회귀 0)
) -> AnalysisResult:
```

**initial_state 주입:**
```python
initial_state = {
    ...
    "user_context_block": render_user_context_block(auth_ctx),  # None → ""
}
```

**라우터 미변경:**
- `analysis_router.py`는 변경 없음 (D2 결정)
- 호출 시 `auth_ctx` 미전달 → None → block `""`

#### 3. `src/application/agent_builder/workflow_compiler.py`

**추가 import:**
```python
from src.application.agent_run.auth_context import get_current_auth_context
```

**_run_excel_analysis 블록 주입:**
```python
initial = {
    ...
    "user_context_block": render_user_context_block(get_current_auth_context()),
    # ContextVar(run_agent_use_case:209 세팅)에서 경로 ② 블록 추출
}
```

**_analyze_context 비-엑셀 분기:**
```python
user_block = render_user_context_block(get_current_auth_context())
analysis_prompt = f"{user_block}{system_prompt}\n\n..."
# 검색결과/문맥 분석에도 동일 블록 prepend
```

#### 4. `tests/application/test_analyze_user_context.py` (신규)

**TestBuildAnalysisPromptUserBlock:** 프롬프트 회귀 (§5-1)
- user_block 있음 → 맨 앞 포함, 없음 → 기존 본문 시작

**TestAnalyzeNodeBlockResolution:** 상태 우선순위 (§5-2)
- state 필드 우선, ContextVar 폴백, 둘 다 없음 → 회귀 검증

**TestUseCaseAuthCtxInjection:** 경로 ① forward-compat (§5-3)
- `execute(..., auth_ctx=배상규)` → block 포함
- `execute(...)` (미전달) → block `""` (현재 동작 유지)

**TestSupervisorAnalysisUserBlock:** 경로 ② 블록 주입 (§5-4)
- ContextVar 세팅 후 `_run_excel_analysis` → initial block 포함
- `_analyze_context` → system prompt에 block prepend

---

## 핵심 결정사항

### D1: State 필드로 렌더 완료 문자열 보관

✅ **결정: `user_context_block: str` (렌더 완료 상태 저장)**

- **이유:** 워크플로우가 렌더 책임에서 분리되고, `ExcelAnalysisState`에 mutable/외부 객체(AuthContext)를 두지 않아 직렬화·테스트가 간단함
- **효과:** state 스키마가 모두 primitive type으로 유지되어, 이후 그래프 확장 시 재사용성 높음

### D2: 경로 ① 라우터 인증 정책 — 현재대로 유지 (분리 시행)

✅ **결정: 이번 iteration은 라우터 미변경, `AnalyzeExcelUseCase`에만 forward-compatible 키워드 추가**

- **이유:** 
  - 실제 "내 휴가" 질의의 진입 경로는 **경로 ②(Supervisor 재사용)**이고, 여기서는 이미 `run_agent_use_case.py:209`에서 ContextVar 세팅됨
  - 경로 ①(단독 엑셀)은 현재 익명 허용 엔드포인트로, 인증이 선택적
  - 라우터를 건드리면 API 계약 변경 → 프론트 의존성 증가
- **효과:**
  - 경로 ①은 회귀 0 유지 (auth_ctx 미전달 → block `""`)
  - 경로 ②는 즉시 동작 (ContextVar 폴백)
  - 라우터 인증 결합은 별도 Task로 분리 (향후 `[Design] analysis-router-auth-binding` 등으로 진행 가능)

### D3: 두 분기(엑셀/비-엑셀) 블록 계산 — ContextVar 폴백 1줄 통일

✅ **결정: `render_user_context_block(get_current_auth_context())` 재사용**

- **이유:** `run_agent_use_case.py:209`에서 ContextVar이 이미 세팅되므로, 별도 배선(클로저 캡처 등)이 불필요
- **효과:** 두 분기 간 일관성 확보, 코드 중복 최소화 (1줄짜리 ContextVar 폴백)

---

## 보안 고려사항

### 화이트리스트 불변식 (유지)

✅ **노출 필드 제한:**
- **허용:** 이름, 대표부서, 역할, 권한 라벨만
- **금지:** 사번, 이메일, 숫자 user_id, 직급코드 등

**이번 작업의 보안 영향도:**
- `render_user_context_block`을 **호출만** 함 (렌더러 수정 없음)
- 새 노출 표면 **0**
- 렌더러의 화이트리스트가 자동으로 누출 방어

---

## 위험도 및 영향 범위

| 항목 | 영향 | 비고 |
|------|------|------|
| **그래프 구조** | 없음 | 노드·엣지 추가 0, state 필드 1개만 |
| **응답 스키마** | 없음 | AnalysisResult 불변, `/api-contract-sync` 불필요 |
| **경로 ① (단독 엑셀)** | 회귀 0 | auth_ctx 미전달 → block `""` → 기존 동작 |
| **경로 ② (Supervisor)** | 개선 | ContextVar 세팅 → 즉시 사용자 블록 주입 |
| **프롬프트 길이** | 소폭 증가 | 사용자 블록 약 10~15줄 (인증 시에만) |
| **민감정보 노출** | 없음 | 화이트리스트 렌더러 재사용, user_id 미노출 |

---

## 테스트 커버리지

### 검증된 케이스 (All GREEN)

| 케이스 | 파일 | 라인 |
|--------|------|------|
| 프롬프트 prepend + 기본값 회귀 | `test_analyze_user_context.py` | L105-122 |
| state > ContextVar > None 우선순위 | `test_analyze_user_context.py` | L128-174 |
| auth_ctx 전달 vs 미전달 (forward-compat) | `test_analyze_user_context.py` | L208-237 |
| 경로 ② 엑셀 + 비-엑셀 분기 블록 주입 | `test_analyze_user_context.py` | L251-294 |

**Windows 이벤트 루프 플레이키 대책:**
- 신규 비동기 테스트는 격리 실행으로 검증 (메모리 노트: backend-test-eventloop-flakiness)

---

## 교훈 및 개선사항

### 잘된 점

1. **기존 패턴 재사용:** `render_user_context_block`(general_chat에서 이미 사용) 재사용으로 새 코드 최소화 + 보안 자동 상속
2. **이중화 설계:** state 필드(명시) + ContextVar 폴백으로 두 진입 경로 모두 대응
3. **forward-compatible 설계:** 라우터 변경 없이 `auth_ctx` 키워드로 향후 확장 가능 (D2)
4. **파일 통합 테스트:** feature별 단일 파일로 통합하여 테스트 가독성 우수

### 개선 기회

1. **라우터 인증 결합 (D2 후속):** 이번 iteration은 경로 ②만 실질 수정, 경로 ①은 회귀. 향후 `analysis_router`에 `AssembleAuthContextUseCase` 의존성 추가로 두 경로 완전 통일 (별도 Task)
2. **블록 계산 헬퍼 추출 (선택):** supervisor 두 분기에서 `render_user_context_block(get_current_auth_context())` 1줄이 2회 반복. 현재는 허용 수준, 향후 헬퍼 추출 가능

---

## 후속 작업

### 즉시 (없음)

구현이 Design 전 코드 항목과 완전 일치. 아키텍처·컨벤션·보안 모두 준수.

### 선택 (문서 다듬기)

**Design §5 파일명 갱신:**
- 현재 Design: 3개 분리 파일(`test_excel_analysis_prompt.py`, `test_analyze_excel_use_case.py`, workflow_compiler 테스트) 명시
- 실제 코드: 단일 `tests/application/test_analyze_user_context.py` (4개 클래스)
- 권장: Design §5를 실제 구현 경로로 갱신 또는 팀 컨벤션이 file-per-concern 강제 시 3개 파일로 분리 재구성

### 후속 Task (Design의 §8)

1. **경로 ① 라우터 인증 결합 (미루어진 작업):**
   - Task명: `[Design] analysis-router-auth-binding` (또는 별도 Do Task)
   - 내용: `analysis_router`에 `AssembleAuthContextUseCase` 의존성 결합 → `auth_ctx` 조립 후 `use_case.execute(auth_ctx=...)` 전달
   - 효과: 경로 ①도 인증 사용자 블록 주입 가능 (현재는 익명만 가능)

2. **블록 계산 헬퍼 추출 (선택):**
   - supervisor `_run_excel_analysis` + `_analyze_context`에서 반복되는 1줄을 공용 method로 추출
   - 현재: 코드 중복이 1줄이므로 우선순위 낮음

---

## 결론

✅ **완료 상태: PASS**

- **설계 일치도 96.2%** (90% 게이트 초과)
- **기능 동기화 불필요** (Partial은 테스트 파일 구성 문구만)
- **실제 비즈니스 문제 해결:** "나의 휴가는 며칠 남았어?" 1인칭 질의가 분석 경로에서 정상 동작
- **보안 강화:** 화이트리스트 렌더러 재사용으로 민감정보 누출 없음
- **회귀 0:** 미인증/경로 ① 동작 그대로 유지

**다음 단계:** 경로 ① 라우터 인증 결합은 별도 Task로 진행. 현재 feature는 경로 ②(실제 사용 경로)의 완전 지원으로 사용자 가치 충분.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-10 | Completion report from gap analysis (96.2% match) | report-generator |
