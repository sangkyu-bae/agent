# claude-agent-e2e-fixes Design Document

> **Summary**: 실 E2E 결함 5건을 Option C(실용 균형)로 고친다. 모델별 판정은 domain 정책 함수, 적용은 `LLMFactory`·수퍼바이저·사용량 콜백·엑셀 생성기 제자리에서 한다. 출력 한도는 `llm_model.max_output_tokens`(V092)로 관리한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: idt 0.1.x
> **Author**: 배상규
> **Date**: 2026-11-19
> **Status**: Draft
> **Planning Doc**: [claude-agent-e2e-fixes.plan.md](../../01-plan/features/claude-agent-e2e-fixes.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 실 E2E에서 최신 Claude 에이전트가 라우팅 400·빈 답·반복 루프로 동작하지 않았고, 엑셀 집계 빈칸과 비용 추적 0이 조용히 감춰졌다 |
| **WHO** | P2(에이전트 소유자) — 관리자가 등록한 모델로 에이전트를 만들고 결과물(엑셀 등)을 받는 사용자, 그리고 사용량·비용을 보는 관리자 |
| **RISK** | json_schema 전환 시 Anthropic 스키마 제약 위반(41개 호출 지점), 큰 출력 한도의 SDK 비스트리밍 거부, 연속 호출 상한이 정상 재호출을 막음, V092 운영 적용 순서 |
| **SUCCESS** | 같은 E2E 시나리오(Opus 5.5, data_analysis + excel_export)가 끝까지 성공하고 엑셀 값이 원천 직접 계산과 일치, 평균 금리 채워짐, 반복 호출이 상한에서 멈춤, ai_llm_call에 모델명·입출력 토큰 기록 |
| **SCOPE** | 5개 모듈: M1 퍼센트·빈 컬럼 / M2 출력 한도(DB·API·관리자 화면·팩토리) / M3 구조화 출력 / M4 반복 루프 / M5 비용 추적. PR 1개 |

---

## 1. Overview

### 1.1 Design Goals

- 관리자가 고른 모델(최신 Claude 포함)로 만든 에이전트가 끝까지 동작한다.
- 모델별 차이는 domain 정책 함수 한 곳에서 판정하고, 호출 지점(구조화 출력 41곳 등)은 고치지 않는다.
- 구형 모델·OpenAI·Ollama의 요청 payload는 바뀌지 않는다(출력 한도를 저장하지 않은 경우).
- 실패를 감추던 경로(빈 집계, 반복, 비용 0)를 드러내거나 멈춘다.

### 1.2 Design Principles

- **판정은 domain, 적용은 제자리**: 이름 → 능력 판정은 순수 함수, 적용은 기존 클래스 안에서.
- **모르는 신형은 보수적으로**: 이름 형식을 모르는 모델은 "temperature 미전송·강제 tool 호출 미사용"으로 본다. 실측상 json_schema는 구형(sonnet-4-6)에서도 동작하므로 안전한 쪽이다.
- **기본값 = 무영향**: 새 인자(`max_consecutive_worker_calls=0` 등)는 기본값에서 기존 동작과 바이트 동일.

### 1.3 Plan 대비 변경 (Design 조사 결과)

| Plan 항목 | Design 결정 | 근거 (2026-11-19 실호출) |
|-----------|-------------|-------------------------|
| FR-07 Anthropic 요청 타임아웃 명시 | **삭제** | langchain-anthropic 1.6.1 + anthropic 0.125에서 `claude-opus-5-5`에 `max_tokens` 64000·128000을 타임아웃 없이 보내도 정상 응답(`end_turn`). Plan이 가정한 SDK 비스트리밍 거부가 이 조합에서 발생하지 않음. 범위 검증(≤128000)만 유지 |
| 환경변수 `ANTHROPIC_REQUEST_TIMEOUT_SECONDS` | 삭제 | 위와 같음 |
| M5 "추정 원인" | **확정** | 스트리밍 `on_llm_end`: `llm_output=None`, `invocation_params` 빈 dict, 메시지 `response_metadata={"model_name": "claude-sonnet-4-6", ...}`, `usage_metadata`에 `input_tokens`/`output_tokens` |
| M3 json_schema 동작 | **확인** | Opus 5.5: `function_calling` 400, `json_schema` 정상(Literal·Optional·`ge/le`·list 스키마). Sonnet 4.6도 json_schema 정상 |

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 판정 로직을 팩토리·수퍼바이저에 인라인 | `LlmCapabilities` VO·반복 감지 정책 클래스·사용량 추출기 클래스 | 기존 domain 정책 파일에 함수 추가, 반복 상한은 순수 함수 + 상태 키 + 안내 블록 |
| **New Files (BE)** | 1 | 6 | 3 |
| **Modified Files (BE)** | 14 | 15 | 15 |
| **Complexity** | Low | High | Medium |
| **Risk** | 모델 규칙이 infrastructure에 섞임 | 구현체 1개에 추상화 과다 | Low |

**Selected**: Option C — 사용자 확정. 모델 판정은 이미 `domain/llm/sampling_policy.py`(PR #118)에 있어 같은 자리에 함수를 더하는 것이 자연스럽다.

### 2.1 Component Diagram

```
관리자 화면 ── PATCH/POST /api/v1/llm-models (max_output_tokens) ── LlmModel(V092)
                                                                      │
LlmModel ──▶ LLMFactory.create ──┬─ anthropic_accepts_temperature        (domain, 기존)
                                 ├─ resolve_max_output_tokens            (domain, 신규) ─▶ max_tokens
                                 └─ anthropic_supports_forced_tool_choice (domain, 신규)
                                      └ False ▶ JsonSchemaStructuredChatAnthropic (infra, 신규 하위 클래스)
                                                   with_structured_output(method 기본 json_schema)
PiiGuardedLLMFactory / GuardedLlm ── with_structured_output 위임 (무변경)
UtilityLLMProvider 캐시 dict ── max_output_tokens 직렬화/복원(.get)

supervisor_node ── worker_repeat_policy (domain, 신규) ── state.repeat_worker_id/count
                   ├─ 안내 블록 "repeat" (_select_guidance_block)
                   └─ 상한 초과 재선택 → "__end__" (final_answer)

UsageCallback._extract_model / _extract_tokens ── 메시지 response_metadata / usage_metadata 폴백, 키 기반 정규화

ops_executor ── clean_numeric_text(% → 비율)  ExcelGenerator ── empty_columns ──▶ _render_excel_summary 경고
```

### 2.2 Data Flow (E2E 시나리오 기준)

```
Opus 5.5 에이전트 실행
 → supervisor: with_structured_output(SupervisorDecision) = json_schema   (M3, 400 해소)
 → data_analysis: utility LLM max_tokens = 16000(NULL 기본) → text 포함   (M2)
 → supervisor: 분석 2회 연속 후 안내 블록 → excel_export 선택 or 종료     (M4)
 → excel_export: ops groupby mean("8.9%") = 0.0747 → 0.0% 서식           (M1)
 → 모든 LLM 호출 ai_llm_call: provider=anthropic, model_name, 입출력 토큰  (M5)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `LLMFactory` | `sampling_policy`, `settings.anthropic_default_max_output_tokens` | 출력 한도·구조화 방식 |
| `JsonSchemaStructuredChatAnthropic` | `langchain_anthropic.ChatAnthropic` | 기본 method 교체 |
| `supervisor_nodes` | `worker_repeat_policy` | 연속 호출 판정 |
| `WorkflowCompiler` | `settings.supervisor_max_consecutive_worker_calls`(main.py 주입) | 상한 전달 |
| `UsageCallback` | — | 추출 로직만 변경 |

---

## 3. Data Model

### 3.1 DB — V092

```sql
-- claude-agent-e2e-fixes M2 (V092): 출력 한도(응답 max_tokens). 기존 max_tokens는 컨텍스트 크기.
-- NULL이면 provider 기본(Anthropic은 설정 기본값, 그 외 미전달).
-- ⚠️ COMMENT 안에 콤마 금지 — tests/db/test_migration_ddl_comments.py 파서 제약.
ALTER TABLE llm_model
  ADD COLUMN max_output_tokens INT NULL
  COMMENT '응답 최대 출력 토큰 수 — NULL이면 provider 기본값 사용 (Anthropic은 서버 설정 기본값)'
  AFTER max_tokens;
```

- SQLAlchemy `models.py`: `max_output_tokens = Column(Integer, nullable=True, comment=...)` (DDL과 같은 문구)
- 번호: 작업 시작 시 master 최신 V091 확인. PR 직전 재확인.

### 3.2 Domain / API

| 위치 | 변경 |
|------|------|
| `domain/llm_model/entity.py` `LlmModel` | `max_output_tokens: int \| None = None` (기본값 있는 필드 끝에 추가 — 기존 생성자 호출 무변경) |
| `infrastructure/llm_model/llm_model_repository.py` | to/from ORM 매핑, update 반영 |
| `application/llm_model/schemas.py` | `CreateLlmModelRequest`·`UpdateLlmModelRequest`: `max_output_tokens: int \| None = Field(None, ge=1, le=MAX_OUTPUT_TOKENS_LIMIT)`, `LlmModelResponse`: `max_output_tokens: int \| None` |
| create/update use case | 필드 전달 |
| `application/llm_model/utility_llm_provider.py` | 캐시 dict에 `max_output_tokens` 저장, 복원은 `data.get("max_output_tokens")`(구 캐시 항목 호환) |
| `infrastructure/llm_model/seed.py` | 변경 없음(NULL) |

`MAX_OUTPUT_TOKENS_LIMIT = 128000`은 domain 상수(`domain/llm/sampling_policy.py`).

### 3.3 Frontend

| 위치 | 변경 |
|------|------|
| `idt_front/src/types/llmModel.ts` | `LlmModel.max_output_tokens: number \| null`, Create/Update 요청 `max_output_tokens?: number \| null` |
| `pages/AdminLlmModelsPage/index.tsx` | 폼 필드 `max_output_tokens`(문자열 상태 → 숫자/ null), 라벨 "최대 출력 토큰", 도움말 "비우면 기본값(Anthropic 16000)", 1~128000 정수 검증 문구. 기존 `max_tokens` 라벨을 "컨텍스트 크기(최대 토큰)"로 |
| 목록 표시 | 출력 한도 열 또는 상세에 표시(값 없으면 "기본") |

서비스·훅은 요청 본문을 그대로 넘기므로 타입만 바뀐다(구현 시 확인).

### 3.4 Supervisor State

```python
# supervisor_state.py — 선택 키 (build_initial_state 초기화)
repeat_worker_id: str      # 수퍼바이저가 마지막으로 라우팅한 워커
repeat_worker_count: int   # 그 워커로 연속 라우팅한 횟수
```

### 3.5 Excel Result

```python
# domain/excel_generator/schemas.py ExcelGenerateResult
empty_columns: tuple[str, ...] = ()   # "시트명/컬럼명" — 행이 있는데 값이 전부 빈 컬럼
```

---

## 4. Domain Policies

### 4.1 `domain/llm/sampling_policy.py` (기존 파일에 추가)

```python
MAX_OUTPUT_TOKENS_LIMIT = 128000

def anthropic_supports_forced_tool_choice(model_name: str) -> bool:
    """tool_choice {type: tool|any} 를 받는 모델인가."""

def resolve_max_output_tokens(provider: str, stored: int | None, anthropic_default: int) -> int | None:
    """저장값 우선. 없으면 anthropic만 기본값, 그 외 None(미전달)."""
```

`anthropic_supports_forced_tool_choice` 판정표 (Claude API 문서 기준, 2026-11):

| 이름 형식 | 결과 |
|-----------|------|
| `claude-3-*`, `claude-3.*` | True |
| `claude-(opus\|sonnet)-<major>[-<minor>][-yyyymmdd]`: 버전 < 5.5 | True (4.x, `claude-opus-5`, `claude-sonnet-5`) |
| 같은 형식, 버전 ≥ 5.5 | False (`claude-opus-5-5`, `claude-sonnet-5-5`) |
| `claude-haiku-*`: 버전 ≤ 5.5 | True |
| `claude-(fable\|mythos)-<major>[-<minor>]`: 버전 < 5.1 | True (`claude-fable-5`) |
| 같은 형식, 버전 ≥ 5.1 | False |
| 그 외(모르는 형식, 접두사 붙은 이름, 빈 값) | False |

### 4.2 `domain/agent_builder/worker_repeat_policy.py` (신규)

```python
def next_repeat_state(prev_worker: str, prev_count: int, routed_worker: str) -> tuple[str, int]:
    """라우팅 후 (repeat_worker_id, repeat_worker_count). 종료(__end__/"")는 ("", 0)."""

def repeat_exhausted(worker: str, repeat_worker: str, count: int, limit: int) -> bool:
    """limit>0 이고 worker == repeat_worker 이고 count >= limit."""
```

### 4.3 `domain/excel_generator/spec_policies.py`

- `clean_numeric_text`: 정리 후 `%`로 끝나면 숫자부 / 100. `"8.9%"`→0.089, `"-5%"`→-0.05, `"%"`→None.
- `_to_percent`(coerce_cell percent)는 이제 `clean_numeric_text`와 결과가 같으므로 `clean_numeric_text`를 그대로 쓰도록 단순화.
- 영향: 크기 비교 value `"5%"` → 0.05. 숫자 타입 value `5`는 그대로 5(셀 0.089와 비교) — 프롬프트 규칙에 "퍼센트 컬럼 조건은 '5%'처럼 % 를 붙여라" 한 줄 추가.

---

## 5. Component Design

### 5.1 M2·M3 — `LLMFactory._create_anthropic`

```python
def _create_anthropic(self, llm_model, temperature):
    kwargs = dict(model=..., api_key=...)
    if anthropic_accepts_temperature(llm_model.model_name):
        kwargs["temperature"] = temperature
    max_out = resolve_max_output_tokens("anthropic", llm_model.max_output_tokens,
                                        self._anthropic_default_max_output_tokens)
    kwargs["max_tokens"] = max_out
    cls = ChatAnthropic if anthropic_supports_forced_tool_choice(llm_model.model_name) \
        else JsonSchemaStructuredChatAnthropic
    return cls(**kwargs)
```

- `LLMFactory.__init__(anthropic_default_max_output_tokens: int = 16000)` — main.py에서 `settings.anthropic_default_max_output_tokens` 주입. 기존 `LLMFactory()` 호출(테스트·스크립트)은 기본값으로 동작.
- OpenAI·Ollama: `max_output_tokens`가 저장돼 있으면 각각 `max_tokens`·`num_predict`로 전달, 없으면 무변경.
- 구형 Anthropic 모델에도 `max_tokens`를 명시하게 된다(기존엔 langchain 모델별 기본). sonnet-4-6 기본 128000 → 16000으로 낮아짐 — 아래 §9 위험.

### 5.2 M3 — `infrastructure/llm/structured_chat_anthropic.py` (신규)

```python
class JsonSchemaStructuredChatAnthropic(ChatAnthropic):
    """강제 tool_choice를 거부하는 모델용 — with_structured_output 기본 method를 json_schema로.

    호출부가 method를 명시하면 존중한다. 그 외 동작은 ChatAnthropic과 같다.
    """
    def with_structured_output(self, schema, *, include_raw=False, method="json_schema", **kwargs):
        return super().with_structured_output(schema, include_raw=include_raw, method=method, **kwargs)
```

- `GuardedLlm.with_structured_output`은 `self._inner.with_structured_output(...)`로 위임하므로 무변경으로 적용된다(FR-10) — 테스트로 고정.
- 계약 테스트(PII 경계 `ALLOWED_DIRECT_CONSTRUCTION`): 새 파일은 `ChatAnthropic(`을 직접 호출하지 않으므로 목록 변경 없음. `llm_factory.py`의 생성 호출 수 변화는 구현 후 맞춘다.

### 5.3 M3 — 스키마 정적 검사 (FR-11)

- `tests/contracts/test_structured_output_schemas_anthropic.py`: src를 AST로 훑어 `with_structured_output(<Name>)`의 Pydantic 클래스를 import해 `model_json_schema()`를 얻고, Anthropic 구조화 출력이 거부하는 패턴을 찾는다.
  - 자유 키 dict(`additionalProperties`가 스키마) — 기존 위키 패턴 재사용
  - 루트가 object가 아닌 스키마
- 대표 스키마 실호출 프로브(수퍼바이저 `SupervisorDecision`, 검색 판단, 환각 판정)는 E2E 스크립트에서 확인.
- 위반 발견 시: 그 스키마만 LLM 전용 Draft로 분리(이번 범위) 또는 예외 목록+사유(Design 갱신).

### 5.4 M4 — 수퍼바이저

`create_supervisor_node(..., max_consecutive_worker_calls: int = 0)` — 0이면 비활성(바이트 동일).

1. **안내 블록**: `_select_guidance_block`에 종류 `"repeat"` 추가. 우선순위: 오류 > **반복** > 빈 결과 > 능력 부정 > 재진입. `repeat_exhausted(state.last_worker_id, repeat_worker_id, count, limit)`일 때:
   ```
   [반복 호출 주의]
   - {worker}를 방금 {count}회 연속 수행했습니다. 같은 워커를 다시 호출해도 결과가 달라지지 않을 가능성이 큽니다.
   - 지금까지 결과로 다음 단계(다른 워커)로 넘어가거나, 충분하면 FINISH하세요.
   - 같은 워커를 다시 고르면 지금까지 결과로 최종 답변을 작성합니다.
   ```
2. **강제 종료**: LLM 결정 후 `repeat_exhausted(next_worker, ...)`이면 `next_worker="__end__"`, `logger.warning("worker repeat limit reached", worker=..., count=...)`, `_step_output_summary`에 `[반복 상한] {worker} {count}회 연속 — 최종 답변으로 종료` 접두. `limit_reached`·`limit_reason`은 세우지 않는다(프론트 payload 무변경, final_answer가 수집 결과로 답변).
3. **상태 갱신**: 워커로 라우팅하는 모든 return(LLM 결정·강제 라우팅 `hooks.force_worker`)에서 `next_repeat_state`로 갱신. 종료 return은 ("", 0).
4. 강제 라우팅 경로는 상한 검사 대상이 아니다(결정적 규칙이 고른 것).
5. `WorkflowCompiler.__init__(…, max_consecutive_worker_calls: int = 0)` → `create_supervisor_node`에 전달. main.py가 `settings.supervisor_max_consecutive_worker_calls`(기본 2)를 주입.

### 5.5 M5 — `UsageCallback`

```python
def _extract_model(self, response, kwargs):
    llm_output = response.llm_output or {}
    model_name = (llm_output.get("model_name") or llm_output.get("model")
                  or self._model_from_generations(response)            # 신규: message.response_metadata
                  or kwargs.get("invocation_params", {}).get("model")
                  or self._start_models.pop(run_id, None)              # 신규: on_chat_model_start 기록
                  or "unknown")

def _normalize_to_token_usage(self, usage, provider):
    # 키 기반: input_tokens/output_tokens 가 있으면 그것, prompt_tokens/... 면 그것, Ollama 키면 그것
```

- `on_chat_model_start`/`on_llm_start`에서 `invocation_params["model"]`을 `run_id`별로 기록해 두고 end에서 꺼낸다(이미 `_start_ts`로 latency를 같은 방식으로 관리).
- provider 추론은 기존 `_infer_provider(model_name)` 그대로(모델명이 나오면 `claude-` → anthropic).

### 5.6 M1 — 엑셀 생성기

- `ExcelGenerator._materialize` 이후 `_empty_columns(sheets)`: 행 ≥1인 시트에서 모든 값이 `None`/빈 문자열인 컬럼 → `"시트/컬럼"`.
- 완료 로그에 `empty_columns`, 결과에 담기.
- `workflow_compiler._render_excel_summary`: 비어 있지 않으면 `⚠️ 다음 컬럼은 원천 값으로 계산할 수 없어 비어 있습니다: …` 줄 추가 → final_answer가 이 사실을 받는다.
- 계획 프롬프트 규칙 3에 "퍼센트 컬럼 조건은 '5%'처럼 %를 붙여라" 추가.

---

## 6. Error Handling

| # | 상황 | 처리 |
|---|------|------|
| 1 | 관리자가 `max_output_tokens` 0·음수·128000 초과 | API 422 (Pydantic), 프론트 사전 검증 문구 |
| 2 | json_schema 구조화 출력이 스키마 제약으로 400 | 기존 호출부 예외 처리 그대로(수퍼바이저는 `__end__`). 정적 검사로 사전 차단 |
| 3 | 반복 상한 초과 재선택 | `__end__` + warning 로그 + 단계 요약 접두 |
| 4 | 사용량 추출 실패(모델명 못 찾음) | 기존처럼 `unknown` + resolver warning (악화 없음) |
| 5 | 구 캐시 항목(필드 없음) | `.get` → None → 기본값 경로 |
| 6 | 집계 결과 전부 빈 컬럼 | 실패 아님 — 경고만 |

---

## 7. Security Considerations

- [x] 새 API 필드는 관리자 전용 기존 엔드포인트(권한 무변경)
- [x] PII 경계: 새 생성 지점 없음(하위 클래스는 팩토리 안에서만 생성) — 경계 계약 테스트 유지
- [x] 입력 검증: 출력 한도 범위(ge=1, le=128000)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit (domain) | `sampling_policy` 신규 함수, `worker_repeat_policy`, `clean_numeric_text` % | pytest |
| Unit (infra/app) | `LLMFactory` payload, 하위 클래스 method, GuardedLlm 위임, `UsageCallback`, 수퍼바이저 노드, 엑셀 생성기·요약, llm_model 스키마·리포지토리·유스케이스·유틸리티 캐시 | pytest |
| Contract | 구조화 출력 스키마 Anthropic 제약 정적 검사, PII 경계·응답 정규화 기존 계약 | pytest(AST) |
| DB | V092 COMMENT | `tests/db/test_migration_ddl_comments.py` |
| FE | 관리자 모델 폼 입력·검증·요청 본문, 타입 | vitest + RTL + MSW |
| E2E | Opus 5.5 에이전트 엑셀 보고서 | `idt/scripts/e2e_claude_excel_report.py`(수동) |

### 8.2 Domain 테스트

| # | 케이스 | 기대 |
|---|--------|------|
| D1 | forced tool: `claude-sonnet-4-6`, `claude-opus-4-8`, `claude-opus-5`, `claude-haiku-5-5`, `claude-fable-5`, `claude-3-5-sonnet-20241022` | True |
| D2 | forced tool: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-fable-5-1`, `claude-fable-5-2`, `claude-mythos-5-2`, `claude-opus-6`, `anthropic.claude-opus-5-5`, `""` | False |
| D3 | `resolve_max_output_tokens("anthropic", None, 16000)` | 16000 |
| D4 | `resolve_max_output_tokens("anthropic", 64000, 16000)`, `("openai", 2000, 16000)` | 64000, 2000 |
| D5 | `resolve_max_output_tokens("openai", None, 16000)`, `("ollama", None, …)` | None |
| D6 | `next_repeat_state("a", 1, "a")` / `("a", 2, "b")` / `("a", 2, "__end__")` | ("a",2) / ("b",1) / ("",0) |
| D7 | `repeat_exhausted("a","a",2,2)` / `("a","a",1,2)` / `("b","a",5,2)` / `("a","a",9,0)` | True / False / False / False |
| D8 | `clean_numeric_text("8.9%")`, `"-5%"`, `"1,234.5%"`, `"%"` | 0.089 / -0.05 / 12.345 / None |
| D9 | `coerce_cell("12.5%","percent")` 기존 결과 유지 | 0.125 |

### 8.3 Infra / Application 테스트

| # | 케이스 | 기대 |
|---|--------|------|
| F1 | Opus 5.5 모델 생성 → 타입 `JsonSchemaStructuredChatAnthropic`, payload `max_tokens=16000`, temperature 없음 | 일치 |
| F2 | sonnet-4-6 → `ChatAnthropic`, `max_tokens=16000`(기본), temperature 있음 | 일치 |
| F3 | `max_output_tokens=64000` 저장 → payload 64000 | 일치 |
| F4 | OpenAI 저장값 없음 → payload에 max_tokens 없음 / 저장 2000 → 2000 | 일치 |
| F5 | 하위 클래스 `with_structured_output(S)`이 `method="json_schema"`로 부모 호출, 명시 method 존중 | 패치로 확인 |
| F6 | `GuardedLlm(inner=하위 클래스).with_structured_output` → 안쪽 json_schema | 확인 |
| U1 | 스트리밍 형태 LLMResult(llm_output None, 메시지 response_metadata model_name, usage input/output) → provider anthropic, 토큰 분리 | 일치 |
| U2 | OpenAI 형태(llm_output token_usage) 기존 결과 무변경 | 일치 |
| U3 | 모델명이 start 기록에만 있는 경우 | start 값 사용 |
| S1 | limit=0 → 프롬프트·상태 키 외 결과 기존과 동일 | 무회귀 |
| S2 | limit=2, 같은 워커 2회 연속 후 결정 프롬프트에 반복 안내 | 포함 |
| S3 | 그 상태에서 LLM이 같은 워커 선택 → `__end__`, warning, 단계 요약 접두 | 일치 |
| S4 | 다른 워커 선택 → 정상 라우팅, 카운터 ("b",1) | 일치 |
| S5 | 오류 블록이 있으면 반복 블록보다 오류 우선 | 우선순위 |
| E1 | groupby mean on `"8.9%"` 컬럼 → 비율 평균 | pandas 기준값/100 |
| E2 | 행 있는데 값 전부 None 컬럼 → `empty_columns` + 요약 경고 문구 | 포함 |
| L1 | llm_model 생성·수정·응답 `max_output_tokens` 왕복, 범위 밖 422 | 일치 |
| L2 | 리포지토리 ORM 매핑, 유틸리티 캐시 직렬화·구 항목 복원 | 일치 |

### 8.4 Frontend

| # | 케이스 | 기대 |
|---|--------|------|
| FE1 | 편집 폼에 기존 값 표시, 비우면 요청 본문 `max_output_tokens: null` | 일치 |
| FE2 | 0·음수·128001 입력 시 오류 문구, 요청 안 보냄 | 일치 |
| FE3 | 라벨 "컨텍스트 크기"·"최대 출력 토큰" 노출 | 일치 |

### 8.5 E2E (SC-1·2·5·6)

`idt/scripts/e2e_claude_excel_report.py` — 2026-11-19 scratchpad 스크립트 정리판:
- 결정적 입력 생성(600행, seed) + 기대값 계산
- 인프로세스 `TestClient`, 모델·유틸리티·근거 판정 모델 env 덮어쓰기, `max_iterations=10`
- `[L3]` 에이전트 생성 → 실행 → 산출 xlsx 다운로드 → 검증 리포트 → 에이전트 soft delete(try/finally)
- 실행 run의 `ai_llm_call` 조회로 SC-6 확인
- 커밋하되 pytest 수집 대상 아님(스크립트), 비용 경고를 docstring에 명시

---

## 9. Risks (Design 단계 추가)

| Risk | Mitigation |
|------|------------|
| sonnet-4-6 등 구형 Anthropic의 출력 한도가 langchain 기본(128000/64000)에서 16000으로 낮아짐 → 긴 답이 잘릴 수 있음 | 관리자가 모델별 `max_output_tokens`로 올릴 수 있음(이 기능의 목적). 릴리스 노트에 명시. 대안(기본값 보정만)은 사용자가 컬럼 방식을 선택하며 기각 |
| 하위 클래스가 langchain-anthropic 버전 업 시 `with_structured_output` 시그니처 변경에 깨짐 | 시그니처는 `*args/**kwargs`를 그대로 넘기고 `method`만 기본값 교체. 테스트 F5로 고정 |
| 반복 안내가 정상 흐름(같은 워커를 다른 입력으로 2회)을 막음 | 기본 2는 "2회까지 허용, 3번째 연속에서 종료". 설정으로 조정·0이면 비활성 |

---

## 10. Clean Architecture — Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| 모델 능력 판정·출력 한도 해석 | Domain | `src/domain/llm/sampling_policy.py` |
| 반복 상한 판정 | Domain | `src/domain/agent_builder/worker_repeat_policy.py` (신규) |
| 퍼센트 해석 | Domain | `src/domain/excel_generator/spec_policies.py` |
| 하위 클래스 | Infrastructure | `src/infrastructure/llm/structured_chat_anthropic.py` (신규) |
| 팩토리·콜백 | Infrastructure | `llm_factory.py`, `usage_callback.py` |
| 수퍼바이저 | Application | `supervisor_nodes.py`, `supervisor_state.py`, `workflow_compiler.py` |
| llm_model | Domain/Infra/Application | entity, models, repository, schemas, use cases, utility provider |
| DI·설정 | Interfaces/Config | `api/main.py`, `config.py` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/db/migration/V092__add_max_output_tokens_to_llm_model.sql          (신규)
idt/src/domain/llm/sampling_policy.py                                   (수정)
idt/src/domain/agent_builder/worker_repeat_policy.py                    (신규)
idt/src/domain/excel_generator/{spec_policies,schemas}.py               (수정)
idt/src/domain/llm_model/entity.py                                      (수정)
idt/src/infrastructure/llm/structured_chat_anthropic.py                 (신규)
idt/src/infrastructure/llm/{llm_factory,usage_callback}.py              (수정)
idt/src/infrastructure/llm_model/{models,llm_model_repository}.py       (수정)
idt/src/infrastructure/excel_generator/generator.py                     (수정)
idt/src/application/llm_model/{schemas,create_*,update_*,utility_llm_provider}.py (수정)
idt/src/application/agent_builder/{supervisor_nodes,supervisor_state,workflow_compiler}.py (수정)
idt/src/config.py, idt/src/api/main.py                                  (수정)
idt/scripts/e2e_claude_excel_report.py                                  (신규)
idt_front/src/types/llmModel.ts, pages/AdminLlmModelsPage/index.tsx (+test) (수정)
tests: domain·infra·application·contracts 신규/보강
```

### 11.2 Implementation Order

1. M1 퍼센트·빈 컬럼 (작고 독립)
2. M5 사용량 콜백 (독립, 비용 기록 정확도 먼저)
3. M3 구조화 출력 (정책 + 하위 클래스 + 팩토리 분기 + 스키마 검사)
4. M2 백엔드 (V092 → 엔티티·ORM·리포지토리·스키마·유스케이스·캐시 → 팩토리 출력 한도)
5. M2 프론트 (타입 → 관리자 화면 + 테스트) — `/api-contract-sync`
6. M4 수퍼바이저 반복 상한
7. E2E 스크립트 → Opus 5.5 실행 → 회귀

### 11.3 Session Guide

| Module | Scope Key | Description | Turns |
|--------|-----------|-------------|:-----:|
| 퍼센트·빈 컬럼 | `module-1` | spec_policies %, generator empty_columns, 요약 경고, 프롬프트 1줄 | 10-15 |
| 비용 추적 | `module-2` | UsageCallback 모델명·토큰 추출 | 10-15 |
| 구조화 출력 | `module-3` | 정책 함수, 하위 클래스, 팩토리 분기, 스키마 정적 검사 | 20-25 |
| 출력 한도 BE | `module-4` | V092, llm_model 스택, 캐시, 팩토리 max_tokens | 20-25 |
| 출력 한도 FE | `module-5` | 타입, 관리자 화면, vitest | 15-20 |
| 반복 상한 | `module-6` | 정책, 상태, 안내 블록, 종료, 컴파일러·DI | 20-25 |
| E2E | `module-7` | 스크립트, Opus 5.5 실행, 회귀 | 15-20 |

| Session | Scope |
|---------|-------|
| 1 | Plan + Design (완료) |
| 2 | `--scope module-1,module-2,module-3` |
| 3 | `--scope module-4,module-5` |
| 4 | `--scope module-6,module-7` |
| 5 | Check + Report |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-19 | Initial draft — Option C, FR-07 삭제(실호출 근거), M5 원인 확정 | 배상규 |
