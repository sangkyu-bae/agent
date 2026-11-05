# agent-token-limit Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: sangplusbot (idt 백엔드 + idt_front)
> **Analyst**: 배상규
> **Date**: 2026-11-05
> **Design Doc**: [agent-token-limit.design.md](../02-design/features/agent-token-limit.design.md)
> **Branch**: `feature/agent-token-limit` (worktree `wt/agent-token-limit`), 커밋 61914f5 → 414899e

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 토큰 한도가 코드 상수 8000으로 전 에이전트 고정이라 긴 수집 1회로 후속 워커가 실행되지 못하고, 한도 종료 사실도 사용자에게 전달되지 않는다. |
| **WHO** | P2 KB 운영자/에이전트 소유자(설정), 최종 사용자(완주된 답변 또는 한도 안내). |
| **RISK** | 기본값 상향으로 비용 상한 완화(반복 한도가 2차 상한), 토큰 가드 `limit_reached` 변경 시 되물음 루프 회귀(기존 테스트 갱신). |
| **SUCCESS** | 재현 런 완주, 설정 왕복, 토큰 도달 안내·플래그 통일, 회귀 통과. |
| **SCOPE** | DB(V085)+도메인 → API → 실행 경로 → 프론트 설정/배지. 집계 방식 변경·서브 상속 복원은 범위 밖. |

---

## Strategic Alignment Check

### Plan Alignment (PRD 없음)

| Element | Expected | Status |
|---------|----------|:------:|
| Core Problem (WHY) | 토큰 한도 단일 소스·조기 종료 안내 | ✅ Addressed — 재현 런이 기본값으로 완주(§2.7 L3-1) |
| Target User (WHO) | 에이전트 소유자가 설정, 사용자가 안내를 받음 | ✅ Addressed — 설정 탭 + 답변 안내/배지 |
| Value | 반복·토큰 한도가 같은 소스·같은 종료 경로 | ✅ Delivered |

### Success Criteria Status

| # | Criteria (Plan §4.1) | Status | Evidence |
|---|---------------------|:------:|----------|
| SC-1 | 재현 시나리오가 기본값 50000으로 토큰 가드 없이 완주 | ✅ Met | 실런 `77a01a91`: scrape_url → data_analysis(+chart_builder) → presentation_generator → final_answer, supervisor LLM 결정 4회, payload에 `limit_reached` 없음, 264s / LLM 28회 224,748 토큰. 동일 질의가 어제(한도 8000)는 스크랩 1회 후 조기 종료(LangSmith 01a1a939). 단위: `test_agent_token_limit_runtime.py::test_token_usage_below_agent_limit_does_not_trigger` |
| SC-2 | 생성→조회→수정→조회→포크 왕복 보존 | ✅ Met | L1 인프로세스 왕복 §2.7 (create 50000 → patch 60000 → get 60000 → patch None 유지). 포크 복사는 `test_fork_agent_use_case.py::test_fork_copies_token_limit`, `test_auto_fork_service.py::test_auto_fork_copies_token_limit` |
| SC-3 | 토큰 도달 시 final_answer 안내 + `limit_reached`·사유 플래그, 워커 미실행도 답변 | ✅ Met | 실런 `99718ab3`(§2.7 L3-3): 가드 로그 → final_answer → payload `limit_reached: true, limit_reason: "token"`, 답변이 한도를 언급. 정적: `supervisor_nodes.py:464-469` → `route_to_worker_or_final`(무변경) → `_render_limit_notice` → latch `run_agent_use_case.py:1509-1513`. 워커 미실행 도달은 단위 `TestRouteWithLimitReached` |
| SC-4 | 서브 에이전트 초기 state `token_limit` = 서브 정의 값 | ✅ Met | `workflow_compiler.py:1492`(`token_limit=sub_agent.token_limit`), `:2958-2963`; 테스트 `TestSubAgentTokenLimit` 3건 (20000 vs 부모 100000, 기본값 폴백, 컴파일 전달) |
| SC-5 | 범위 밖(7999, 500001) API 422, 도메인 ValueError | ✅ Met | L1 §2.7 #2·#3·#6 (422), `test_token_limit_policy.py` (ValueError) |
| SC-6 | 설정 탭 입력·저장·재진입 유지·clamp | ✅ Met (RTL) | `LimitNumberField.test.tsx` 6건, `SettingsPanel.test.tsx` 토큰 섹션 3건, `AgentBuilderPage/index.test.tsx` create 기본값·edit 60000→70000 전송. 브라우저 수동 확인은 미실시 |
| SC-7 | 기존 테스트 전부 통과(상시 실패 제외), 프론트 통과 | ✅ Met | 백엔드 `tests/application/agent_builder` 1324 passed; `tests/api`+`agent_builder` 실패 25건 = master 동일 목록. 프론트 1739 passed, 실패 9건/4파일 = master 동일 파일(10건) |

**Success Rate**: 7/7 Met (SC-6은 RTL 단위 기준, 브라우저 실화면 미확인)

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | 기본 50000 / 8000~500000 | ✅ | — |
| [Plan] | 집계 방식(글자수÷4) 유지 | ✅ | 집계 지점 9곳 무변경 |
| [Plan] | 서브 에이전트 독립 값 | ✅ | `// 2` 제거, 사용량 합산 유지 |
| [Plan] | 포크 복사 | ✅ | — |
| [Design] | Option C (배선 복제 + 정책 + `limit_reason` additive) | ✅ | — |
| [Design] D11 | 사유 없는 도달(구 서버)은 일반 문구 | ⚠️ | `Message`에 `limitReached`가 없어 프론트에서 일반 문구 분기가 도달 불가 (G-1). 현 서버는 항상 사유를 보내므로 실효 영향 없음 |
| [Design] §5.3 | 수정 파일 목록 | ⚠️ | `StudioLayout.tsx`가 누락(핸들러 패스스루 필요) |
| [Design] §4.1 | PUT 응답에 `token_limit` | ⚠️ | `UpdateAgentResponse`는 `max_iterations`도 없는 기존 구조 — 미포함 유지 (G-4) |

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design D1~D12·Page UI Checklist·API 계약과 구현의 일치 여부를 정적으로 대조하고, 로컬 스택(MySQL 3308 + MCP + LLM)에서 L1 API 왕복과 L3 재현 런을 실행해 Plan SC를 실측한다.

### 1.2 Analysis Scope

- Design: `docs/02-design/features/agent-token-limit.design.md`
- 구현: 커밋 2514ebf(DB+도메인), 1ad6191(API), ff8d901(실행 경로), 414899e(프론트)
- 정적 분석: gap-detector 에이전트(읽기 전용) + 본인 검증
- 런타임: 인프로세스 `TestClient(app)` — 실 DB·MCP·LLM 사용, 로컬 DB V085 적용(2026-11-05)

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints

| Design | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| POST /api/v1/agents `token_limit?` | `CreateAgentRequest.token_limit = Field(50000, ge=8000, le=500000)` | ✅ | 응답 `CreateAgentResponse.token_limit` |
| PUT /api/v1/agents/{id} | PATCH `UpdateAgentRequest.token_limit: int \| None` | ✅ | 메서드는 기존 PATCH. 응답에 `token_limit` 없음(G-4, 기존 구조 동일) |
| GET /api/v1/agents/{id} | `GetAgentResponse.token_limit` | ✅ | |
| POST fork | `fork_agent_use_case.py:100`, `auto_fork_service.py:69` | ✅ | |
| WS ANSWER_COMPLETED `limit_reached`, `limit_reason` | `_answer_payload(limit_reached=…, limit_reason=…)` truthy-only | ✅ | `websocket.ts:84-90` 타입 일치 |

### 2.2 Data Model

| Field | Design | Impl | Status |
|-------|--------|------|--------|
| `agent_definition.token_limit` | INT NOT NULL DEFAULT 50000 AFTER max_iterations, COMMENT | V085 동일 + 모델 `comment=` | ✅ |
| `TokenLimitPolicy` | 50000 / 8000 / 500000 | `policies.py:191-209` | ✅ |
| `SupervisorState.limit_reason` | str, 초기 "" | `supervisor_state.py:40`, `build_initial_state` | ✅ |
| `_StreamState.limit_reason` | latch 최초값 | `run_agent_use_case.py:155, 1509-1513` | ✅ |

### 2.3 Component Structure

| Design Component | Implementation | Status |
|------------------|----------------|--------|
| `LimitNumberField` | `settings/LimitNumberField.tsx` | ✅ |
| `SettingsPanel` 토큰 섹션 | `settings/SettingsPanel.tsx:84-108` | ✅ |
| `AgentTestPanel` 패스스루 | `:28, 128-129` | ✅ |
| `AgentBuilderPage` form/전송/핸들러 | `:124, 313, 405, 565` | ✅ |
| `agentDetailMapping` | `:96` | ✅ |
| `limitReachedNotice` | `utils/limitNotice.ts` | ✅ |
| `MessageBubble` 배지 | `:77-81` | ✅ |
| `useAgentRunStream` / `ChatPage` | `:51-52, 173-174` / `:139, 289, 363` | ✅ |
| — (Design 누락) | `StudioLayout.tsx:31, 71, 141` | ⚠️ Design에 추가 필요 |

### 2.4 Functional Depth Analysis

| File | Depth | Placeholder | Missing |
|------|:-----:|-------------|---------|
| 백엔드 변경 14개 | 100 | 없음 | — |
| 프론트 변경 16개 + 신규 2개 | 100 | 없음 | G-1 일반 문구 분기 도달 불가 |

**Shallow File Count**: 0

### 2.5 Page UI Checklist Verification (§5.4)

| Page | Elements | Implemented | Missing | Rate |
|------|:--------:|:-----------:|:-------:|:----:|
| Studio 설정 탭 | 6 | 6 | 0 | 100% |
| 채팅 답변 | 3 | 3 | 0 | 100% |

**Functional Match Rate**: 93% (gap-detector, G-1·G-3 감점)

### 2.6 API Contract Verification

| # | Endpoint/Channel | Design | Server | Client | Contract |
|---|------------------|:------:|:------:|:------:|:--------:|
| 1 | POST /agents (create) | ✅ | ✅ | ✅ | PASS |
| 2 | PATCH /agents/{id} | ✅ | ✅ | ✅ | PASS (응답 필드만 미포함) |
| 3 | GET /agents/{id} | ✅ | ✅ | ✅ | PASS |
| 4 | WS answer_completed | ✅ | ✅ | ✅ | PASS |

**Contract Match Rate**: 92% (gap-detector; PUT 응답·프론트 create 응답 타입 미포함)

### 2.7 Runtime Verification Results

실행 방식: 메인 venv python, cwd=worktree idt, `fastapi.testclient.TestClient(src.api.main.app)` 인프로세스, 로컬 JWT(user 7). 스크립트는 세션 스크래치 `smoke_token_limit.py`.

#### L1: API (TestClient)

| # | Test | Expected | Actual | Pass |
|---|------|----------|--------|:----:|
| 1 | POST create (token_limit 미전달) | 201, 50000 | 201, 50000 | ✅ |
| 2 | POST create 7999 | 422 | 422 | ✅ |
| 3 | POST create 500001 | 422 | 422 | ✅ |
| 4 | GET detail | 200, 50000 | 200, 50000 | ✅ |
| 5 | PATCH 60000 | 200 | 200 | ✅ |
| 6 | PATCH 100 | 422 | 422 | ✅ |
| 7 | PATCH name만 (token_limit None) | 200, 값 유지 | 200 | ✅ |
| 8 | GET after | 60000 | 60000 | ✅ |
| 9 | DELETE (정리) | 204 | 204 | ✅ |
| 10 | DB `agent_definition.token_limit` | INT DEFAULT 50000 | 적용 확인 | ✅ |

**L1 Score**: 10/10 = 100%

#### L2: UI (Vitest + RTL — Playwright 미사용)

| # | Page | Action | Result | Pass |
|---|------|--------|--------|:----:|
| 1 | LimitNumberField | 999 blur / abc Enter / 복원 / 상위 동기화 | 6/6 | ✅ |
| 2 | SettingsPanel | 토큰 섹션 표시·clamp·복원(2번째 버튼) | 3/3 + 기존 11 | ✅ |
| 3 | AgentBuilderPage | create 기본값 50000 전송, edit 60000 프라임→70000 전송 | 2/2 | ✅ |
| 4 | useAgentRunStream | limit 플래그 캡처·부재 기본값 | 2/2 | ✅ |
| 5 | MessageBubble | token/iteration 배지, 스트리밍·사유 없음 미표시 | 3/3 | ✅ |
| 6 | limitNotice / agentDetailMapping | 5/5, 2/2 | | ✅ |

**L2 Score**: 6/6 = 100% (브라우저 실화면 확인은 미실시)

#### L3: 시나리오 (실 에이전트 `df9d0fd2`, 실 MCP 스크랩·LLM)

| # | Scenario | Result | Pass |
|---|----------|--------|:----:|
| 1 | SC-1 기본 50000 | run `77a01a91`: scrape → analysis(+chart) → presentation → final_answer, `limit_reached` 없음, 264s | ✅ |
| 2 | SC-3 token_limit=8000 | run `cbf34be6`: 가드 **미발동** — 이번 스크랩 워커 산출(LLM 요약)이 32k자 미만이라 usage < 8000. scrape → analysis → FINISH, 168s. 집계가 워커 요약 길이에 의존함을 실측 (Plan §1.2 기록과 일치) | ➖ 조건 미충족 |
| 3 | SC-3 강제 (초기 state `token_limit=1`, 코드 무수정) | run `99718ab3`: scrape → supervisor 가드(`token_limit reached` 로그 1회, LLM 미호출, step summary `{"next_worker":"__end__"}`) → final_answer. payload `limit_reached: true, limit_reason: "token"`. 답변 본문이 "한도로 인해 … 재스크래핑을 진행하지 못해"라고 명시하고 미확인 수치를 부족으로 표기. 158s / LLM 7회 | ✅ |
| 4 | SC-2/6 API 왕복 | L1 #1~#8 | ✅ |
| 5 | G-2 프로브 (중첩 그래프 이벤트) | LangGraph 소형 실험: 자식 그래프 supervisor의 `limit_reached=True` chain_end가 부모 `astream_events`에 도달 (`parent_ids` 길이 3, 최상위 노드 1, 최상위 그래프 0) → latch가 서브 한도 도달을 부모 payload에 전파 | ❌ → Act-1에서 수정 (§9) |

**L3 Score**: Act-1 전 3/4 = 75% → Act-1 후 4/4 = 100% (#2는 조건 미충족으로 집계 제외)

**Runtime Match Rate**: Act-1 전 92.5% → 후 (100×0.4 + 100×0.3 + 100×0.3) = 100%

### 2.8 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  97%                 │
│  Functional Match Rate:  93%                 │
│  Contract Match Rate:    92%                 │
│  Runtime Match Rate:     100% (Act-1 후, 전 92.5%) │
│  ─────────────────────────────────────────── │
│  Overall Match Rate:     95.8% (Act-1 후, 전 93.2%) │
│  = (97×0.15) + (93×0.25) + (92×0.25) + (100×0.35) │
└─────────────────────────────────────────────┘
```

### 2.9 Gap List

| # | Severity | Conf. | Gap | 조치 |
|---|----------|:-----:|-----|------|
| G-2 | **Important** | 95% (실험 확인) | `_map_chain_end` latch(`run_agent_use_case.py:1509`)가 중첩 깊이를 보지 않아 서브 에이전트의 토큰/반복 가드가 부모 payload `limit_reached`·`limit_reason`을 세운다. 부모 final_answer에는 안내가 없어 배지와 답변이 어긋남. 반복 한도에도 있던 기존 결함이나 독립 토큰 예산으로 노출 확률 증가 | **Act-1 완료**: `_map_event`가 `nested = len(parent_ids) > 1`을 넘기고 `_map_chain_end`는 `not nested`일 때만 latch. 테스트 `TestNestedLimitLatch` 2건 (중첩 무시·최상위/구 픽스처 유지) |
| G-3 | Important | 55% | V085가 V084(kb-quick-setup 미병합) 앞에 적용될 경우 Flyway 순서 검증 충돌 가능. 로컬은 Flyway 이력 테이블 없이 SQL 직접 적용 | 머지 순서 조율 또는 outOfOrder — 배포 담당 결정, Report에 기록 |
| G-1 | Minor | 95% | 프론트 일반 문구 분기 도달 불가(`Message.limitReached` 없음) | Design §5.2 정정 완료(v0.2) |
| G-4 | Minor | 90% | PATCH 응답·프론트 create 응답 타입에 `token_limit` 없음 | Design §4.2 정정 완료(v0.2) |
| G-5 | Minor | 90% | pytest 수준 HTTP 왕복 테스트 없음 | L1 인프로세스 실측으로 대체(본 문서). pytest 추가는 후속 |
| G-6 | Minor | 85% | Design이 `test_answer_payload_contract` 참조 — 실제 이름 상이 | Design §4.3 정정 완료(v0.2) |
| G-7 | Minor | 80% | ChatPage `view.limitReason → updateMessage` 매핑 테스트 없음 | 후속 |
| G-8 | Minor | 70% | 복원 버튼 2개 aria-label 동일 | 후속(접근성) |

---

## 3. Code Quality Analysis

| 항목 | 결과 |
|------|------|
| 함수 길이 40줄 / if 2단계 | 신규 함수 `TokenLimitPolicy.validate`, `_render_limit_notice`, `LimitNumberField.commitDraft` 모두 10줄 내외 |
| 로깅 | 토큰 가드 warning에 `token_limit` 필드 추가, print 없음 |
| 중복 | 반복·토큰 입력 UI를 `LimitNumberField`로 통합 (기존 중복 제거) |
| Lint/tsc | 수정 파일 lint: master와 동일한 기존 2오류·2경고(AgentBuilderPage set-state-in-effect, ChatPage deps). tsc 기준선 209건 중 `tokenLimit` 관련 신규 0건(픽스처 2곳 보강) |

---

## 5. Test Coverage

| Area | 신규/갱신 테스트 | 결과 |
|------|------------------|------|
| 도메인 | `test_token_limit_policy.py` 16, `test_supervisor_config.py` 갱신 | 통과 |
| 인프라 | repository save/update/row 3 | 통과 |
| 애플리케이션 | 스키마 4, 유스케이스 7, `test_agent_token_limit_runtime.py` 15, 기존 4건 기대값 갱신 | `tests/application/agent_builder` 1324 passed |
| 프론트 | 신규 2파일 11건 + 기존 6파일 보강 14건 | 125 passed (대상 파일) |
| 미커버 | G-2 중첩 latch, G-7 ChatPage 매핑, pytest HTTP 왕복 | — |

---

## 6. Clean Architecture Compliance

| 검사 | 결과 |
|------|------|
| Domain → Infrastructure | 0건 |
| Domain → LangGraph | 0건 |
| Domain → LangChain | 1건(`domain/llm/interfaces.py`, 기존·본 변경 무관) |
| Routes → Infrastructure | 10건(master 동일, 본 변경 무관) |
| Infrastructure Policy 정의 | 0건 |
| 본 기능 레이어 배치 | `TokenLimitPolicy` domain, 주입 application, 매핑 infrastructure — Design §9.4 일치 |

---

## 7. Convention Compliance

- 네이밍 `token_limit` / `tokenLimit` / `TOKEN_LIMIT`, 주석 `agent-token-limit D#` 참조 일관.
- DDL COMMENT 규칙: V085 통과(`test_migration_ddl_comments.py`).
- 컴포넌트 파일 런타임 상수 export 없음(`TOKEN_LIMIT`은 `constants/`).

---

## 8. Recommended Actions

1. ~~Act: G-2 latch 깊이 필터 + 테스트~~ → §9 Act-1 완료.
2. ~~Design 정정 (G-1·G-4·G-6·StudioLayout)~~ → Design v0.2 완료.
3. **Report 기록**: G-3 마이그레이션 순서(kb-quick-setup V084와의 병합 순서), 토큰 집계가 워커 요약 길이에 의존해 같은 질의도 런마다 사용량이 다름(L3-2 실측).
4. **후속**: pytest HTTP 왕복(G-5), ChatPage 매핑 테스트(G-7), 복원 버튼 aria-label(G-8).

---

## 9. Act-1 (사용자 결정 2026-11-05: "G-2 수정 + Design 정정")

| 항목 | 내용 |
|------|------|
| 변경 | `run_agent_use_case.py` `_map_event`: `nested = len(raw.get("parent_ids") or []) > 1` → `_map_chain_end(..., nested=)`; latch 조건에 `not nested` 추가. 다른 캡처(charts·approval·final_state)는 기존대로 |
| 근거 | LangGraph 실험: 최상위 노드 `parent_ids` 1, 최상위 그래프 0, 서브 그래프 노드 3 |
| 테스트 | `TestNestedLimitLatch::test_nested_sub_agent_guard_does_not_latch_parent`, `::test_top_level_guard_still_latches` (parent_ids 부재 픽스처 호환 포함). 대상 4파일 78 passed |
| 문서 | Design v0.2 (D10 Act-1, §4.2, §4.3, §5.2, §5.3) |
| 재집계 | L3 4/4 → Runtime 100% → Overall 95.8% |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-05 | 정적 분석(gap-detector) + L1/L3 실측 | 배상규 |
| 0.2 | 2026-11-05 | Act-1 (G-2 latch 깊이 필터) 반영, Design v0.2 정정 | 배상규 |
