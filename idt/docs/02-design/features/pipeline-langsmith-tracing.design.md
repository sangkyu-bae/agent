# Design — pipeline-langsmith-tracing

> Feature: `pipeline-langsmith-tracing`
> Created: 2026-09-20
> Phase: design
> Plan: `docs/01-plan/features/pipeline-langsmith-tracing.plan.md`
> 선택 아키텍처: **Option C-2 — contextvar 기반 단계 스코프 추적**

---

## Context Anchor

| 축 | 내용 |
|---|---|
| **WHY** | 파이프라인 LLM 호출 3곳이 전부 무추적. 실패해도 `degraded` 플래그 하나 외에 근거가 남지 않는다. |
| **WHO** | P2(KB 운영자/에이전트 소유자) — 생성 실패 원인을 스스로 규명해야 하는 주체. 2차로 백엔드 개발자. |
| **RISK** | 전역 `os.environ` 변경(기존 3곳)이 파이프라인 run을 엉뚱한 프로젝트로 흘려보내고 있을 수 있다. 수정 시 기존 3경로의 추적이 깨지면 안 된다. |
| **SUCCESS** | 파이프라인 5단계 run이 전용 프로젝트에 단계별로 분리 기록되고, 기존 4개 추적 경로가 회귀 없이 동작한다. |
| **SCOPE** | 파이프라인 관측성만. 프롬프트 생성 **품질** 개선은 [[prompt-fallback-visibility]]가 담당한다. |

---

## 1. Overview

### 1-1. 설계 결정 요약

| # | 결정 | 근거 |
|---|---|---|
| D1 | **Option C-2** — `langchain_core.tracers.context.tracing_v2_enabled` contextvar로 단계 스코프 추적 | 시그니처 무변경. domain Port 오염 회피 |
| D2 | 외부 전송은 **API 키 유무로만 제어** (별도 킬스위치 없음) | 기존 `_make_project_tracer` 계약 승계(`langsmith.py:70-71`) |
| D3 | 전역 `os.environ` 오염 제거를 **이번 범위에 포함** (3곳 전부) | 제거 전까지 파이프라인 run이 다른 프로젝트로 섞인다 |
| D4 | 추적 컨텍스트는 **`yield`를 가로지르지 않는다** | contextvar × async generator 상호작용 회피 (§7-2) |
| D5 | 프로젝트명 상수는 `langsmith.py` **단일 출처** | CLAUDE.md §3 |

### 1-2. Option C-1을 버린 이유 (기록)

Plan §7-1의 Option C는 `trace` dict를 호출 인자로 내려보내는 안이었다. Design 단계에서 실제 호출 체인을 추적한 결과 **domain Port 3개의 시그니처를 바꿔야 함**이 드러났다:

| Port | 파일 | 계층 |
|---|---|---|
| `PromptGeneratorPort.generate()` | `src/domain/prompt_composer/interfaces.py:22` | domain |
| `IntentAnalyzerInterface.analyze()` | `src/domain/intent/interfaces.py:25` | domain |
| `ToolSelectorPort.select()` | `src/domain/tool_selection/interfaces/tool_selector_port.py:16` | domain |

`trace`의 실체는 LangChain `RunnableConfig` dict다. CLAUDE.md §2가 domain의 LangChain 사용을 금지하므로 **관측성 하나를 위해 도메인 순수성을 깨는 거래**가 된다. C-2는 같은 목적을 시그니처 변경 0건으로 달성한다.

### 1-3. 실측 검증 (Design 단계에서 수행)

`langchain_core 1.6.0` 환경에서 직접 확인:

| 검증 항목 | 결과 |
|---|---|
| `tracing_v2_enabled(project_name, tags)` 존재 | ✅ `Generator[LangChainTracer, None, None]` 반환 |
| API 키 없이 진입 | ✅ 예외 없이 진입/이탈. `LangChainTracer`가 생성되고 contextvar가 세팅됨 |
| `await` 직접 호출로 전파 | ✅ |
| `asyncio.create_task()` 안으로 전파 | ✅ |

> ⚠️ **키 없이도 진입이 되고 tracer가 생성된다**는 점이 중요하다. 그대로 쓰면 키 없는 환경에서 전송을 시도한다. 따라서 **D2를 만족하려면 진입 전 키 가드가 필수**다 (§3-1 FR-01).

---

## 2. 현황 재확인 (Plan §1 요약)

### 2-1. 배선 0건

| 파일 | 검색 결과 |
|---|---|
| `src/api/routes/agent_pipeline_router.py` | `trace`/`langsmith`/`callbacks`/`run_name` — 0건 |
| `src/application/agent_create_pipeline/use_case.py` | 0건 |
| `src/infrastructure/agent_create_pipeline/adapters.py` | 0건 |

### 2-2. 협력자 소유 관계 — 이 설계의 핵심 제약

| 단계 | 인스턴스 | 공유 여부 |
|---|---|---|
| `intent` | `main.py:5203` `_intent_use_case` | ⚠️ **공유** — `intent_router.py`와 파이프라인이 같은 싱글턴 (`main.py:5241`) |
| `prompt` | `_prompt_f` (`ComposePromptUseCase`) | ⚠️ **공유** — `prompt_composer_router.py`와 공용 |
| `tools` | `main.py:2595` | ✅ **전용** (일반 채팅용 `:2562`과 별도) |

**어댑터 내부에서 tracer를 만들면 독립 라우터 호출까지 파이프라인으로 오분류된다.** 호출 스코프에서 켜는 C-2가 이 문제를 구조적으로 해소한다 — contextvar는 "지금 이 호출 스택"에만 적용되므로, 같은 싱글턴이라도 파이프라인 경유 호출에만 추적이 붙는다.

### 2-3. 전역 오염 경로

`langsmith()` (`langsmith.py:10-36`)는 `os.environ["LANGSMITH_TRACING"]="true"` / `LANGSMITH_PROJECT`를 **영구 세팅**하고 되돌리지 않는다. 호출부 3곳:

| 파일:라인 | 프로젝트명 | 비고 |
|---|---|---|
| `run_agent_use_case.py:237` | `agent-run` | **이중 배선** — `:662`에 per-run tracer가 이미 있음 |
| `general_chat/use_case.py:315` | `general-chat` | async generator `stream()` 본문 최상단 |
| `use_cases/analyze_excel_use_case.py:68` | `excel-analysis-agent` | 일반 async 함수 |

---

## 3. Requirements → 설계 매핑

### 3-1. 신규 모듈 요소

`src/infrastructure/langsmith/langsmith.py`에 추가한다.

| ID | 요소 | 내용 |
|---|---|---|
| FR-01 | `_tracing_enabled() -> bool` | `LANGCHAIN_API_KEY` 또는 `LANGSMITH_API_KEY`가 비어있지 않은지. `_make_project_tracer:67-71`의 키 판별 로직과 **동일 규칙을 공유**(중복 구현 금지 — 기존 함수에서 추출) |
| FR-01 | `PIPELINE_PROJECT_NAME = "agent-create-pipeline"` | 프로젝트명 단일 출처 (D5) |
| FR-02~05 | `pipeline_tracing(stage, *, request_id, round_, stop_after)` | `@contextmanager`. 키 없으면 `nullcontext`, 있으면 `tracing_v2_enabled(PIPELINE_PROJECT_NAME, tags=[...])` |
| FR-06 | `scoped_tracing(project_name, tags=None)` | 범용 스코프 추적 컨텍스트. 전역 `langsmith()` 대체용 |

### 3-2. 태그 설계

`tracing_v2_enabled`는 `run_name`을 받지 않으므로 **태그로 단계를 구분**한다.

```
tags = [
    "agent-create-pipeline",     # 공통 — 전체 필터용 (FR-05)
    f"stage:{stage}",            # intent | tools | prompt (FR-02~04)
    f"request:{request_id}",     # 한 요청의 단계 묶음 조회 (SC-02)
    f"round:{round_}",           # 되묻기 라운드
    f"stop:{stop_after or 'none'}",
]
```

> **SC-02 대응**: Plan은 "metadata에 `request_id`"를 요구했으나, `tracing_v2_enabled`는 metadata 인자가 없다. **태그로 대체**한다. LangSmith는 태그 필터를 지원하므로 "한 요청의 3단계 묶어보기" 목적은 달성된다. Plan SC-02의 문구는 Check 단계에서 이 대체를 반영해 평가한다.

### 3-3. 실사용 모델명 관측 (Plan §7-3 보강 항목)

`prompt` 단계의 실제 모델은 DB utility LLM에서 오고, 해석 실패 시 `ChatOpenAI(gpt-4o-mini)`로 조용히 떨어진다(`prompt_composer/adapter.py:164-175`, `utility_llm_provider.py:69-82`).

LangSmith run은 **실제 호출된 모델명을 자동으로 기록**하므로(LangChain이 LLM 메타를 전송), 별도 작업 없이 이 항목이 충족된다. 다만 "provider 해석이 실패해 폴백했다"는 사실 자체는 run에 안 남으므로, **`_resolve_chain`의 폴백 진입에 `logger.warning`을 추가**한다 (현재 무로그).

---

## 4. 아키텍처 — 적용 지점

### 4-1. 파이프라인 (FR-02~05)

**수정 지점은 `_stage()` 단 한 곳이다.**

```python
# src/application/agent_create_pipeline/use_case.py:178
async def _stage(self, stage, ctx, stage_fn) -> AsyncIterator[StageEvent]:
    """started 이벤트 → 실행 → elapsed 채워 completed 이벤트."""
    yield StageEvent("stage_started", StageRecord(stage, StageStatus.OK))
    start = time.monotonic()
    # Design Ref: §4-1 — 추적 컨텍스트는 await 만 감싼다. yield 를 가로지르면
    # contextvar 가 소비자 컨텍스트로 샌다 (§7-2).
    with pipeline_tracing(stage, request_id=ctx.request_id,
                          round_=ctx.round, stop_after=ctx.stop):
        record = await stage_fn(ctx)
    record = replace(record, elapsed_ms=int((time.monotonic() - start) * 1000))
    ctx.records.append(record)
    yield StageEvent("stage_completed", record)
```

**이 한 곳이 5단계 전부를 덮는다** — `_stage`는 `INTENT`(`use_case.py:146`)와 `runners` 루프(`:169`) 양쪽에서 쓰이기 때문이다. `create`/`bind`는 LLM을 호출하지 않으므로 컨텍스트만 열렸다 닫히고 run이 생기지 않는다(무해).

| 단계 | LLM 호출 지점 | 도달 경로 |
|---|---|---|
| `intent` | `src/infrastructure/intent/adapter.py:172` | `_run_intent` → `AnalyzeIntentUseCase.execute` → `IntentAnalyzerInterface.analyze` → 어댑터 |
| `tools` | `src/infrastructure/tool_selection/llm_tool_selector.py:223` | `_run_tools` → `ToolSelectorPort.select` → `_invoke` |
| `prompt` | `src/infrastructure/prompt_composer/adapter.py:194` | `_run_prompt` → `ComposePromptUseCase.compose` → `PromptGeneratorPort.generate` → 어댑터 |

세 경로 모두 `_stage`의 `await` 안쪽이므로 contextvar가 전파된다(§1-3 실측).

### 4-2. 전역 오염 제거 (FR-06, FR-07)

| 대상 | 조치 | 주의 |
|---|---|---|
| `run_agent_use_case.py:237` | **삭제만** | `:662` `make_agent_run_tracer`가 이미 `graph_config.callbacks`로 프로젝트를 지정한다. 기능 손실 없음 (FR-07) |
| `general_chat/use_case.py:315` | `scoped_tracing("general-chat")`으로 치환하되 **그래프 호출만 감싼다** | `stream()`이 async generator다. 본문 최상단에서 `with`를 열면 `yield`를 가로지른다 → §7-2 위반. 그래프 실행부(`:430` 부근)로 범위를 좁힌다 |
| `analyze_excel_use_case.py:68` | `scoped_tracing("excel-analysis-agent")`으로 치환 | 일반 async 함수라 그래프 `ainvoke`를 감싸면 된다 |
| `langsmith.py:10` `langsmith()` | **유지(deprecated 주석 추가)** | 호출부 0이 되지만 즉시 삭제하지 않는다 — 외부/테스트 참조 확인 후 별도 커밋 |

### 4-3. 기존 4개 경로 무영향 (NFR-03)

| 경로 | 방식 | 이번 변경 영향 |
|---|---|---|
| `agent-run` | `:662` per-run tracer (명시 callbacks) | `:237` 전역 제거로 **오히려 정확해짐** |
| `agent-composer` | `composer.py:219` / `planner.py:232` | 없음 |
| `document-extractor` | 어댑터 내부 tracer | 없음 |
| `document-generator` | 어댑터 내부 tracer | 없음 |

명시 tracer와 contextvar tracer가 동시에 존재할 일은 없다 — 서로 다른 호출 스택이다.

---

## 5. 데이터 / 계약 변경

**없음.**

| 항목 | 변경 |
|---|---|
| API 요청/응답 스키마 | 없음 |
| DB 스키마 | 없음 |
| 프론트엔드 | 없음 → `/api-contract-sync` **불필요** |
| domain Port 시그니처 | 없음 (D1의 핵심 이득) |
| 환경변수 | 없음 (기존 `LANGCHAIN_API_KEY` / `LANGSMITH_API_KEY` 재사용) |

---

## 6. 에러 처리 / 강하 (NFR-01)

| 상황 | 동작 |
|---|---|
| API 키 없음 | `pipeline_tracing`이 `nullcontext` 반환 → 추적 없음, 본 흐름 정상 |
| `tracing_v2_enabled` 진입 실패 | `try/except`로 흡수하고 `nullcontext`로 강하 + `logger.warning`. **파이프라인을 중단시키지 않는다** |
| LangSmith 전송 실패 | LangChain 내부에서 흡수(기존 동작). 본 흐름 무영향 |
| `stage_fn`이 예외 발생 | 컨텍스트가 정상적으로 닫히고 예외는 그대로 전파 — `use_case.py`의 "예외 전파가 계약"(§6.2)을 유지 |

---

## 7. 설계상 위험과 대응

### 7-1. 키 없이도 tracer가 생성되는 문제

§1-3에서 실측한 대로 `tracing_v2_enabled`는 키가 없어도 진입하고 `LangChainTracer`를 만든다. **기존 `_make_project_tracer`는 키가 없으면 `None`을 반환**해 이를 막았다(`langsmith.py:70-71`).

→ `pipeline_tracing`이 **진입 전에 키를 검사**해 `nullcontext`를 반환하게 한다. 키 판별 로직은 `_make_project_tracer`에서 추출해 공유한다(중복 금지).

### 7-2. contextvar × async generator — 가장 큰 함정

`@contextmanager`로 contextvar를 세팅한 채 `yield`를 가로지르면, 제너레이터가 일시정지된 동안 컨텍스트가 소비자 쪽으로 새거나 재개 시 복원이 어긋난다.

**규칙: 추적 컨텍스트는 `await`만 감싸고, 절대 `yield`를 포함하지 않는다.**

| 위치 | 준수 방법 |
|---|---|
| `use_case.py:_stage()` | `with`가 `await stage_fn(ctx)`만 감싼다. 두 `yield`는 밖에 있다 (§4-1 코드) |
| `general_chat.stream()` | 본문 최상단이 아니라 그래프 실행부만 감싼다 (§4-2) |
| `run_agent.stream()` | 해당 없음 — 삭제만 한다 |

이 규칙을 **테스트로 고정**한다 (§8 T-05).

### 7-3. `run_name` 미지원

`tracing_v2_enabled`는 `run_name`을 받지 않는다. LangSmith run 이름은 실행된 Runnable 이름(`RunnableSequence` 등)이 된다.

→ 태그(`stage:prompt`)로 구분한다(§3-2). 단계 구분이라는 목적은 달성되며, Plan SC-01의 "`pipeline:{stage}` run_name" 문구는 **"`stage:{stage}` 태그"로 대체**됨을 Check 단계에 명시한다.

### 7-4. `asyncio.wait_for` 타임아웃 시 run 기록

`intent`/`prompt` 어댑터는 `asyncio.wait_for(chain.ainvoke(...), timeout=...)`을 쓴다. 타임아웃 시 내부 task가 취소되는데, tracer가 해당 run을 어떤 상태로 남기는지는 **실측 미확인**이다.

→ Do 단계에서 의도적 타임아웃을 주입해 확인한다 (Plan SC-03의 핵심). 만약 run이 남지 않는다면 §9의 보완안(어댑터 `_degrade`에 구조화 로그 보강)으로 대체한다.

### 7-5. 전역 오염 제거의 회귀 위험

`general_chat`/`analyze_excel`은 현재 config·callbacks 구성부가 **아예 없다**(grep 확인). 전역 방식에 전적으로 의존하고 있어, 치환 위치를 잘못 잡으면 추적이 조용히 끊긴다.

→ 경로별 **개별 커밋**으로 롤백 단위를 좁힌다. 각 커밋마다 해당 기능을 수동 실행해 LangSmith 기록을 확인한다.

---

## 8. Test Plan

LLM 실호출 없이 검증한다. `tracing_v2_callback_var` 를 직접 읽어 단언한다.

| ID | 레벨 | 내용 |
|---|---|---|
| T-01 | L1 단위 | 키 없음 → `pipeline_tracing`이 `nullcontext`. contextvar 미세팅 |
| T-02 | L1 단위 | 키 있음 → 컨텍스트 안에서 `tracing_v2_callback_var.get() is not None`, 밖에서 `None` |
| T-03 | L1 단위 | 태그에 `agent-create-pipeline`, `stage:{stage}`, `request:{request_id}`가 포함됨 |
| T-04 | L1 단위 | `tracing_v2_enabled`가 예외를 던져도 `pipeline_tracing`이 강하하고 호출자가 정상 진행 |
| T-05 | L2 통합 | **`_stage()` 실행 중 `stage_fn` 안에서는 contextvar가 보이고, `stage_completed` yield를 받은 소비자 쪽에서는 보이지 않는다** (§7-2 고정) |
| T-06 | L2 통합 | 파이프라인 1회 실행(LLM 목) 시 3개 단계에서 각각 컨텍스트가 열렸다 닫힌 것을 스파이로 확인 |
| T-07 | L2 회귀 | 파이프라인을 거치지 않는 `intent_router` 직접 호출에는 contextvar가 세팅되지 않음 (§2-2 오분류 방지) |
| T-08 | L2 회귀 | `run_agent_use_case`가 `os.environ["LANGSMITH_TRACING"]`을 변경하지 않음 (FR-07) |
| T-09 | 수동 | 실제 위저드 1회 실행 → LangSmith 대시보드에 3 run 기록 확인 (SC-01) |
| T-10 | 수동 | `run_agent` 실행 직후 파이프라인 호출 → 파이프라인 run이 `agent-run`에 섞이지 않음 (SC-04) |

> TDD 필수(CLAUDE.md §1): T-01~T-05를 먼저 작성해 실패를 확인한 뒤 구현한다.

---

## 9. 대안 / 폴백 (§7-4가 실패할 경우)

타임아웃 run이 LangSmith에 남지 않는 것으로 확인되면:

1. `prompt_composer/adapter.py:_degrade`와 `intent/adapter.py:_degrade`의 로그에 `model_name`·`payload_size`·`timeout_sec`을 추가한다.
2. `_resolve_chain`의 provider 폴백 진입에 `warning`을 추가한다 (§3-3, 어차피 수행).

이 경우에도 `error`/`schema`/`empty` 세 사유는 LangSmith에 남으므로 목적의 대부분은 달성된다.

---

## 10. 레이어 검토

| 변경 파일 | 계층 | 규칙 위반 여부 |
|---|---|---|
| `infrastructure/langsmith/langsmith.py` | infrastructure | — |
| `application/agent_create_pipeline/use_case.py` | application → infrastructure import | ✅ 허용. CLAUDE.md §6이 금지하는 것은 `domain → infrastructure`. 선례: `run_agent_use_case.py:87`, `agent_composer/composer.py:14`, `planner.py:23` |
| `application/general_chat/use_case.py` | 〃 | ✅ (이미 `langsmith` import 중) |
| `application/use_cases/analyze_excel_use_case.py` | 〃 | ✅ (동일) |
| `application/agent_builder/run_agent_use_case.py` | 삭제만 | — |
| **domain/** | — | **변경 없음** ✅ |

`/verify-architecture` 스킬로 Do 완료 후 검증한다.

---

## 11. Implementation Guide

### 11.1 구현 순서

```
1. [TDD] T-01~T-04 작성 → 실패 확인
2. langsmith.py: 키 판별 로직 추출 + _tracing_enabled() + PIPELINE_PROJECT_NAME
                 + pipeline_tracing() + scoped_tracing()
3. T-01~T-04 통과 확인
4. [TDD] T-05~T-07 작성 → 실패 확인
5. use_case.py:_stage() 에 pipeline_tracing 적용 (§4-1)
6. T-05~T-07 통과 확인
7. prompt_composer/adapter.py:_resolve_chain 폴백 warning 추가 (§3-3)
8. [TDD] T-08 작성 → run_agent_use_case.py:237 삭제 → 통과 확인
9. general_chat/use_case.py:315 치환 (§4-2, yield 규칙 주의)
10. analyze_excel_use_case.py:68 치환
11. /verify-architecture, /verify-logging 실행
12. 수동 T-09, T-10
```

### 11.2 파일별 변경 요약

| 파일 | 유형 | 규모 |
|---|---|---|
| `src/infrastructure/langsmith/langsmith.py` | 추가 | ~60줄 |
| `src/application/agent_create_pipeline/use_case.py` | 수정 | ~5줄 (`_stage` 1곳) |
| `src/infrastructure/prompt_composer/adapter.py` | 수정 | ~5줄 (warning) |
| `src/application/agent_builder/run_agent_use_case.py` | 삭제 | 1줄 |
| `src/application/general_chat/use_case.py` | 수정 | ~5줄 |
| `src/application/use_cases/analyze_excel_use_case.py` | 수정 | ~5줄 |
| `tests/infrastructure/langsmith/test_pipeline_tracing.py` | 신규 | T-01~T-04 |
| `tests/application/agent_create_pipeline/test_tracing.py` | 신규 | T-05~T-08 |

**신규 2 / 수정 5 / 삭제 1** — 약 150줄 (테스트 포함).

### 11.3 Session Guide

| 모듈 | 키 | 내용 | 선행 |
|---|---|---|---|
| module-1 | `tracer-core` | `langsmith.py` 확장 + T-01~T-04 | — |
| module-2 | `pipeline-wiring` | `_stage()` 적용 + T-05~T-07 + `_resolve_chain` warning | module-1 |
| module-3 | `global-cleanup` | 전역 오염 3곳 제거 + T-08 | module-1 |
| module-4 | `manual-verify` | T-09, T-10 수동 검증 | module-2, module-3 |

권장 세션 분할:
- **세션 1**: module-1 + module-2 (핵심 목적 달성)
- **세션 2**: module-3 (회귀 위험이 별개라 분리)
- **세션 3**: module-4 (실환경 필요)

```
/pdca do pipeline-langsmith-tracing --scope tracer-core,pipeline-wiring
/pdca do pipeline-langsmith-tracing --scope global-cleanup
```

---

## 12. Plan 대비 변경 사항 (Check 단계 참고)

| Plan 항목 | Design에서의 변경 | 사유 |
|---|---|---|
| Option C = 명시적 `trace` 인자 | **C-2 contextvar로 변경** | domain Port 3개 오염 회피 (§1-2) |
| FR-02~04 "`run_name` 주입" | **태그로 대체** | `tracing_v2_enabled`가 run_name 미지원 (§7-3) |
| FR-02~04 "`metadata` 주입" | **태그로 대체** | 동일 |
| SC-01 "`pipeline:{stage}` run_name" | **"`stage:{stage}` 태그"로 판정** | 동일 |
| SC-02 "metadata에 request_id" | **"태그에 `request:{id}`"로 판정** | 동일 |
| §7-1 A/B/C 3안 | C-2 확정 | 사용자 선택 |

### 12-1. Do 단계에서 발생한 편차 (module-3)

| Design 항목 | 실제 구현 | 사유 |
|---|---|---|
| §4-2 `general_chat` → `scoped_tracing` | **`make_general_chat_tracer()`를 `callbacks`에 주입** | `stream()`의 그래프 호출 `agent.astream_events(...)`가 `async for` 안에서 `yield mapped`를 수행한다 — 컨텍스트 매니저로 감싸면 §7-2를 위반한다. `:430`에 이미 `config.callbacks`가 있어 `run_agent:662`와 동형 처리가 가능했다 |
| (없음) | **`tests/conftest.py` 신규** — LangSmith env 격리 autouse 픽스처 | `main.py:20 load_dotenv()`가 import 시점에 실제 `LANGCHAIN_API_KEY`를 `os.environ`에 올린다. 그 결과 (1) 테스트가 실제 LangSmith로 run을 POST하고 (2) tracer가 생겨 `config`가 붙으면서 이를 받지 않는 대역이 깨졌다 |

### 12-2. Do 단계에서 발견한 선행 결함 (이번 범위 밖)

**`TraceExtractor`가 동작하지 않는다.** 로컬 DB 실측: `ai_run` 152건 중
`langsmith_trace_id` 적재 **0건**, `langsmith_run_url` **0건**.

`extract()`는 그래프 실행이 끝난 뒤 호출되는데(`run_agent_use_case.py:319,462`,
`general_chat/use_case.py:266`), 그 시점에는 run tree contextvar가 이미 해제된다.
실측 결과:

| 추적 방식 | 실행 중 | 실행 후(실제 호출 시점) |
|---|---|---|
| 없음 | `(None, None)` | `(None, None)` |
| 전역 env (제거 전 방식) | `(None, None)` | `(None, None)` |
| 명시 callbacks tracer | `(trace_id, None)` | `(None, None)` |
| `scoped_tracing` | `(trace_id, None)` | `(None, None)` |

→ 전역 제거가 이 기능을 **퇴행시키지 않는다**(이미 0건). 오히려 전역 방식은
실행 중에도 trace_id를 남기지 못했다. 수정하려면 `extract()` 호출 위치를 그래프
실행 **중**으로 옮겨야 하며, 별도 feature로 다룬다.

---

## Version History

| 버전 | 일자 | 내용 |
|---|---|---|
| 0.1 | 2026-09-20 | 최초 작성. Option C-2 확정. langchain_core 1.6.0 실측 반영. |
