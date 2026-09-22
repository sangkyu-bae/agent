# Plan — pipeline-langsmith-tracing

> Feature: `pipeline-langsmith-tracing`
> Created: 2026-09-20
> Phase: plan
> 관련: [[prompt-fallback-visibility]] (이 feature가 선행)

---

## Executive Summary

| 관점 | 내용 |
|---|---|
| **Problem** | 에이전트 생성 파이프라인(`/api/v1/agents/pipeline/stream`) 전 구간에 LangSmith 배선이 **0건**이다. 5단계 중 3단계가 LLM을 호출하는데 어느 것도 추적되지 않아, 실패·품질 저하가 발생해도 사후에 원인을 볼 수 없다. |
| **Solution** | `run_agent`·`agent_composer`가 이미 쓰는 per-run tracer 패턴을 파이프라인에 동형 적용하고, `os.environ`을 영구 변경하는 전역 오염 경로를 제거한다. |
| **Function UX Effect** | 사용자 화면 변화 없음. 운영자가 LangSmith에서 `pipeline:{stage}` run_name으로 단계별 입출력·지연·실패를 조회할 수 있다. |
| **Core Value** | **"폴백이 실패를 가린다"는 구조적 은폐를 깬다.** 코드에 이미 *"intent 모듈에서 3개월 은폐된 실사례"*(`adapter.py:94-100`)가 기록돼 있고, 동일 패턴이 prompt_composer에서 재발한 정황이 있다. |

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

### 1-1. 현재 상태 (코드 검증 완료)

`/api/v1/agents/pipeline/stream` 경로 전 구간에 LangSmith 배선이 없다.

| 파일 | 검색 결과 |
|---|---|
| `src/api/routes/agent_pipeline_router.py` | `trace`/`langsmith`/`callbacks`/`run_name` — **0건** |
| `src/application/agent_create_pipeline/use_case.py` | **0건** |
| `src/infrastructure/agent_create_pipeline/adapters.py` | **0건** |

LLM을 실제로 호출하는 3개 지점도 전부 config 미전달:

| 단계 | 호출 지점 | 현재 |
|---|---|---|
| `intent` | `src/infrastructure/intent/adapter.py:172` `chain.ainvoke(payload)` | config 없음 |
| `tools` | `src/infrastructure/tool_selection/llm_tool_selector.py:223` `llm.ainvoke(messages)` | config 없음 |
| `prompt` | `src/infrastructure/prompt_composer/adapter.py:194` `chain.ainvoke(payload)` | config 없음. **Protocol(`:118`)은 `config` 자리를 열어뒀으나 호출이 넘기지 않는다** |

### 1-2. 이미 배선된 경로 (따라야 할 선례)

`src/infrastructure/langsmith/langsmith.py`

**방식 A — per-run tracer (권장 패턴)**

| 호출부 | 프로젝트 |
|---|---|
| `run_agent_use_case.py:662` `make_agent_run_tracer(agent.name, tags)` | `agent-{에이전트명}` |
| `agent_composer/composer.py:219`, `planner.py:232` `make_composer_tracer()` | `agent-composer` |
| `document_extractor/{composer,slot_extractor}.py` | `document-extractor` |
| `document_generator/generator.py:238` | `document-generator` |

`_make_project_tracer()` (`langsmith.py:58`) 주석: *"graph_config['callbacks']에 주입해 전역 os.environ 변경 없이 run별 프로젝트를 지정한다. langchain_core는 명시적 LangChainTracer가 있으면 전역 auto-tracer를 추가하지 않으므로 중복/경합이 없다."* API 키가 없으면 `None`을 반환해 본 흐름에 영향을 주지 않는다.

**방식 B — 전역 `os.environ` 변경 (제거 대상)**

`langsmith()` (`langsmith.py:10-36`)는 키가 있으면 `os.environ["LANGSMITH_TRACING"]="true"` / `LANGSMITH_PROJECT`를 **프로세스 전역에 영구 세팅**하고, 되돌리는 코드가 없다. 호출부 3곳:

- `run_agent_use_case.py:237` `langsmith(project_name="agent-run")`
- `general_chat/use_case.py:315` `langsmith(project_name="general-chat")`
- `use_cases/analyze_excel_use_case.py:68` `langsmith(project_name="excel-analysis-agent")`

### 1-3. 전역 오염이 만드는 실제 문제

`.env:30`은 `LANGSMITH_TRACING=false`지만 `LANGCHAIN_API_KEY`는 설정돼 있다. 따라서:

```
1. 누군가 에이전트를 실행       → run_agent_use_case.py:237 langsmith("agent-run")
                                 ⇒ 전역 TRACING=true, PROJECT="agent-run" (영구)
2. 이후 /agents/pipeline 호출   → 명시 tracer가 없으므로 langchain_core가 전역 auto-tracer 부착
                                 ⇒ 파이프라인 LLM 호출이 "agent-run" 프로젝트로 섞여 들어감
3. 이후 일반 채팅 실행          → PROJECT="general-chat" 으로 덮어씀
                                 ⇒ 이후 파이프라인 run은 "general-chat" 에 섞임
```

즉 **"배선 없음 = 추적 안 됨"이 아니다.** 서버 기동 직후에만 꺼져 있고, 이후엔 비결정적으로 엉뚱한 프로젝트에 섞인다. 동시 요청이 있으면 `run_agent`의 per-run tracer와 전역 tracer가 프로젝트를 놓고 경합한다(`run_agent`는 `:237`에서 전역을 켜고 `:662`에서 per-run을 쓰는 **이중 배선** 상태).

> ⚠️ 이 3-스텝 시나리오는 코드 구조에서 도출한 것이며, LangSmith 대시보드로 실측 검증하지 않았다. Do 단계에서 재현 확인을 우선 항목으로 둔다.

### 1-4. 보조 문제 — 로그 사후 조회 불가

`StructuredLogger` (`structured_logger.py:52`)는 `StreamHandler(sys.stdout)`만 쓴다. 파일 핸들러가 없어 **서버 터미널 스크롤백을 잃으면 실패 로그를 되찾을 방법이 없다.** 이번 조사에서 실제로 `prompt generation {reason}, fallback=degraded` 로그를 확인하지 못한 이유다.

---

## 2. Scope

### In Scope

1. 파이프라인 전용 LangSmith 프로젝트 + per-run tracer 팩토리 추가
2. `intent` / `tools` / `prompt` 3개 LLM 호출에 tracer·`run_name`·`metadata` 주입
3. 단계 경계 추적: `stage_started`/`stage_completed`가 LangSmith run과 대응되도록 구성
4. 전역 `os.environ` 오염 제거 — `langsmith()` 호출 3곳을 per-run tracer로 전환
5. `run_agent_use_case`의 이중 배선(`:237` 전역 + `:662` per-run) 해소

### Out of Scope

- 프롬프트 생성 **품질** 개선 → [[prompt-fallback-visibility]]
- degraded 시 저장 차단 UX → [[prompt-fallback-visibility]]
- 로그 파일 핸들러 추가 → 별도 검토 (§9에 후보로 기록)
- LangSmith 외 APM/OTel 도입

---

## 3. Requirements

### FR — 기능 요구사항

| ID | 요구사항 | 근거 |
|---|---|---|
| FR-01 | `langsmith.py`에 `PIPELINE_PROJECT_NAME`과 `make_pipeline_tracer(tags)`를 추가한다. 기존 `make_*_tracer`와 동형(`_make_project_tracer` 재사용). | `langsmith.py:89-95` 선례 |
| FR-02 | `intent` 단계 LLM 호출에 tracer + `run_name="pipeline:intent"` + `metadata={request_id, round, user_id}`를 주입한다. | `adapter.py:172` |
| FR-03 | `tools` 단계에 동일 형태로 `run_name="pipeline:tools"` + `metadata={request_id, candidate_count, top_k}`를 주입한다. | `llm_tool_selector.py:223` |
| FR-04 | `prompt` 단계에 `run_name="pipeline:prompt"` + `metadata={request_id, tool_ids, has_intent}`를 주입한다. **Protocol이 이미 `config` 자리를 갖고 있으므로 시그니처 변경 없이 값만 채운다.** | `prompt_composer/adapter.py:118,194` |
| FR-05 | 세 단계의 `tags`에 공통 태그(`agent-create-pipeline`)와 단계 태그를 넣어 LangSmith에서 필터 가능하게 한다. | — |
| FR-06 | `langsmith()` 전역 함수 호출 3곳을 per-run tracer로 전환한다. 각 경로의 기존 프로젝트명(`agent-run`/`general-chat`/`excel-analysis-agent`)은 **그대로 유지**한다. | `langsmith.py:10-36` |
| FR-07 | `run_agent_use_case.py:237`의 전역 호출을 제거한다. `:662`의 per-run tracer가 이미 프로젝트를 지정하므로 기능 손실이 없다. | `run_agent_use_case.py:237,662` |
| FR-08 | API 키 미설정 환경에서 tracer는 `None`이 되고 본 흐름에 영향을 주지 않는다(기존 `_make_project_tracer` 계약 승계). | `langsmith.py:70-71` |

### NFR — 비기능 요구사항

| ID | 요구사항 |
|---|---|
| NFR-01 | tracer 생성·주입 실패가 파이프라인 실행을 중단시키지 않는다 (best-effort). |
| NFR-02 | 프로젝트명은 하드코딩 상수로 `langsmith.py` 한 곳에만 둔다 (CLAUDE.md §3 config 단일 출처). |
| NFR-03 | 기존 4개 추적 경로(`agent-run`/`agent-composer`/`document-extractor`/`document-generator`)에 회귀가 없다. |
| NFR-04 | 레이어 규칙 준수 — 아래 §7-1 참조. |

---

## 4. Success Criteria

| ID | 기준 | 검증 방법 |
|---|---|---|
| SC-01 | 위저드로 에이전트 1건을 생성하면 LangSmith 전용 프로젝트에 `pipeline:intent` / `pipeline:tools` / `pipeline:prompt` run 3건이 기록된다. | 수동 E2E + 대시보드 확인 |
| SC-02 | 각 run의 metadata에 동일한 `request_id`가 있어 한 요청의 3단계를 묶어 조회할 수 있다. | 대시보드 필터 |
| SC-03 | `prompt` 단계가 degraded로 떨어진 run에서 LangSmith 상으로 **실패 원인(예외/타임아웃)이 식별된다.** | 의도적 실패 주입 후 확인 |
| SC-04 | `run_agent` 실행 후 파이프라인을 호출해도 파이프라인 run이 `agent-run` 프로젝트로 새지 않는다. | 순차 실행 후 대시보드 확인 |
| SC-05 | API 키를 제거한 환경에서 파이프라인이 정상 동작하고 에러 로그가 없다. | 테스트 |
| SC-06 | 기존 4개 경로의 추적이 이전과 동일하게 동작한다. | 회귀 테스트 |

---

## 5. Risks and Mitigation

| 위험 | 영향 | 완화 |
|---|---|---|
| `langsmith()` 제거가 기존 추적을 끊음 | `general-chat`·`excel-analysis` 추적 유실 | FR-06에서 프로젝트명을 유지한 per-run tracer로 **1:1 치환**. 경로별로 개별 커밋하여 롤백 단위를 작게 유지 |
| `run_agent`의 전역 호출 제거가 하위 경로(sub_agent 등)의 추적에 영향 | 일부 run 누락 | `:662` tracer가 `graph_config.callbacks` 선두에 있어 그래프 전체(하위 노드 포함)를 덮는지 Do 단계에서 먼저 확인 |
| 전역 `LANGSMITH_TRACING`이 이미 켜진 상태에서 per-run tracer가 중복 기록 | run 중복 | `langsmith.py:62-63` 주석의 "명시 tracer가 있으면 전역 auto-tracer를 추가하지 않는다"를 테스트로 고정 |
| `.env`에 `LANGSMITH_TRACING=false`지만 키가 존재 | 의도치 않은 외부 전송 | 전역 오염 제거 후에는 명시 tracer만 동작 — 오히려 개선. **다만 파이프라인 프롬프트/요청 내용이 LangSmith로 나간다는 점은 사용자 승인 대상** (§9-1) |
| LLM 어댑터 시그니처 변경 범위 | 호출부 광범위 수정 | `prompt_composer`는 Protocol에 `config` 자리가 이미 있어 무변경. `intent`/`tool_selection`은 **기본값 `None`**으로 추가해 기존 호출부 무영향 |

---

## 6. Impact Analysis

### 변경 대상 (예상)

| 파일 | 변경 유형 | 비고 |
|---|---|---|
| `src/infrastructure/langsmith/langsmith.py` | 추가 | `PIPELINE_PROJECT_NAME`, `make_pipeline_tracer()` |
| `src/infrastructure/intent/adapter.py` | 수정 | `ainvoke`에 config 전달 |
| `src/infrastructure/tool_selection/llm_tool_selector.py` | 수정 | 〃 |
| `src/infrastructure/prompt_composer/adapter.py` | 수정 | `:194` — Protocol 무변경, 값만 전달 |
| `src/application/agent_create_pipeline/use_case.py` | 수정 | 단계별 trace 메타 전달 (설계안에 따라 유무 결정) |
| `src/application/agent_builder/run_agent_use_case.py` | 삭제 | `:237` 전역 호출 |
| `src/application/general_chat/use_case.py` | 수정 | `:315` → per-run tracer |
| `src/application/use_cases/analyze_excel_use_case.py` | 수정 | `:68` → per-run tracer |

### 무영향 확인 대상

- 프론트엔드: **변경 없음** (API 계약 무변경 → `/api-contract-sync` 불필요)
- DB 스키마: 변경 없음
- 기존 테스트: `tests/` 내 langsmith 관련 테스트 존재 여부를 Do 단계에서 확인

---

## 7. Architecture Considerations

### 7-1. 레이어 규칙 — 결정 필요

`application/` 레이어가 `infrastructure/langsmith`를 직접 import하는 것은 **기존 선례가 있다**:

- `run_agent_use_case.py:87`, `agent_composer/composer.py:14`, `planner.py:23`

CLAUDE.md §6이 금지하는 것은 `domain → infrastructure`이므로 **규칙 위반은 아니다.** 다만 `document_extractor`/`document_generator`는 `infrastructure` 안에서만 쓴다.

파이프라인은 `application/agent_create_pipeline/use_case.py`가 흐름을 쥐고 있어 두 가지 선택지가 있다. **Design 단계에서 3안 비교로 결정한다.**

| 안 | 내용 | 트레이드오프 |
|---|---|---|
| A | UseCase가 tracer를 만들어 어댑터에 넘김 | 단계 메타(round, stop_after)를 한곳에서 붙일 수 있음. application→infrastructure import 추가 |
| B | 각 infrastructure 어댑터가 자체적으로 tracer 생성 | 레이어가 깨끗함. 단계 메타를 어댑터가 모름 → run 간 연결이 `request_id`뿐 |
| C | `domain/agent_create_pipeline/interfaces.py`에 Port를 정의하고 infrastructure가 구현, main.py가 주입 | 가장 정석. 파일 수 증가, 관측성 하나에 과한 추상화일 수 있음 |

> **주의**: 이 프로젝트는 CLAUDE.md §6에서 "과도한 추상화(두꺼운 DDD)"를 금지한다. C안은 그 경계에 있다.

### 7-2. 단계 경계와 LangSmith run의 대응

`use_case.py:178` `_stage()`가 `stage_started` → 실행 → `stage_completed`를 yield한다. LangSmith run을 이 경계와 1:1로 맞출지, 아니면 LLM 호출 단위로 둘지 결정이 필요하다. LLM을 호출하지 않는 `create`/`bind` 단계는 LangSmith run이 없으므로 **완전 대응은 불가능**하다.

### 7-3. `prompt` 단계의 모델 해석 경로 (부수 발견)

`main.py:4379`가 `llm_provider=get_utility_llm_provider()`를 주입하므로, `prompt` 단계 모델은 `PROMPT_COMPOSER_MODEL`(기본 `gpt-4o-mini`)이 **아니라 DB의 utility LLM 설정**에서 온다(`adapter.py:164-172`). 그런데 `.env`에 `UTILITY_LLM_MODEL_NAME`이 없어 `settings.utility_llm_model_name = None`이다.

`UtilityLLMProvider.get()` (`utility_llm_provider.py:69-82`)은 **어떤 실패든 `None`을 반환**하고, 그러면 `_resolve_chain`이 `ChatOpenAI(gpt-4o-mini)` 직접 생성으로 떨어진다. 이 폴백 체인 자체가 관측되지 않는 구간이므로, **metadata에 "실제 사용된 모델명"을 반드시 포함**해야 한다 (FR-04 보강 항목).

---

## 8. Convention Prerequisites

- **TDD 필수** (CLAUDE.md §1): tracer 주입 여부를 검증하는 테스트를 먼저 작성한다. LLM 실호출 없이 `chain` 목으로 `config` 인자를 캡처해 단언하는 방식.
- **print() 금지 / logger 필수** (§6)
- **config 하드코딩 금지** (§3) — 프로젝트명 상수는 `langsmith.py` 단일 출처
- **함수 40줄 / if 중첩 2단계** (§3)
- 작업 전 `docs/wiki/_INDEX.md` 확인 (루트 CLAUDE.md §6-1). 특히 `degradation-vs-failure-boundary` 문서가 `prompt_composer/policies.py`에서 참조되므로 함께 읽는다.

---

## 9. Next Steps

### 9-1. Design 진입 전 사용자 확인 필요

| # | 확인 사항 |
|---|---|
| 1 | **외부 전송 승인** — LangSmith 추적을 켜면 사용자의 에이전트 생성 요청 원문·의도 분석 결과·생성된 시스템 프롬프트가 Anthropic이 아닌 **LangSmith(외부 서비스)로 전송**된다. 현재 `.env:30`이 `LANGSMITH_TRACING=false`인 것이 의도적 결정인지 확인이 필요하다. |
| 2 | `.env`의 `LANGCHAIN_API_KEY`가 커밋 이력에 들어간 적이 있는지 확인 권장 (이번 조사 중 파일에서 평문으로 확인됨). |
| 3 | §7-1의 A/B/C 3안 중 선택 — `/pdca design pipeline-langsmith-tracing`에서 비교표와 함께 제시 예정 |

### 9-2. 후속 검토 후보 (이 feature 범위 밖)

- `StructuredLogger`에 파일 핸들러 추가 (로그 사후 조회 불가 문제)
- `.env`에 `UTILITY_LLM_MODEL_NAME` 미설정 상태의 의도 확인

### 9-3. 명령

```
/pdca design pipeline-langsmith-tracing
```

---

## Version History

| 버전 | 일자 | 내용 |
|---|---|---|
| 0.1 | 2026-09-20 | 최초 작성. 코드 정적 검증 기반. |
