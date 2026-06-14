# ANALYZE_USER_CONTEXT: 분석 노드에 로그인 사용자·부서 컨텍스트 주입

> 상태: Plan
> 연관 Task: ANALYZE-USERCTX-001
> 작성일: 2026-06-09
> 우선순위: High
> 대상 노드: `excel_analysis_workflow.py :: _analyze_node` (그래프 노드명 `analyze_with_claude`)
> 선행 작업: `analyze_with_claude`(프롬프트 엄격화/차트 분리) — archived 2026-06

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | `analyze_with_claude` 노드의 프롬프트(`_build_analysis_prompt`)는 **사용자 질문 + 엑셀 데이터 + 웹 검색 결과**만 넣고, **로그인 사용자가 누구인지(이름·부서·역할) 정보를 전혀 주입하지 않는다.** 그래서 "나의 휴가는 며칠 남았어?" 처럼 **"나/내/본인"으로 자기 자신을 지칭하는 질문**이 오면, 모델은 데이터에서 *어느 사람의 행(行)이 '나'인지* 판단할 근거가 없어 엉뚱한 사람을 고르거나 "누구인지 확인되지 않습니다"로 답한다. 동일 시스템의 `general_chat` 경로는 이미 `render_user_context_block(auth_ctx)`로 사용자 컨텍스트를 prepend하는데, **분석 노드만 이 블록이 빠져 있다.** |
| **Solution** | 이미 존재하는 `render_user_context_block`(이름·대표부서·역할·권한 라벨만 화이트리스트로 노출)을 **분석 노드 프롬프트 맨 앞에 prepend**한다. `auth_ctx`를 **명시적 시그니처(state 필드)로 전달**하되, 누락 시 `get_current_auth_context()` ContextVar로 폴백한다(Defense in Depth). 두 진입 경로(① 단독 `AnalyzeExcelUseCase`, ② Supervisor 재사용 `workflow_compiler`)에 동일하게 적용하고, supervisor의 비-엑셀 분석 분기(`_analyze_context`)에도 같은 블록을 넣는다. |
| **Function UX Effect** | "나의 휴가 며칠 남았어?", "내 부서 실적 알려줘" 같은 **1인칭 질문이 정상 동작**한다. 모델이 "나 = 배상규 / OO부서"로 매핑한 뒤, 엑셀·도구 데이터에서 **본인 행을 정확히 골라** 답한다. 미인증(anonymous) 호출은 블록이 빈 문자열로 처리되어 **기존 동작 그대로**(회귀 없음). |
| **Core Value** | **분석 경로와 대화 경로의 사용자 컨텍스트 일관성 확보.** "내 ~"라는 자기지칭 질의를 분석 노드가 처리할 수 있게 되어, RAG/엑셀 분석이 **개인화된 답변**을 낼 수 있다. 화이트리스트 렌더러를 재사용하므로 사번·이메일·user_id 등 **민감정보 누출 없이** 식별만 제공한다. |

---

## 1. 문제 정의 (Problem Statement)

대상: `src/application/workflows/excel_analysis_workflow.py :: _build_analysis_prompt` (line 299~319)

현재 분석 프롬프트는 다음 4개 입력만 조립한다:

```python
return f"""당신은 데이터 분석 결과를 자연어 텍스트로만 작성하는 분석가입니다.
...
## 사용자 질문
{query}
## 엑셀 데이터
{excel_data}
## 웹 검색 결과
{web_context if web_context else "없음"}
{ANALYSIS_OUTPUT_GUIDE}"""
```

여기에 **"지금 질문하는 사람이 누구인가"** 정보가 전혀 없다. 따라서:

```
[로그인: 배상규 / 여신관리부]
[사용자] "나의 휴가는 며칠 남았어?"
   → analyze_with_claude 노드 프롬프트:
        질문="나의 휴가는 며칠 남았어?"
        엑셀데이터=[{이름:배상규, 잔여휴가:5}, {이름:김철수, 잔여휴가:3}, ...]
        (← '나'가 누구인지에 대한 단서 0개)
   → 모델: "어느 분의 휴가를 말씀하시는지 확인되지 않습니다" 또는 임의의 행 선택
```

### 1-1. 동일 시스템에 정답 패턴이 이미 있음

`general_chat` 경로는 사용자 컨텍스트를 system prompt 앞에 붙인다:

```python
# src/application/general_chat/use_case.py:130
prompt = render_user_context_block(auth_ctx) + _SYSTEM_PROMPT
```

`render_user_context_block`(`src/application/agent_run/prompt_rendering.py`)이 만드는 블록:

```
[현재 사용자 정보]
- 이름: 배상규
- 부서: 여신관리부
- 역할: 일반 사용자

사용자가 '나', '내', '본인'이라고 말하면 위 사용자를 의미합니다.

[허용된 정보 영역]
- ...(권한 라벨)
...
```

→ **분석 노드에는 이 블록이 빠져 있다.** 그래서 "내 ~" 질의가 분석 경로로 들어오면 실패한다.

### 1-2. 중요한 범위 명확화 (오해 방지)

`render_user_context_block`은 **신원(이름·부서·역할·권한 라벨)만** 제공한다. **잔여 휴가 숫자 같은 실제 데이터는 여전히 엑셀/도구 결과에 있어야 한다.** 이번 작업은 모델이 *"나 = 배상규"*로 **매핑**해 본인 행을 고르게 하는 것이 목적이며, 데이터에 없는 휴가일수를 **창작하게 만드는 것이 아니다**(선행 작업의 "추측·창작 금지" 규칙 유지).

---

## 2. 현재 구조 분석 (Current State)

### 2-1. `analyze_with_claude` 진입 경로 2개

| # | 경로 | auth_ctx 가용성 | 근거 |
|---|------|----------------|------|
| ① | 단독 엑셀 분석: `analysis_router` → `AnalyzeExcelUseCase.execute()` → `ExcelAnalysisWorkflow.run()` | **없음**. 라우터는 `user_id` Form 문자열만 받고(`analysis_router.py:50`, 기본 `"anonymous"`), ContextVar도 미세팅 | `analysis_router.py:47-70`, `analyze_excel_use_case.py:42-91` |
| ② | Supervisor 재사용: `run_agent_use_case` → compiler `analysis_node` → `_run_excel_analysis()` → `ExcelAnalysisWorkflow.run()` | **있음(ContextVar)**. `run_agent_use_case.py:209`에서 `set_current_auth_context(auth_ctx)` 설정 후 그래프 실행 | `run_agent_use_case.py:176-291`, `workflow_compiler.py:552-630` |

> 즉, 경로 ②는 `get_current_auth_context()` 폴백만으로도 즉시 동작 가능하다. 경로 ①은 라우터가 auth_ctx를 조립해 명시적으로 넘겨야 한다.

### 2-2. Supervisor 비-엑셀 분석 분기도 동일 누락

`workflow_compiler.py:632 _analyze_context`(엑셀 없이 검색결과/대화문맥을 분석하는 분기)도 system prompt에 사용자 블록이 없다. 동일 증상이므로 함께 처리한다.

### 2-3. 재사용 가능한 기존 자산 (신규 구현 불필요)

| 자산 | 위치 | 역할 |
|------|------|------|
| `render_user_context_block(ctx)` | `application/agent_run/prompt_rendering.py` | 화이트리스트 블록 렌더(None/anonymous → `""`) |
| `get_current_auth_context()` | `application/agent_run/auth_context.py` | 현재 Task ContextVar 조회(폴백용) |
| `AuthContext` (frozen VO) | `domain/agent_run/auth_context.py` | 이름·대표부서·역할·권한 보유 |
| `AssembleAuthContextUseCase` | `application/permission/assemble_auth_context.py` | User → AuthContext 조립(경로 ① 라우터에서 필요 시) |

### 2-4. 제약 (CLAUDE.md)

- 아키텍처/레이어 이동 금지 → **그래프 구조·노드 추가 없음.** state 필드 1개 추가 + 프롬프트 조립부 수정으로 한정.
- "우선 명시적 시그니처를 선호한다 (Defense in Depth)"(`auth_context.py:25-26 주석`) → state 필드(명시) + ContextVar(폴백) 이중화.
- 화이트리스트 강제: 사번/이메일/user_id 노출 금지 → `render_user_context_block` 재사용으로 자동 충족.
- TDD 필수(RED→GREEN), config 하드코딩 금지, print 금지.

---

## 3. 수정 범위 (Scope)

| # | 위치 | 내용 | 레이어 | 우선순위 |
|---|------|------|--------|----------|
| 1 | `excel_analysis_workflow.py` `ExcelAnalysisState` | `user_context_block: str` 필드 추가(기본 `""`) | application | High |
| 2 | `excel_analysis_workflow.py` `_build_analysis_prompt` | 본문 맨 앞에 사용자 컨텍스트 블록 prepend | application | High |
| 3 | `excel_analysis_workflow.py` `_analyze_node` | 블록 결정: state 필드 우선 → 없으면 `render_user_context_block(get_current_auth_context())` 폴백 | application | High |
| 4 | `analyze_excel_use_case.py` `execute` | `auth_ctx: AuthContext \| None = None` 키워드 추가 → 초기 state에 렌더 결과 주입 | application | High |
| 5 | `analysis_router.py` | (경로 ①) auth 의존성으로 `AuthContext` 조립해 use_case에 전달 — 미인증이면 None 허용 | interfaces | Medium |
| 6 | `workflow_compiler.py` `_create_analysis_node` / `_run_excel_analysis` | 엑셀 분기 초기 state에 블록 주입(`auth_ctx` 클로저 캡처 또는 ContextVar) | application | High |
| 7 | `workflow_compiler.py` `_analyze_context` | 비-엑셀 분석 분기 system prompt에 블록 prepend | application | Medium |
| 8 | `tests/...` | 프롬프트 회귀 + 폴백 + 2경로 통합 테스트 (TDD) | - | High |

**범위 외 / 후속**:
- 프롬프트 렌더러 자체(`render_user_context_block`) 포맷 변경 — 기존 그대로 재사용.
- 권한 기반 도구 필터링 로직 — 이미 별도 구현(USE_RAG_SEARCH 등), 손대지 않음.
- 응답 스키마 불변 → `/api-contract-sync`/프론트 변경 **불필요**.
- 경로 ① 라우터의 인증 강제화(현재 익명 허용 엔드포인트) — Design에서 정책 결정(기본: 익명 허용 유지, ctx 있으면 사용).

---

## 4. 설계 (Solution Design)

### 4-1. 블록 결정 우선순위 (핵심)

```
_analyze_node:
  block = state.get("user_context_block")            # ① 명시적 주입 우선
  if not block:                                       # ② 폴백
      block = render_user_context_block(get_current_auth_context())
  prompt = _build_analysis_prompt(query, excel_data, web_context, user_block=block)
```

- 경로 ②(Supervisor)는 ContextVar가 이미 세팅돼 있어 폴백만으로 동작. 단, 일관성을 위해 §3-6에서 명시 주입도 함께 한다.
- None/anonymous → `render_user_context_block`이 `""` 반환 → 프롬프트에 군더더기 없이 기존과 동일(회귀 0).

### 4-2. 프롬프트 조립부 (제안 — Design 확정)

```python
def _build_analysis_prompt(self, query, excel_data, web_context, user_block=""):
    header = f"{user_block}" if user_block else ""   # user_block 끝에 이미 '---' 구분자 포함
    return f"""{header}당신은 데이터 분석 결과를 자연어 텍스트로만 작성하는 분석가입니다.
... (기존 본문 유지) ...
{ANALYSIS_OUTPUT_GUIDE}"""
```

> `render_user_context_block` 반환값은 끝에 `"\n---\n\n"` 구분자를 포함하므로 추가 개행 불필요. (`prompt_rendering.py:61`)

### 4-3. 경로 ① 명시 주입 (`AnalyzeExcelUseCase` + 라우터)

```python
# use_case.execute(...)
async def execute(self, excel_file_path, user_query, user_id,
                  request_id=None, *, auth_ctx: AuthContext | None = None):
    ...
    initial_state = {
        ...,
        "user_context_block": render_user_context_block(auth_ctx),
    }
```

- 라우터(`analysis_router`)는 인증 의존성으로 `User`를 받아 `AssembleAuthContextUseCase`로 `auth_ctx`를 조립해 전달. 미인증이면 `auth_ctx=None`(블록 `""`).
- DI placeholder(`get_analyze_excel_use_case`)와 인증 의존성 결합 방식은 Design에서 기존 의존성 패턴(`interfaces/dependencies/auth.py`) 따라 확정.

### 4-4. 경로 ② Supervisor (`workflow_compiler`)

- `_create_analysis_node`가 `auth_ctx`(또는 ContextVar)에서 블록을 만들어 `_run_excel_analysis`의 초기 state `user_context_block`에 주입.
- 엑셀 없는 분기 `_analyze_context`는 `analysis_prompt` 맨 앞에 동일 블록 prepend.
- 권장: 한 군데서 `block = render_user_context_block(get_current_auth_context())`로 구해 두 분기 공용 사용(ContextVar는 `run_agent_use_case.py:209`에서 이미 세팅됨).

### 4-5. 보안/화이트리스트

- `render_user_context_block`이 노출 필드를 **이름·대표부서·역할·권한 라벨**로 화이트리스트 고정 → 사번/이메일/숫자 user_id 누출 불가(`prompt_rendering.py:25-30` 주석 규약).
- 이번 작업은 렌더러를 **호출만** 하므로 새 노출 표면이 생기지 않는다.

---

## 5. 테스트 계획 (TDD)

### 5-1. 프롬프트 회귀 (application)
- `_build_analysis_prompt(q, data, "", user_block=BLOCK)` → 결과 문자열이 `BLOCK`으로 시작하고 "[현재 사용자 정보]"·"나", "내", "본인" 문구 포함.
- `user_block=""` → 기존 본문과 동일(블록 없음, 회귀 없음).

### 5-2. 폴백 동작 (application, ContextVar)
- ContextVar에 `AuthContext(이름=배상규, 부서=여신관리부)` 세팅 + state에 `user_context_block` 없음 → `_analyze_node`가 폴백으로 블록 주입.
- ContextVar None + state 없음 → 블록 `""`(anonymous 회귀 없음).
- state 필드와 ContextVar 동시 존재 → **state 필드 우선**.

### 5-3. 2경로 통합 (application, FakeClaude)
- 경로 ①: `AnalyzeExcelUseCase.execute(..., auth_ctx=배상규)` → FakeClaude에 전달된 프롬프트에 "배상규" 포함.
- 경로 ②: compiler `analysis_node` 실행(ContextVar=배상규, 엑셀 첨부) → `_run_excel_analysis` 초기 state에 블록 포함, FakeClaude 프롬프트에 "배상규" 포함.
- 경로 ② 비-엑셀(`_analyze_context`): system prompt에 블록 포함.

> 모든 신규/변경 RED→GREEN. Windows 이벤트 루프 플레이키는 격리 실행 검증(메모리 노트 참조).

---

## 6. 영향 범위 / 리스크

| 항목 | 영향 | 비고 |
|------|------|------|
| 분석 프롬프트 길이 | 사용자 블록만큼 소폭 증가 | 인증 시에만, 무시 가능 |
| 미인증/단독 익명 호출 | 블록 `""` → **기존 동작 그대로** | 회귀 0 |
| 그래프 구조 | **불변**(노드/엣지 추가 없음) | 회귀 위험 낮음 |
| 응답 스키마 | **불변** | 프론트 변경·`/api-contract-sync` 불필요 |
| 민감정보 | 화이트리스트 렌더러 재사용 | 사번/이메일/user_id 노출 없음 |
| 데이터 없는 휴가 질문 | 신원만 주입, 데이터 없으면 "데이터에 없음" | 선행 작업 추측 금지 규칙과 정합 |
| 경로 ① 라우터 인증 결합 | 의존성 배선 추가 | Design에서 기존 패턴 확정 |

---

## 7. 구현 순서

1. 프롬프트 회귀 테스트(RED) → `_build_analysis_prompt`에 `user_block` 파라미터 + prepend(GREEN) — 5-1
2. `ExcelAnalysisState`에 `user_context_block` 필드 추가 + `_analyze_node` 블록 결정(state 우선/ContextVar 폴백) + 폴백 테스트 — 5-2
3. `AnalyzeExcelUseCase.execute`에 `auth_ctx` 키워드 추가 + 초기 state 주입(경로 ①) + 통합 테스트 — 5-3
4. `analysis_router`에 인증 의존성 결합(미인증 None 허용)
5. `workflow_compiler` 엑셀/비-엑셀 분석 분기에 블록 주입(경로 ②) + 통합 테스트
6. 전체 테스트 격리 실행으로 그린 확인
7. `/pdca analyze analyze-user-context` (Gap 분석) → Report

---

## 8. 미해결 / 후속 이슈 (Design에서 확정)

- **state 필드 vs auth_ctx 객체 보유**: state에 렌더 완료 문자열(`user_context_block`)을 둘지, `AuthContext` 객체를 둘지. (권장: 문자열 — 워크플로우가 렌더 책임에서 자유로움)
- **경로 ① 라우터 인증 정책**: 현재 익명 허용 엔드포인트를 유지(ctx 있으면 사용)할지, 인증 필수화할지.
- **DI 배선**: `get_analyze_excel_use_case` placeholder와 `AssembleAuthContextUseCase` 결합 위치 — 기존 `interfaces/dependencies/auth.py` 패턴 준수.
- **공용화 범위**: supervisor 두 분기에서 블록 계산 로직을 헬퍼로 공용화할지.
