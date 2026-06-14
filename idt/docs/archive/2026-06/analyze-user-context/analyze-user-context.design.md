# ANALYZE_USER_CONTEXT (Design): 분석 노드 사용자·부서 컨텍스트 주입

> 상태: Design
> 연관 Task: ANALYZE-USERCTX-001 (blockedBy: Plan)
> 작성일: 2026-06-09
> Plan: `docs/01-plan/features/analyze-user-context.plan.md`
> 대상 노드: `excel_analysis_workflow.py :: _analyze_node` (그래프 노드명 `analyze_with_claude`)

---

## 0. 설계 결정 확정 (Plan §8 미해결 이슈 해소)

사용자 지시에 따라 Plan의 열린 결정을 다음과 같이 못박는다.

| # | 이슈 | 확정 결정 | 근거 |
|---|------|-----------|------|
| D1 | state에 문자열 vs `AuthContext` 객체 | **렌더 완료 문자열 `user_context_block: str`** 보관 (권장안) | 워크플로우가 렌더 책임에서 분리됨. `ExcelAnalysisState`에 mutable/외부 객체 안 들임 → 직렬화·테스트 단순 |
| D2 | 경로 ① 단독 라우터 인증 정책 | **현재대로 유지** — `analysis_router` 인증 결합 **이번 iteration 제외** | 익명 허용 엔드포인트 그대로. supervisor 경로(ContextVar 세팅됨)가 실제 "내 휴가" 질의 경로이므로 그곳만 실질 수정 |
| D3 | supervisor 두 분기 블록 계산 공용화 | **공용 ContextVar 폴백 1줄**로 통일 (`render_user_context_block(get_current_auth_context())`) | `run_agent_use_case.py:209`에서 이미 ContextVar 세팅 → 별도 배선 불필요 |

> D2 결과: 단독 엑셀 분석 경로는 **회귀 0**으로 현재 동작 그대로 유지되되, `AnalyzeExcelUseCase`에는 **forward-compatible optional 키워드 `auth_ctx`만** 추가(기본 None)하여 추후 라우터 배선 시 1줄로 연결 가능하게 둔다. 라우터 자체는 건드리지 않는다.

---

## 1. 개요 (What & Why)

`analyze_with_claude` 노드의 프롬프트에 **로그인 사용자 신원(이름·대표부서·역할·권한 라벨)** 블록을 prepend하여, "나의 휴가는 며칠 남았어?"처럼 1인칭으로 자기 자신을 지칭하는 질의를 분석 노드가 처리할 수 있게 한다. 블록 생성은 **기존 `render_user_context_block`을 재사용**하며 신규 렌더러를 만들지 않는다(화이트리스트 누출 방어 자동 상속).

- 신원 **매핑**만 제공 — 실제 휴가 일수 등 데이터는 여전히 엑셀/도구 결과에 존재해야 함(추측·창작 금지 규칙 유지).
- 그래프 구조·노드 추가 없음. state 필드 1개 + 프롬프트 조립부 수정 + supervisor 분기 1줄.

---

## 2. 아키텍처 / 데이터 흐름

### 2-1. 블록 소스 우선순위 (단일 규칙)

```
analyze_with_claude(_analyze_node):
    block = state.get("user_context_block")          # ① 명시 주입(있으면 우선)
    if not block:
        block = render_user_context_block(            # ② ContextVar 폴백
            get_current_auth_context()
        )
    prompt = _build_analysis_prompt(query, excel_data, web, user_block=block)
```

- `render_user_context_block(None | anonymous)` → `""` → 프롬프트 변화 없음(회귀 0).
- 두 소스 모두 비면 빈 문자열 → 기존과 동일.

### 2-2. 경로별 블록 주입 지점

```
[경로 ② supervisor — 실제 "내 휴가" 질의 경로]
run_agent_use_case (auth_ctx ContextVar SET, :209)
  └─ compiler.analysis_node
       ├─ excel 분기:  _run_excel_analysis → initial["user_context_block"]
       │                 = render_user_context_block(get_current_auth_context())   ★추가
       │                 → ExcelAnalysisWorkflow.run → _analyze_node (state 필드 사용)
       └─ context 분기: _analyze_context → analysis_prompt 앞에 block prepend         ★추가

[경로 ① 단독 엑셀 — 현재대로 유지]
analysis_router (익명, 변경 없음)
  └─ AnalyzeExcelUseCase.execute(auth_ctx=None 기본)                                  ☆forward-compat
       → initial["user_context_block"] = render_user_context_block(auth_ctx)  # None → ""
       → ExcelAnalysisWorkflow.run → _analyze_node
       (ContextVar 미세팅 → block "" → 현재와 동일)
```

★ = 이번 iteration 실질 변경 / ☆ = optional 파라미터만 추가(라우터 미변경)

---

## 3. 상세 변경 (파일별)

### 3-1. `src/application/workflows/excel_analysis_workflow.py`

**(a) import 추가**

```python
from src.application.agent_run.auth_context import get_current_auth_context
from src.application.agent_run.prompt_rendering import render_user_context_block
```

> 둘 다 application 레이어 내부 참조 → DDD 위반 없음(app→app).

**(b) `ExcelAnalysisState`에 필드 추가**

```python
class ExcelAnalysisState(TypedDict):
    ...
    charts: list
    # analyze-user-context: 분석 프롬프트 앞에 prepend할 렌더 완료 사용자 블록.
    # 빈 문자열이면 미인증/미주입 → 프롬프트 변화 없음.
    user_context_block: str
```

**(c) `_analyze_node` — 블록 결정 후 프롬프트 빌더에 전달** (line 191~196 부근)

```python
web_results = state.get("web_search_results", "")
user_block = state.get("user_context_block") or render_user_context_block(
    get_current_auth_context()
)
prompt = self._build_analysis_prompt(
    state["user_query"],
    state["excel_data"],
    web_results,
    user_block=user_block,
)
```

**(d) `_build_analysis_prompt` — 시그니처 + 본문 prepend** (line 299~319)

```python
def _build_analysis_prompt(
    self, query: str, excel_data: dict, web_context: str, user_block: str = ""
) -> str:
    """분석 프롬프트 생성.

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
```

> `user_block`은 `render_user_context_block`이 만든 `"[현재 사용자 정보]...\n---\n\n"` 형태이거나 `""`. 따라서 f-string 맨 앞 `{user_block}` 직접 삽입으로 충분.

### 3-2. `src/application/use_cases/analyze_excel_use_case.py` (forward-compat, 라우터 미변경)

**(a) import 추가**

```python
from src.application.agent_run.prompt_rendering import render_user_context_block
from src.domain.agent_run.auth_context import AuthContext
```

**(b) `execute` 시그니처에 keyword-only `auth_ctx` 추가** (line 42~48)

```python
async def execute(
    self,
    excel_file_path: str,
    user_query: str,
    user_id: str,
    request_id: str | None = None,
    *,
    auth_ctx: AuthContext | None = None,   # analyze-user-context: 기본 None(현재 동작 유지)
) -> AnalysisResult:
```

**(c) `initial_state`에 필드 주입** (line 71~91)

```python
initial_state = {
    ...
    "viz_decision": "",
    "charts": [],
    # analyze-user-context: 미인증이면 render가 "" 반환 → 프롬프트 변화 없음.
    "user_context_block": render_user_context_block(auth_ctx),
}
```

> `analysis_router`는 **변경하지 않는다**(D2). 현재 호출 `use_case.execute(excel_file_path=..., user_query=..., user_id=...)`은 `auth_ctx` 미전달 → None → `""`. 기존과 100% 동일.

### 3-3. `src/application/agent_builder/workflow_compiler.py` (실질 수정 — 경로 ②)

> 이미 `render_user_context_block`(line 20), `AuthContext`(line 45) import 됨. `get_current_auth_context`만 추가 필요.

**(a) import 추가**

```python
from src.application.agent_run.auth_context import get_current_auth_context
```

**(b) `_run_excel_analysis` — initial state에 블록 주입** (line 602~624)

```python
async def _run_excel_analysis(self, wf, question: str, excel: dict, logger) -> str:
    initial = {
        "request_id": "",
        "user_query": question,
        ...
        "viz_decision": "",
        "charts": [],
        # analyze-user-context: ContextVar(run_agent_use_case에서 세팅됨) 기반 사용자 블록.
        "user_context_block": render_user_context_block(get_current_auth_context()),
    }
```

**(c) `_analyze_context` — 비-엑셀 분석 분기 system prompt 앞에 블록 prepend** (line 649~654)

```python
user_block = render_user_context_block(get_current_auth_context())
analysis_prompt = (
    f"{user_block}{system_prompt}\n\n"
    f"당신은 데이터 분석가입니다. {source_hint} 사용자의 질문에 답합니다.\n\n"
    f"{ANALYSIS_OUTPUT_GUIDE}\n\n"
    f"[분석 대상 데이터]\n{context}\n\n[질문]\n{question}"
)
```

### 3-4. 라우터 / 프론트 — 변경 없음

- `analysis_router.py`: 변경 없음(D2).
- 응답 스키마 불변 → `/api-contract-sync`·프론트 변경 불필요.

---

## 4. 보안 / 화이트리스트 (불변식)

- 노출 필드는 `render_user_context_block`이 화이트리스트로 고정: **이름·대표부서·역할·권한 라벨만**. 사번/이메일/숫자 user_id 노출 불가(`prompt_rendering.py:25-30` 규약).
- 이번 작업은 렌더러를 **호출만** → 새 노출 표면 0.
- `AuthContext`는 frozen VO이므로 ContextVar 경유 전달 중 변조 불가.

---

## 5. 테스트 설계 (TDD: RED → GREEN)

### 5-1. 프롬프트 회귀 (application) — `tests/application/workflows/test_excel_analysis_prompt.py`
- `_build_analysis_prompt("Q", {"a":1}, "", user_block="[현재 사용자 정보]\n- 이름: 배상규\n---\n\n")`
  → 결과가 `user_block`으로 **시작**하고, "배상규"·"## 사용자 질문"·"Q" 포함.
- `user_block=""` (기본) → 결과가 "당신은 데이터 분석 결과를..."로 시작(블록 없음, **회귀 검증**).

### 5-2. 블록 소스 우선순위 (application) — `_analyze_node` 단위
- (state 우선) state `user_context_block="BLOCK_S"` + ContextVar=배상규 → FakeClaude 프롬프트에 "BLOCK_S" 포함, ContextVar 블록 미사용.
- (ContextVar 폴백) state 필드 없음/"" + ContextVar=배상규 → 프롬프트에 "배상규" 포함.
- (둘 다 없음) state 없음 + ContextVar None → 프롬프트에 "[현재 사용자 정보]" 미포함(빈 블록, 회귀 0).

### 5-3. 경로 ① use case (application) — `tests/application/use_cases/test_analyze_excel_use_case.py`
- `execute(..., auth_ctx=AuthContext(display_name="배상규", primary_department_name="여신관리부", role="user", ...))`
  → 워크플로우 초기 state `user_context_block`에 "배상규"·"여신관리부" 포함.
- `execute(...)` (auth_ctx 미전달) → `user_context_block == ""` (**현재 동작 유지 검증**).

### 5-4. 경로 ② supervisor (application) — `workflow_compiler`
- ContextVar=배상규 세팅 후 `_run_excel_analysis` 호출(FakeWorkflow가 initial 캡처) → initial["user_context_block"]에 "배상규" 포함.
- ContextVar=배상규, 검색결과 없는 `_analyze_context` 호출 → FakeLLM system 메시지가 "[현재 사용자 정보]"로 시작.

> Windows 이벤트 루프 플레이키 → 신규 비동기 테스트는 **격리 실행**으로 그린 확인(메모리 노트: backend-test-eventloop-flakiness).

---

## 6. 영향 범위 / 리스크

| 항목 | 영향 | 비고 |
|------|------|------|
| 단독 엑셀 분석(경로 ①) | **회귀 0** | auth_ctx 미전달 → block "" → 현재와 동일 |
| supervisor 엑셀/문맥 분석(경로 ②) | 인증 시 사용자 블록 주입 | ContextVar 이미 세팅 → 배선 추가 없음 |
| 프롬프트 길이 | 인증 시 소폭 증가 | 무시 가능 |
| 그래프 구조 / 응답 스키마 | **불변** | 프론트·api-contract 불필요 |
| 민감정보 | 화이트리스트 렌더러 재사용 | 누출 0 |
| `_build_analysis_prompt` 호출부 | 1곳(`_analyze_node`)만 변경 | 회귀 위험 낮음 |

---

## 7. 구현 순서 (Do 단계 체크리스트)

1. `_build_analysis_prompt` 회귀 테스트(RED) → 시그니처 `user_block=""` + 본문 prepend(GREEN) — §5-1
2. `ExcelAnalysisState.user_context_block` 추가 + `_analyze_node` 블록 결정(state 우선/ContextVar 폴백) + import — §5-2
3. `AnalyzeExcelUseCase.execute`에 `*, auth_ctx=None` + initial 주입 + 테스트(라우터 **미변경**) — §5-3
4. `workflow_compiler`: `get_current_auth_context` import + `_run_excel_analysis`/`_analyze_context` 블록 주입 + 테스트 — §5-4
5. 전체 테스트 **격리 실행**으로 그린 확인
6. `/pdca analyze analyze-user-context` (Gap 분석) → Report

---

## 8. 후속 (이번 범위 외)

- **경로 ① 라우터 인증 결합**: `analysis_router`에 인증 의존성 추가 → `AssembleAuthContextUseCase`로 `auth_ctx` 조립해 `execute(auth_ctx=...)` 전달. (D2로 보류 — 별도 Task)
- supervisor 블록 계산 헬퍼 추출(현재 1줄 중복은 허용 수준).
