# agent-create-pipeline Planning Document

> **Summary**: 의도 분석(`intent`) → 도구 추천(`tool_selection`) → 시스템 프롬프트 생성(`prompt_composer`) → 에이전트 확정 저장(`agent_builder`)을 하나의 백엔드 엔드포인트로 엮는 오케스트레이션 파이프라인. 필수 정보가 부족하면 되묻기(stateless HITL)로 왕복하고, 충족되면 `agent_definition` 실제 생성까지 한 호출로 완료한다. 화면이 단계별 진행·확인·에러 상태를 표시할 수 있도록 **단계 상태 모델 + SSE 진행 이벤트 스트리밍**을 계약에 포함한다. 기존 자동 생성 경로 2종은 무변경.
>
> **Project**: sangplusbot (idt — 백엔드)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-08-18
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 최근 세 사이클에서 만든 재료 모듈(`intent`, `tool_selection`, `prompt_composer`)이 전부 출하됐지만 서로 배선된 적이 없다. 에이전트를 자동으로 만들려면 호출자가 `/intent/analyze` → (도구 수동 선택) → `/prompt-composer/compose` → `POST /api/v1/agents` → `PATCH` 바인딩까지 **4~5번의 API를 순서대로 알고 호출**해야 하며, 도구 추천은 빌더 문맥에 노출된 API 자체가 없다. |
| **Solution** | 신규 병렬 엔드포인트 `agent-create-pipeline` — 자연어 요청 하나를 받아 의도 판정(미충족 슬롯이면 되묻기 질문 반환) → `LLMToolSelector` 재사용 도구 추천 → `ComposePromptUseCase`로 프롬프트 생성·버전 저장 → `CreateAgentUseCase`로 `agent_definition` 생성 → 프롬프트 세션에 `agent_id` 자동 바인딩까지 서버가 순차 오케스트레이션한다. 진행 중에는 **단계별 상태 이벤트(SSE)** 를 송출하고, 최종 응답에도 단계별 결과(steps) 요약을 담는다. 기존 `/agents/compose`·`/v3/agents/auto` 경로는 물리적 무변경. |
| **Function/UX Effect** | 이번 사이클 화면 구현은 **없음** (프론트 스코프 제외 — 사용자 확정)이지만, 화면이 "의도 분석 → 도구 추천 → 프롬프트 생성 → 에이전트 생성" 각 단계의 진행·성공·degraded·실패를 실시간 표시할 수 있는 API 계약을 이번에 확정한다. 생성 근거(의도·도구·프롬프트 버전)가 전부 이력으로 남는다. |
| **Core Value** | "재료 모듈의 첫 완주 배선" — 각 모듈의 단일 책임·degraded 계약을 그대로 유지한 채, 조합 책임만 지는 UseCase 하나로 end-to-end 가치를 증명한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | intent·tool_selection·prompt_composer가 배선 없이 각자 떠 있어, 에이전트 자동 생성의 end-to-end 가치가 한 번도 증명된 적 없다 |
| **WHO** | P2(에이전트 소유자). 이번 사이클 1차 소비자는 API 호출자(백엔드) — 프론트 배선은 후속 사이클 |
| **RISK** | 도구선택+프롬프트 생성 규칙이 **3벌 공존**하게 됨(AgentComposer / v3 auto / 신규 파이프라인). 수렴 계획 없이 방치되면 규칙이 벌어진다 |
| **SUCCESS** | 기존 경로 회귀 0건 · 되묻기 왕복 후 재호출로 생성 완주 · LLM 단계별 실패는 200+degraded, 저장 실패는 5xx · 생성된 agent_id 조회 가능 + 세션 바인딩 확인 · SSE 이벤트 순서가 단계 정의와 일치하고 실패 단계가 이벤트로 식별됨 |
| **SCOPE** | 오케스트레이션 UseCase + 신규 라우터(POST + SSE 스트림) + 단계 상태 모델 + intent 스펙 서버 소유 + 도구 추천 어댑터. **밖**: 프론트 UI, 기존 경로 수정, 신규 테이블 |

---

## 1. Overview

### 1.1 Purpose

자연어 한 문장(+ 되묻기 답변)으로 에이전트를 **만들어 주는** 단일 엔드포인트를 만든다. 핵심은 새 로직이 아니라 **조합**이다 — 판정·추천·생성·저장의 실제 일은 전부 기존 모듈이 하고, 신규 UseCase는 순서·데이터 전달·실패 정책만 소유한다.

### 1.2 Background — 재료 현황과 배선 공백

| 모듈 | 산출물 | 현재 배선 | 비고 |
|------|--------|-----------|------|
| `intent` | `IntentResult` + 미충족 슬롯 되묻기(stateless 왕복) | `POST /api/v1/intent/analyze` 단독 | 분류 스펙(labels/slots)을 요청으로 받는 무결합 설계 |
| `tool_selection` | `SelectionResult{selected_ids, …, fallback}` | General Chat 런타임만 (`tool_selector_enabled` 기본 off) | 빌더 문맥용 추천 API 없음 |
| `prompt_composer` | 구조화 프롬프트 + `prompt_session`/`prompt_version` 이력 | `POST /api/v1/prompt-composer/compose` 단독 | Plan에서 배선을 명시 이월(O1/O3/O4) — **본 기능이 그 이월분** |
| `agent_builder` | `agent_definition` CRUD | `POST /api/v1/agents` (확정 저장) | `CreateAgentUseCase` 재사용 대상 |

기존 자동 생성 경로 2종은 살아있는 라이브 경로다:

- `POST /api/v1/agents/compose` — `AgentComposer` LLM 1회 통합 호출, 무저장 초안 (진입 화면·Fix 탭 의존)
- `POST /api/v3/agents/auto` — 202+세션 폴링, 되묻기 후 실제 생성 (`AutoAgentBuilder` 루프)

### 1.3 Design Decisions (사용자 확정 4건 + 파생 3건)

| ID | 결정 | 근거 | 대가 |
|----|------|------|------|
| **D1** | **신규 병렬 엔드포인트** — 기존 compose/auto 물리적 무변경 | 회귀 0. 검증 후 후속 사이클에서 기존 경로 대체·수렴 검토 (사용자 확정) | 도구선택+프롬프트 규칙 3벌 공존 → §5 R1 |
| **D2** | 도구 추천은 **`LLMToolSelector` 재사용** — 빌더 문맥 어댑터로 감싼다 | 검증된 셀렉터·환각 방어(§6.1 #6) 재사용, 신규 LLM 로직 0 (사용자 확정) | 대화 필터용 top_k 설계를 빌더 문맥에 이식 → §5 R3 |
| **D3** | **되묻기 포함** — 미충족 슬롯이면 `complete=false`+questions 반환, 클라이언트가 answers/round 실어 재호출 (intent의 stateless HITL 관례 그대로) | 세션 테이블 불필요, `stateless-hitl-clarification` 위키 패턴 준수 (사용자 확정) | 왕복 동안 도구·프롬프트 단계는 미실행 — complete 이후에만 수행 |
| **D4** | complete 시 **`agent_definition` 실제 생성까지** — `CreateAgentUseCase` 재사용, `agent_id` 반환, `prompt_session` 저장 + `agent_id` 바인딩 자동 | "에이전트 생성하는 하나의 엔드포인트"라는 요청 원문 (사용자 확정). 프론트 없이도 완결 | 사용자 검토 단계 없음 — 저품질이어도 생성됨 → degraded 플래그·버전 이력으로 사후 수정 근거 제공 |
| **D5** | intent 분류 스펙(labels/slots)은 **서버가 소유** — 에이전트 생성용 고정 스펙을 config/도메인 상수로 정의해 intent 모듈에 주입 | 호출자가 스펙을 알 필요 없어야 "하나의 엔드포인트"가 성립. intent 모듈의 무결합 설계는 그대로 (스펙은 여전히 주입 인자) | 스펙 변경 시 서버 배포 필요 |
| **D6** | degraded 경계는 **"쓸 수 있는 결과가 존재하는가"** 기준 — intent/도구추천/프롬프트 LLM 실패는 단계별 degraded 플래그+폴백으로 진행, **에이전트 저장 실패는 5xx 전파** | `degradation-vs-failure-boundary` 위키 패턴(승인) + prompt_composer §6.2 계약과 동일 | 부분 degraded 상태로 생성된 에이전트 존재 가능 → 응답에 단계별 플래그 명시 |
| **D7** | **세션 없는 단일 왕복** — 202+폴링 세션(v3 방식)을 만들지 않는다. 기본은 동기 JSON 응답 | 신규 상태 테이블 0, stateless 왕복과 일관. LLM 최대 3회 순차 호출 지연은 NFR로 관리 | 장시간 요청 → §5 R2 |
| **D8** | **단계 상태는 1급 계약** — 파이프라인 단계(intent → tools → prompt → create → bind)마다 `{status: running\|ok\|degraded\|failed\|skipped, reason, elapsed_ms}` 상태 모델을 domain에 정의한다. 전송은 2채널: ① **SSE 스트림 엔드포인트**가 `stage_started`/`stage_completed`/`stage_failed` 이벤트를 실시간 송출(기존 agent-run `run/stream` SSE 관례·포매터 재사용), ② 동기 POST 응답과 SSE 최종 이벤트 양쪽에 `steps[]` 요약을 포함해 화면이 사후에도 단계별 확인·에러 표시를 재구성할 수 있게 한다 | 화면의 단계별 진행·에러 표시 요구(사용자 확정). 폴링 세션 없이(D7 유지) 실시간성을 확보하는 유일한 길이 스트리밍이고, SSE는 코드베이스에 검증된 관례가 있다 | 라우터 2개(POST/SSE) 유지보수. SSE 중단 시 재호출 필요 → §5 R7 |

---

## 2. Scope

### 2.1 In Scope

| # | 항목 |
|---|------|
| S1 | `application/agent_create_pipeline`(가칭) — 오케스트레이션 UseCase: intent 판정(되묻기 분기) → 도구 추천 → 프롬프트 생성 → 에이전트 생성 → 세션 바인딩 |
| S2 | 에이전트 생성용 intent 스펙 정의 (labels/slots — 구체 축은 Design에서 확정) + config |
| S3 | `tool_selection` 셀렉터의 빌더 문맥 어댑터 — 전체 활성 `tool_catalog`를 후보로 질의 기반 추천 (General Chat 배선과 독립된 활성화 설정) |
| S4 | 신규 라우터 + 요청/응답 스키마 (되묻기 응답과 완료 응답의 구분 포함, 경로는 Design에서 확정 — 예: `POST /api/v1/agents/pipeline`) |
| S5 | 요청 `tool_ids`(선택) 지원 — 사용자 명시 도구는 추천 결과와 병합·항상 포함 |
| S6 | **단계 상태 모델**(domain VO: 단계 열거 + status/reason/elapsed) + UseCase의 단계 이벤트 방출(콜백 또는 async generator — Design에서 확정) |
| S7 | **SSE 스트림 엔드포인트** — 단계 이벤트 실시간 송출 + 최종 이벤트에 결과 전문(되묻기 questions 또는 agent_id+steps). 기존 `run/stream` SSE 포매터·query-token 인증 관례 재사용 |
| S8 | `main.py` DI 조립 + 라우터 등록 (기존 관례: 조립 실패 시 라우터 미등록 낙하) |
| S9 | 테스트 — domain/application/api 계층 + SSE 이벤트 순서·실패 이벤트 테스트 + 기존 경로 무변경 회귀 테스트 (TDD) |

### 2.2 Out of Scope

| # | 항목 | 이유 |
|---|------|------|
| O1 | 프론트엔드 UI 배선 | 사용자 확정 — 후속 사이클 |
| O2 | 기존 `/agents/compose`·`/v3/agents/auto` 수정·대체·정리 | D1 — 검증 후 후속 사이클에서 수렴 검토 |
| O3 | 신규 DB 테이블·마이그레이션 | 기존 `prompt_session`/`prompt_version`/`agent_definition` 재사용으로 충분 |
| O4 | 도구 추천 전용 독립 API (`POST /tools/recommend` 류) | 파이프라인 내부 협력자로만. 단독 노출은 필요해질 때 |
| O5 | 프롬프트 섹션 부분 재생성·에이전트 사후 수정 흐름 | prompt-composer O6과 동일하게 이월 |
| O6 | General Chat 쪽 `tool_selector_enabled` 동작 변경 | 본 기능은 별도 설정으로 활성화 |
| O7 | SSE 끊김 후 이어보기(Last-Event-ID 재개)·진행 상태 서버 보존 | stateless(D7) 유지 — 끊기면 재호출. 중복 생성 방어는 R7에서 관리 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|:--------:|
| **FR-01** | 단일 엔드포인트 `POST`(경로 Design 확정) — `user_request`(필수) + `history`(선택) + `answers`/`round`(되묻기 왕복용, 선택) + `tool_ids`(선택) + `name`(선택) 수신 | P0 |
| **FR-02** | 서버 소유 intent 스펙으로 `AnalyzeIntentUseCase`를 호출한다. `complete=false`면 questions를 에코백하고 **도구·프롬프트·생성 단계를 수행하지 않는다**. 클라이언트는 answers/round를 실어 같은 엔드포인트를 재호출한다 (stateless 왕복, 서버 재clamp 방어 포함) | P0 |
| **FR-03** | complete 시 전체 활성 `tool_catalog`를 후보로 `LLMToolSelector`(어댑터 경유)를 호출해 도구를 추천한다. 요청 `tool_ids`는 추천 결과와 병합하며 항상 포함된다. 카탈로그에 없는 ID는 무시하고 응답에 에코백한다 | P0 |
| **FR-04** | 확정된 도구·의도·요청으로 `ComposePromptUseCase`를 호출해 프롬프트를 생성하고 `prompt_session`/`prompt_version`에 저장한다 (기존 계약 그대로 재사용) | P0 |
| **FR-05** | 생성된 프롬프트·도구·이름으로 `CreateAgentUseCase`(`POST /api/v1/agents`와 동일 경로)를 호출해 `agent_definition`을 생성하고 `agent_id`를 반환한다 | P0 |
| **FR-06** | 생성 직후 `prompt_session`에 `agent_id`를 바인딩한다 (기존 bind 계약 재사용). 바인딩 실패는 생성 성공을 뒤집지 않는다 — 응답에 바인딩 결과 명시 | P1 |
| **FR-07** | LLM 단계별 실패는 **200 + 단계별 degraded 플래그**: intent 실패 → 되묻기 생략·"의도 모름"으로 진행, 추천 실패 → 요청 `tool_ids`만으로(없으면 빈 도구) 진행, 프롬프트 실패 → 규칙기반 폴백. 응답에 어느 단계가 degraded인지 구분해 노출 | P0 |
| **FR-08** | **에이전트 저장·프롬프트 버전 저장 실패는 5xx 전파** — 200으로 위장하지 않는다 (D6) | P0 |
| **FR-09** | 전 요청 인증 필수(`get_current_user`). 세션·에이전트 소유권 검사는 기존 모듈 계약 준수 | P0 |
| **FR-10** | 입력 검증은 기존 모듈 계약을 상속 — `user_request` 길이, history 절단, tool_ids 상한, round 재clamp 등. 위반은 422 | P0 |
| **FR-11** | 기존 라우트(`/agents/compose`, `/v3/agents/auto`, `/intent/analyze`, `/prompt-composer/*`, `POST /api/v1/agents`) **무변경** — 라우트 등록·계약 회귀 테스트로 못박는다 | P0 |
| **FR-12** | 전 단계 `request_id` 전파 + 구조화 로깅 (단계 시작/종료/degraded 사유) | P1 |
| **FR-13** | 동기 POST 응답에 **`steps[]` 단계별 상태 블록** 포함 — 단계(intent/tools/prompt/create/bind)마다 `status(ok\|degraded\|failed\|skipped)`·`reason`·`elapsed_ms`. 되묻기 응답(`complete=false`)에도 수행된 단계까지의 steps를 담는다 | P0 |
| **FR-14** | **SSE 스트림 엔드포인트** — 같은 입력 계약으로 `stage_started`/`stage_completed`/`stage_failed` 이벤트를 단계 순서대로 실시간 송출하고, 마지막 이벤트로 결과 전문(되묻기 questions 또는 `agent_id`+steps)을 보낸다. 이벤트 wire 포맷은 기존 agent-run SSE 관례를 따른다 | P0 |
| **FR-15** | SSE와 동기 POST의 **결과 의미는 동일**해야 한다 — 같은 입력이면 최종 payload 스키마 동일(전송 방식만 다름). 화면은 어느 쪽으로 호출해도 동일한 단계별 확인·에러 상태를 재구성할 수 있다 | P1 |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 지연 | complete 경로 LLM 최대 3회 순차 — 단계별 타임아웃 설정 존재(기존 `tool_selector_timeout_sec` 등 재사용), 전체 상한 config 관리 | 통합 테스트 + 로그 `elapsed_ms` |
| 관측 | 단계별 degraded 사유·elapsed가 로그와 응답에 남는다 | 로그 필드 검증 테스트 |
| 아키텍처 | Thin DDD 레이어 준수 — 오케스트레이션은 application, 신규 비즈니스 규칙은 domain, 외부 호출은 infrastructure | `verify-architecture` 스킬 |
| 테스트 | TDD — 테스트 선행, 4계층 커버 | `verify-tdd` 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 되묻기 시나리오: 1차 호출 `complete=false`+questions → answers 재호출 → `agent_id` 반환까지 통합 테스트로 완주
- [ ] 미충족 슬롯 없는 요청: 1차 호출만으로 `agent_id` 반환
- [ ] 생성된 `agent_id`가 `GET /api/v1/agents/{agent_id}`로 조회되고, 프롬프트·도구가 초안과 일치
- [ ] `prompt_session`에 `agent_id` 바인딩 확인
- [ ] LLM 3단계 각각 실패 주입 시 200 + 해당 단계 degraded 플래그 (저장 실패 주입 시 5xx)
- [ ] 동기 응답·SSE 최종 이벤트 모두에서 `steps[]`가 실제 수행 이력과 일치 (실패 주입 시 해당 단계 `failed`/`degraded` + 이후 단계 `skipped` 표기)
- [ ] SSE 스트림: 이벤트가 단계 정의 순서대로 도착하고, 실패 단계에서 `stage_failed` 이벤트 후 최종 이벤트로 종료됨을 통합 테스트로 검증
- [ ] 기존 5개 경로 라우트·계약 회귀 테스트 통과 (무변경 증명)

### 4.2 Quality Criteria

- [ ] 신규 모듈 테스트 커버 (domain/application/api) — 테스트 선행 커밋 이력
- [ ] `verify-architecture` / `verify-tdd` / `verify-logging` 통과
- [ ] 회귀 판정은 pass/fail 개수가 아니라 **정렬된 FAILED 목록 diff** 기준 (거짓 초록 게이트 위키 준수)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **R1** 도구선택+프롬프트 규칙 3벌 공존 (AgentComposer / v3 auto / 신규) — 규칙 표류 | High | High | 본 Plan에 수렴 방향 명문화: 신규 경로 검증 후 후속 사이클에서 기존 경로의 내부를 파이프라인 모듈로 교체 검토. 그 전까지 프롬프트 규칙 변경은 prompt_composer 한 곳에만 |
| **R2** 동기 LLM 3회 순차 → 장시간 응답·게이트웨이 타임아웃 | Medium | Medium | 단계별 타임아웃 + 전체 상한 config. 초과 시 해당 단계 degraded 폴백. 실측 후 202 전환은 후속 판단 |
| **R3** `LLMToolSelector`가 대화 필터용(top_k) 설계 — 빌더 문맥(전체 카탈로그 후보, "누락이 과잉보다 나쁨")과 목적 불일치 | Medium | Medium | 어댑터에서 빌더용 파라미터(top_k·프롬프트 문맥) 분리 주입. 사용자 명시 `tool_ids` 항상 포함(FR-03)으로 누락 보상. 품질 미달 시 D2 재검토를 Check에서 판단 |
| **R4** 검토 단계 없는 실제 생성 — 저품질 에이전트가 조용히 만들어짐 | Medium | Medium | degraded 플래그·프롬프트 버전 이력·기존 PATCH 수정 경로로 사후 교정 가능. 프론트 배선 사이클에서 확인 UX 추가 여지 |
| **R5** 되묻기 왕복의 answers/round 클라이언트 신고값 조작 | Low | Low | intent 관례 그대로 — 질문 에코백 + 서버 재clamp (`stateless-hitl-clarification` 패턴) |
| **R6** 신규 경로가 v3 auto 세션 루프와 개념 혼동 | Low | Medium | 위키 경고 준수 — 문서·응답 스키마에서 "세션 없음, stateless"를 명시. v3와 경로·태그 분리 |
| **R7** SSE 연결 끊김·클라이언트 재호출로 **에이전트 중복 생성** — 서버는 진행 상태를 보존하지 않으므로(D7) 끊긴 요청의 생성 성공 여부를 클라이언트가 모른다 | Medium | Medium | 생성 단계를 파이프라인 **마지막**에 배치(끊김 대부분은 생성 전). Design에서 멱등성 장치 검토(예: 클라이언트 `request_key`로 동일 요청 재시도 시 기존 agent_id 반환 — 채택 여부는 Design 확정). 최소한 응답·문서에 재호출 시 중복 가능성 명시 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| 신규 라우터/스키마 (POST + SSE) | API | 추가만 (기존 경로 무변경). SSE 인증은 기존 query-token 관례 재사용 |
| `main.py` | DI 조립 | 신규 UseCase 조립 + 라우터 등록 블록 추가 |
| `tool_selection` | 모듈 | 빌더 문맥 어댑터 **추가** (셀렉터 본체 무변경) |
| 신규 config | Config | 파이프라인 활성화·타임아웃·intent 스펙 관련 설정 추가 |

### 6.2 Current Consumers — 재사용 모듈의 기존 소비자

| Resource | 기존 소비자 | Impact |
|----------|------------|--------|
| `AnalyzeIntentUseCase` | `/intent/analyze` 라우터 | None — 호출자 추가일 뿐, 시그니처 무변경 |
| `LLMToolSelector` | General Chat 미들웨어 (`tool_selector_enabled`) | None — 어댑터 신설, 본체·기존 플래그 무변경 (O6) |
| `ComposePromptUseCase` | `/prompt-composer/*` 라우터 | None — additive 소비자 추가. 시그니처 변경 필요 시 optional 마지막 인자+폴백 관례 준수 |
| `CreateAgentUseCase` | `POST /api/v1/agents` | None — 동일 계약으로 호출 |
| `prompt_session` bind | `PATCH /prompt-composer/sessions/{id}` | Needs verification — 파이프라인 내부 바인딩과 외부 PATCH의 409 계약 충돌 여부 Design에서 확정 |
| `agent_definition` | 스토어/워크스페이스/실행 전 경로 | None — 정규 생성 UseCase 경유이므로 스키마 영향 없음 |

### 6.3 Verification

- [ ] 위 소비자 전부 무변경 회귀 테스트 (FR-11)
- [ ] 인증·소유권 계약 변화 없음
- [ ] 스키마 필드 추가/제거로 기존 쿼리 깨지는 곳 없음 (신규 테이블 0)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (기존 Thin DDD — domain/application/infrastructure/interfaces) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 오케스트레이션 위치 | application UseCase / LangGraph 그래프 / 라우터 직조합 | **application UseCase** | 흐름 제어는 application 책임. 라우터 직조합은 금지 규칙, 그래프는 상태 지속이 없어 과함 |
| 기존 모듈 결합 방식 | UseCase 직접 주입 / 포트 재정의 | **UseCase 직접 주입 (생성자 DI)** | 같은 application 레이어 간 조합. main.py 단일 조립 관례 유지 |
| 되묻기 상태 | 세션 테이블 / stateless 에코백 | **stateless 에코백** | intent 관례·위키 패턴. v3 루프와 차별화 (D3·D7) |
| 실패 정책 | 전파 통일 / 단계별 degraded | **단계별 degraded + 저장만 전파** | 승인된 degraded-vs-failure 경계 패턴 (D6) |
| 진행 상태 전송 | 폴링 세션 / SSE 스트리밍 / WebSocket / 최종 응답만 | **SSE 스트리밍 + 최종 steps 요약 병행** | 폴링은 상태 테이블 필요(D7 위배), WS는 단방향 진행 표시에 과함. SSE는 `run/stream` 검증 관례 존재 (D8) |
| 단계 이벤트 방출 | UseCase 콜백 주입 / async generator | Design에서 확정 | 동기 POST와 SSE가 같은 UseCase를 공유해야 함(FR-15) — 방출 방식이 두 라우트 재사용성을 결정 |

### 7.3 Clean Architecture Approach

```
interfaces(라우터 2: POST/SSE + 스키마) → application/agent_create_pipeline(오케스트레이션 + 단계 이벤트 방출)
  ├─ application/intent.AnalyzeIntentUseCase        (재사용)
  ├─ (신규 포트) 도구추천 ← infrastructure/tool_selection 어댑터(LLMToolSelector 랩)
  ├─ application/prompt_composer.ComposePromptUseCase (재사용)
  └─ application/agent_builder.CreateAgentUseCase     (재사용)
domain: 파이프라인 진행 규칙(단계 전이·병합·degraded 판정) Policy
        + 단계 상태 VO(PipelineStage/StageStatus) + intent 스펙 상수
infrastructure: SSE wire 포매팅은 기존 agent_run SSE 포매터 관례 재사용
```

---

## 8. Convention Prerequisites

- [x] CLAUDE.md 코딩 규칙 (idt/CLAUDE.md — 레이어·40줄·타입·config 하드코딩 금지)
- [x] DB 세션 규칙 `docs/rules/db-session.md` — 한 UseCase 내 단일 세션 (CreateAgent+bind 트랜잭션 경계 Design에서 확정)
- [x] 로깅 규칙 `docs/rules/logging.md` — `exception=e` 관례
- [x] 도구 규칙 `docs/rules/tool-and-mcp.md` — 도구 ID 이중 네임스페이스 주의
- [x] 참조 위키: `stateless-hitl-clarification`(✅) · `degradation-vs-failure-boundary`(✅) · `llm-output-trust-boundary`(✅) · `additive-contract-extension`(📝) · `ast-source-contract-tests`(✅) · `router-map`(✅)
- 신규 환경변수/설정: 파이프라인 활성화 플래그, 빌더용 셀렉터 파라미터, 전체 타임아웃 — Design에서 명명

---

## 9. Next Steps

1. [ ] `/pdca design agent-create-pipeline` — 엔드포인트 경로·응답 스키마(되묻기/완료 구분)·steps/SSE 이벤트 스키마·단계 이벤트 방출 방식(콜백 vs generator)·R7 멱등성 장치·intent 스펙 축·트랜잭션 경계·어댑터 파라미터 확정
2. [ ] 설계 리뷰 (특히 R1 수렴 방향, R3 셀렉터 적합성, R7 중복 생성 방어)
3. [ ] TDD 구현 시작

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-18 | 초안 — 사용자 확정 4건(D1~D4) 반영 | 배상규 |
| 0.2 | 2026-08-18 | 화면용 단계별 확인·에러 상태 전송 추가 — D8(단계 상태 모델 + SSE 스트리밍 + steps 요약), FR-13~15, S6~S7, R7, O7 | 배상규 |
