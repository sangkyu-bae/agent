# approval-gate Planning Document

> **Summary**: 에이전트가 되돌릴 수 없는 부작용을 실행하기 직전 `pending`으로 영속 기록하고, 사람이 승인해야만 집행하는 공통 승인 게이트. **승인 시각과 집행 시각을 분리**해 무인 시간대 작업을 지원하고, 기존 미들웨어 카탈로그에 편입해 **에이전트별로 켜고·끄고·설정**한다.
>
> **Project**: sangplusbot (idt)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-20
> **Status**: Draft (v0.2)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트가 되돌릴 수 없는 부작용(이메일 발송, 금리 변경, 건의사항 답변)을 사람 검증 없이 실행한다. 스케줄·웹훅은 사람이 화면 앞에 없어 확인조차 불가능하다. 그렇다고 새벽 00시 작업 때문에 사람을 깨울 수는 없고, 도구마다 승인 로직을 따로 짜면 관리가 흩어진다. |
| **Solution** | 도구 호출을 미들웨어로 가로채 `approval_request`에 **초안 + 멈춘 지점 스냅샷**을 적재하고 런은 정상 종료한다. 승인은 **"집행 허가"일 뿐** — 실제 집행은 `execute_after`가 지정한 시각에 스케줄러가 수행한다. 게이트 자체는 기존 미들웨어 카탈로그의 6번째 타입으로 편입해 에이전트별로 설정하고, 관리자는 `is_enforced`로 강제한다. |
| **Function/UX Effect** | 담당자가 **깨어 있을 때** 초안을 확인·승인하고, 집행은 새벽에 자동으로 일어난다. 작업함(벨)에 '승인 대기' 탭이 생긴다. 거절 시 사유가 에이전트에 주입되어 대안을 찾는다. 에이전트 설정 화면에서 승인 게이트를 켜고 만료·집행시각을 조절한다. |
| **Core Value** | **비가역 행동에 사람의 최종 판단을 구조적으로 강제**하되, 사람을 기계의 시간표에 묶지 않는다 — 판단은 사람의 시간에, 집행은 시스템의 시간에. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트의 비가역 부작용이 사람 검증 없이 실행된다. 동시에 새벽 집행 작업 때문에 사람을 그 시각에 묶어두는 것도 비효율이다. |
| **WHO** | P2 KB 운영자/에이전트 소유자(설정·승인) + 관리자(강제 정책) |
| **RISK** | 승인 중복 클릭에 의한 **이중 집행**. 예약 집행 시각까지 대기하는 동안 스냅샷·초안이 낡음. |
| **SUCCESS** | 게이트 도구는 승인 없이 **0회** 실행되고, 승인 후 지정 시각에 정확히 1회 집행되며, 런이 멈춘 지점부터 이어져 최종 답변까지 도달한다. |
| **SCOPE** | Phase 1(이번): 게이트 골격 + 미들웨어 편입 + 승인 API + 예약 집행 + 재개 + 작업함 탭(집행기 mock). Phase 2: 실제 이메일·금리·게시 도구. Phase 3: 자동 승인 조건식. |

---

## 1. Overview

### 1.1 Purpose

에이전트 실행 중 **비가역 부작용** 직전에 사람의 승인을 받는 공통 게이트를 만든다. 승인 대기 중에도 런은 정상 종료하고, 집행은 지정 시각에, 재개는 멈춘 지점부터 한다.

### 1.2 Background

- 현재 내부 도구 10종은 전부 읽기/생성 계열이라 부작용이 없다. 그러나 **MCP 도구**와 앞으로 붙일 이메일·금리 변경·게시 도구는 비가역이다.
- `/api/v1/webhooks/agents/{id}`(공개 웹훅)와 cron 기반 스케줄(`agent_schedule`, `next_run_at`/`scheduled_for`)이 이미 동작 중이라, **사람이 화면 앞에 없는 실행 경로가 실재**한다.
- **무인 시간대 문제**: 금리 변경은 새벽 00시에 반영되어야 한다. 게이트가 "승인 즉시 집행"이면 담당자가 00시에 깨어 있어야 한다. 그러나 이런 작업은 **판단(무엇으로 바꿀지)과 집행(언제 반영할지)이 분리 가능**하다 — 저녁에 초안을 만들어 승인받고, 00시에 집행하면 된다.
- **에이전트별 제어 요구**: 모든 에이전트가 승인을 원하지는 않는다. 다행히 `domain/middleware/`에 카탈로그 기반 에이전트별 미들웨어 설정 인프라가 이미 있다 — `MiddlewareCatalogEntry(is_builtin, is_enforced, default_config)` + `AgentMiddlewareRecord(agent_id, config)` + `MiddlewareConfigPolicy.validate()`. 승인 게이트를 여기 편입하면 설정 UI·검증·강제 정책이 전부 따라온다.
- 기존 되묻기 3종(compose / pipeline / v3-auto)은 *정보 부족*을 푸는 무상태 왕복이라 재사용할 수 없다. 승인은 영속·비동기·제3자 개입이라 요구사항이 정반대다.
- LangChain `HumanInTheLoopMiddleware` / LangGraph `interrupt()`는 checkpointer를 요구하는데 현재 코드베이스에 checkpointer는 **0건**이다.

### 1.3 Related Documents

- 위키: `backend/patterns/builtin-tools-optout-channel.md` — 관리자 토글 SoT 이원화 + **구조적 우회 차단**(§4) 선례
- 위키: `backend/patterns/supervisor-graph-contracts.md` — 워커 산출물 = `AIMessage(name)` 1건 계약 (재개 설계의 근거)
- 위키: `backend/patterns/stateless-hitl-clarification.md` — 되묻기 패턴. **본 기능과 별개**임을 명시하기 위한 참조
- 위키: `ops/migration-deploy-deps.md` — 신규 V071~V073 배포 의존성 등재 대상
- 코드: `src/domain/middleware/entities.py`, `config_policy.py` — 편입 대상 카탈로그
- 코드: `src/domain/agent_schedule/` — `claim_due` 선점 패턴 (집행 스케줄러가 재사용)

---

## 2. Scope

### 2.1 In Scope

**게이트 코어**
- [ ] `domain/approval/` — `ApprovalRequest` 엔티티 + 상태 기계 + `ApprovalPolicy`
- [ ] `approval_request` 테이블 (V071) + `tool_catalog.requires_approval` 컬럼 (V072)
- [ ] `ApprovalGateMiddleware` — 도구 호출 가로채 pending 적재 후 정상 ToolMessage 반환
- [ ] 승인 도구 **단독 워커 제약** — 에이전트 생성 시 구조 검증
- [ ] 승인 / 거절 API + `ApprovalPolicy.can_decide`(에이전트 소유자)
- [ ] `ActionExecutorInterface` + **mock 집행기** (멱등 계약 포함)

**에이전트별 제어 (신규 v0.2)**
- [ ] `MiddlewareType.APPROVAL_GATE` — 기존 카탈로그 6번째 타입으로 편입 (V073 시드)
- [ ] `MiddlewareConfigPolicy.validate` 분기 추가 — config 키 검증
- [ ] 에이전트별 config: `mode` / `execute_after` / `expires_hours` / `on_expire`
- [ ] `is_enforced` 강제 — 관리자가 켜면 소유자 설정과 무관하게 적용

**예약 집행 (신규 v0.2)**
- [ ] `approval_request.execute_after` — 승인 시각과 집행 시각 분리
- [ ] 집행 스케줄러 — `claim_due` 선점 패턴으로 due 건 집행 (`agent_schedule` 재사용)
- [ ] `approved → scheduled → executed` 상태 추가

**재개**
- [ ] 재개 스냅샷 — `SupervisorState` 직렬화 저장/복원
- [ ] 재개 런 — 집행 결과(또는 거절 사유) 주입 후 supervisor 재진입
- [ ] 만료(`expires_at`) + 에이전트 버전 검증
- [ ] 런당 활성 pending 1건 (순차)

**UI / 확장 지점**
- [ ] 작업함(`JobsPage`) '승인 대기' 탭 + 벨 배지(`unseen-count`) 연동
- [ ] 에이전트 설정 화면에 승인 게이트 미들웨어 노출 (기존 미들웨어 UI 경로 재사용)
- [ ] `ApprovalGateInterface` Protocol — 향후 LangGraph interrupt 구현체 DI 교체 지점

### 2.2 Out of Scope

- **실제 이메일 발송 / 금리 변경 / 건의사항 답변 게시 도구** — Phase 2
- **자동 승인 조건식** (예: 변동폭 ±0.25% 이내 자동 통과) — Phase 3. 조건식 DSL 설계가 별도 과제
- **타임아웃 자동 승인** — 만료는 `expired`로만 처리, 자동 승인 없음
- LangGraph checkpointer 도입 및 `interrupt()` 기반 재개 — Protocol 자리만 남김
- 역할 기반(부서장) 승인자 모델 — `can_decide` 확장 지점만 열어둠
- 초안 **수정 후 승인** — 이번엔 승인/거절 2택
- 한 런에서 승인 **일괄** 처리 — 순차만
- 기존 되묻기 3종 리팩터링 — 손대지 않음

---

## 3. Requirements

### 3.1 Functional Requirements

#### 게이트 코어

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `ApprovalRequest` 상태 기계: `pending → approved → scheduled → executed` / `pending → rejected` / `pending → expired` / `scheduled → failed`. 역방향·건너뛰기 전이 금지 | High | Pending |
| FR-02 | `requires_approval` 플래그 — `ToolMeta.requires_approval_default`(신규 DB 시드) + `tool_catalog.requires_approval`(런타임 SoT). upsert UPDATE 절에서 제외해 sync가 관리자 설정을 덮지 않음 | High | Pending |
| FR-03 | `ApprovalGateMiddleware`가 게이트 도구 호출을 가로채 `pending` 적재 후, 워커에 `"승인 대기 등록됨(approval_id=…)"` ToolMessage 반환. **실제 도구는 호출하지 않음** | High | Pending |
| FR-05 | **단독 워커 제약** — `requires_approval` 도구는 워커에 단독으로만 배치 가능. 다른 도구와 묶으면 에이전트 생성/수정 시 거부 | High | Pending |
| FR-06 | 런당 활성 pending은 **1건**. 두 번째 게이트 도달 시 그 런은 즉시 종료 | High | Pending |
| FR-07 | `GET /api/v1/approvals` / `POST /api/v1/approvals/{id}/approve` / `POST /api/v1/approvals/{id}/reject` | High | Pending |
| FR-08 | `ApprovalPolicy.can_decide(user, request)` — 기본은 `agent_definition.user_id == user.id`. 역할 기반 확장을 위해 **Policy 단일 지점**으로 격리 | High | Pending |
| FR-09 | `ActionExecutorInterface` + `MockActionExecutor`. 실도구는 Phase 2에서 구현체만 추가 | High | Pending |
| FR-10 | **멱등 집행** — `idempotency_key` 유니크 + 조건부 UPDATE(영향 행 0이면 중단). 승인 2회 클릭 → 집행 1회 | High | Pending |
| FR-16 | 감사 로그 — `decided_by` / `decided_at` / 집행 성공·실패 영속 | High | Pending |

#### 에이전트별 제어 *(신규 v0.2)*

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-18 | `MiddlewareType.APPROVAL_GATE = "approval_gate"` 추가 + `middleware_catalog` 시드 행(V073). 기존 4종과 동일한 조립 경로(`_middleware_provider.prepare` → `AppliedMiddleware`)로 흐름 | High | Pending |
| FR-19 | `MiddlewareConfigPolicy.validate`에 `APPROVAL_GATE` 분기 추가. 허용 키: `mode`(`always`\|`off`), `execute_after`(cron 또는 null), `expires_hours`(1~720), `on_expire`(`expire` 고정). 미지정 키는 `_reject_unknown_keys`로 거부 | High | Pending |
| FR-20 | **강제 정책** — `middleware_catalog.is_enforced=true`면 `AgentMiddlewareRecord` 유무·`mode=off`와 무관하게 게이트 적용. 기존 "스냅샷 ∪ enforced 병합" 시맨틱 그대로 사용 | High | Pending |
| FR-21 | 게이트 발동 조건 = `도구.requires_approval` **AND** (`에이전트에 미들웨어 적용` **OR** `is_enforced`). 두 축의 합성 규칙을 Policy 단일 지점에 명시 | High | Pending |
| FR-22 | 에이전트 설정 화면에 승인 게이트 노출 — 기존 미들웨어 설정 UI 경로 재사용. `is_enforced`인 항목은 읽기 전용으로 표시 | Medium | Pending |

#### 예약 집행 *(신규 v0.2)*

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-23 | `approval_request.execute_after: datetime \| None`. 승인 시 config의 `execute_after` cron으로 다음 집행 시각을 계산해 기록. null이면 **즉시 집행**(기존 동작) | High | Pending |
| FR-24 | 집행 스케줄러 — `execute_after <= now` 이고 `status='scheduled'` 인 건을 **선점(claim)** 후 집행. `agent_schedule`의 `claim_due` 트랜잭션 패턴 재사용 (다중 워커 중복 집행 방지) | High | Pending |
| FR-25 | 집행 실패 시 `failed` + 사유 기록. 재시도는 사람이 재승인하는 경로로만 (자동 재시도 없음 — 비가역 작업에 자동 재시도는 위험) | High | Pending |
| FR-26 | 예약 대기 중 만료 검사 — `expires_at < execute_after`면 승인 시점에 **거부**하고 설정 오류를 알림 (영원히 집행 안 되는 조합 차단) | Medium | Pending |

#### 재개

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-04 | pending 적재 시 `resume_snapshot`에 워커 진입 시점 `SupervisorState` 전체를 JSON 직렬화 저장 | High | Pending |
| FR-11 | 재개 런 — 스냅샷 복원 + 집행 결과를 `AIMessage(name=worker_id)`로 주입 + supervisor 노드부터 재진입. **집행 완료 후**에 트리거 | High | Pending |
| FR-12 | 거절 시 `"이 작업은 거절됨(사유: …)"`을 동일 방식으로 주입해 재개 | High | Pending |
| FR-13 | `expires_at`(config `expires_hours`, 기본 168h) 경과 시 `expired`. 만료 건은 승인 불가 | Medium | Pending |
| FR-14 | 승인 **및 집행** 시점에 `agent_definition.updated_at`을 스냅샷 기록값과 대조. 변경됐으면 재개 거부하고 "집행만" 경로 제안 | Medium | Pending |
| FR-15 | `JobsPage` '승인 대기' 탭 + 초안 미리보기 + 승인/거절. `unseen-count`에 pending 합산 | High | Pending |
| FR-17 | `ApprovalGateInterface` Protocol — `StatelessGate`(이번) / `InterruptGate`(향후) DI 교체 지점 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 안전성 | 게이트 도구는 승인 없이 **0회** 실행 — 프롬프트가 아닌 **접근 경로 분리**로 보장 | 우회 시도 회귀 테스트 |
| 멱등성 | 동일 `approval_id` 승인 N회 + 스케줄러 다중 워커 → 집행 정확히 1회 | 동시 승인 10회 + 동시 claim 5워커 테스트 |
| 강제 불가역성 | `is_enforced=true`인 게이트는 어떤 에이전트 설정으로도 비활성화 불가 | `mode=off` + enforced 조합 테스트 |
| 무회귀 | 게이트 도구 미보유 에이전트는 동작·성능·응답 형태 **완전 동일** | 기존 agent_builder 테스트 전량 통과 |
| 예약 정확도 | `execute_after` 기준 집행 지연 ≤ 스케줄러 tick 주기 | 스케줄러 tick 주기 문서화 + 통합 테스트 |
| 스냅샷 용량 | `resume_snapshot` ≤ 256KB (초과 시 messages 절단 후 경고) | 단위 테스트 + 컬럼 상한 |
| 레이어 | `domain/approval/`은 외부 API·DB·LangChain 미참조 | `/verify-architecture` |
| 로깅 | 게이트 발동·승인·거절·예약·집행 전 구간 `request_id` 전파 | `/verify-logging` |
| DDL | 신규 테이블·전 컬럼 COMMENT 필수 | `tests/db/test_migration_ddl_comments.py` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-26 구현 완료 (High 전부, Medium 포함)
- [ ] TDD 준수 — 테스트 선작성 → 실패 확인 → 구현
- [ ] **즉시 집행 E2E**: 게이트 도구 에이전트 실행 → pending + 런 정상 종료 → 승인 → 집행 → 재개 → 최종 답변 도달
- [ ] **예약 집행 E2E** *(금리 시나리오)*: `execute_after` 설정 에이전트 → 저녁 실행 → pending → 승인(`scheduled`) → 시각 도달 → 스케줄러 집행 → 재개
- [ ] **거절 시나리오**: 거절 → 사유 주입 재개 → 에이전트가 사유를 담아 마무리
- [ ] **우회 차단**: 승인 없이 실도구 미호출 회귀 테스트
- [ ] **강제 정책**: `is_enforced` + `mode=off` → 게이트 적용됨
- [ ] **멱등**: 동시 승인 10회 → 집행 1회 / 동시 claim 5워커 → 집행 1회
- [ ] V071~V073 마이그레이션 + 전 컬럼 COMMENT
- [ ] 프론트 '승인 대기' 탭 + 에이전트 설정 노출, Vitest + MSW

### 4.2 Quality Criteria

- [ ] `/verify-architecture` `/verify-logging` `/verify-tdd` 전부 통과
- [ ] 기존 테스트 무회귀 (특히 `tests/application/agent_builder/`, `tests/domain/middleware/`)
- [ ] 함수 40줄·if 2단계 규칙 준수
- [ ] API 계약 동기화 — `idt_front/src/types/` + `constants/api.ts`

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **이중 집행** — 승인 2회 클릭 또는 스케줄러 다중 워커 | High | High | `idempotency_key` 유니크 + 조건부 UPDATE + `claim_due` 선점 패턴. **처음부터** 넣는다 |
| **LLM의 게이트 우회** | High | Medium | 프롬프트 방어 금지. 미들웨어 레이어에서 실도구 호출 자체를 대체. 위키 `builtin-tools-optout-channel` §4와 동형 |
| **예약 대기 중 초안이 낡음** — 저녁 승인, 00시 집행 사이 전제가 바뀜 | High | Medium | 집행 시점에도 `agent_definition.updated_at` 재검증(FR-14). 초안에 `생성 시각` 명시. Phase 3의 자동 승인 조건식이 근본 해법 |
| **영원히 집행 안 되는 조합** — `expires_at < execute_after` | Medium | Medium | 승인 시점에 조합 검증 후 거부(FR-26) |
| **집행 실패 후 방치** — 00시에 실패했는데 아침까지 아무도 모름 | Medium | Medium | `failed` 상태를 작업함 벨에 노출. 자동 재시도는 하지 않음(FR-25) — 비가역 작업이므로 사람 재판단 필요 |
| **낡은 스냅샷 재개** | Medium | Medium | `expires_at` + `updated_at` 대조. 불일치 시 재개 거부, 집행만 제안 |
| **강제 정책의 역효과** — 관리자가 enforced로 켜서 전 에이전트가 멈춤 | Medium | Low | `is_enforced`는 **도구가 `requires_approval`일 때만** 발동(FR-21 합성 규칙). 부작용 없는 도구만 쓰는 에이전트는 무영향 |
| **단독 워커 제약이 사용성을 해침** | Medium | Medium | 검색 워커와 발송 워커를 분리하면 해결되고 supervisor가 순차 라우팅. 에러 메시지로 권장 구조 안내 |
| **미들웨어 config 확장이 기존 4종을 깨뜨림** | Medium | Low | `MiddlewareConfigPolicy.validate`는 `match` 분기 — 신규 case 추가만. `_reject_unknown_keys`로 기존 타입 검증 불변 |
| **스냅샷 비대** | Medium | Medium | 256KB 상한 + messages 절단. LONGTEXT |
| **기존 에이전트 회귀** | High | Low | 게이트 도구 미보유 시 미들웨어 미주입 → 기존 경로와 코드 동일 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `approval_request` | DB Table (신규 V071) | 승인 요청 + 재개 스냅샷 + `execute_after` |
| `tool_catalog.requires_approval` | DB Column (신규 V072) | 도구 축 런타임 SoT. 관리자 토글 |
| `middleware_catalog` | DB Row (신규 V073 시드) | `approval_gate` 타입 행 추가 (`is_enforced` 기본 false) |
| `MiddlewareType` (`domain/middleware/entities.py`) | Domain Enum | `APPROVAL_GATE` 추가 — **4종 → 5종** |
| `MiddlewareConfigPolicy.validate` | Domain Policy | `APPROVAL_GATE` case 분기 추가 |
| `ToolMeta` | Domain Schema | `requires_approval_default: bool = False` 추가 |
| `ToolCatalogModel` / repository upsert | Infrastructure | 컬럼 추가 + **UPDATE 절에서 제외**(보존 계약) |
| `workflow_compiler.py` | Application | 미들웨어 조립에 `ApprovalGateMiddleware` 합류 |
| `CreateAgentUseCase` / Update | Application | 단독 워커 제약 검증 추가 |
| `RunAgentUseCase` | Application | pending 발생 시 응답 플래그 + 재개 진입점 |
| 집행 스케줄러 | Application (신규) | `claim_due` 패턴 재사용 |
| `JobsPage` + 벨 배지 | Frontend | '승인 대기' 탭, unseen-count 합산 |
| 에이전트 미들웨어 설정 UI | Frontend | `approval_gate` 항목 + enforced 읽기 전용 표시 |
| `idt_front/src/types/` + `constants/api.ts` | Frontend | 승인 API 타입·엔드포인트 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `MiddlewareType` (4종) | READ | `MiddlewareConfigPolicy.validate` match 분기 | **None** — case 추가만, 기존 분기 불변 |
| `MiddlewareType` (4종) | READ | `MiddlewareBuilder` 인스턴스화 (application) | Needs verification — 신규 타입 미처리 시 KeyError 가능. 기본 분기 확인 필요 |
| `MiddlewareType` (4종) | READ | `middleware_catalog_router` (관리자 목록) | Needs verification — 응답에 신규 타입 등장, 프론트 렌더 확인 |
| `AppliedMiddleware` 병합 | READ | `_middleware_provider.prepare(agent_id, …)` | Needs verification — "스냅샷 ∪ enforced" 로직에 신규 타입 편승 |
| `_instantiate(plan)` | CREATE | `workflow_compiler:677`, `:713` | Needs verification — `plan.instantiate()`가 신규 타입을 알아야 함. 워커당 새 인스턴스 규칙(builtin-middleware D6) 준수 |
| **v2 실험 경로** `domain/middleware_agent/MiddlewareType` | READ | `middleware_agent/` (summarization, pii, …) | Needs verification — **동명이인 Enum 2개 존재**. 어느 쪽에 추가할지 Design에서 확정 (카탈로그 = `domain/middleware/` 쪽이 유력) |
| `tool_catalog` | READ | `ComposeAgentUseCase._collect_candidates` | **None** — 컬럼 추가만 |
| `tool_catalog` | READ | `workflow_compiler._load_catalog_metadata` | Needs verification — `requires_approval` 동승 |
| `tool_catalog` | UPDATE | `tool_catalog_repository` upsert UPDATE 분기 | **Breaking 주의** — SET 절에 넣으면 sync가 관리자 토글을 덮음. `is_builtin`과 동일 처리 + SQL 컴파일 검사 테스트 |
| `tool_catalog` | READ | `tool_catalog_router` (관리자 도구 목록) | Needs verification — 응답 스키마 확장 시 프론트 동기화 |
| `ToolMeta` | READ | `get_all_tools()` — composer 후보·빌트인 주입·워커 상한 | **None** — 기본값 False |
| 에이전트 생성 | CREATE | `CreateAgentUseCase` Step 2.7(빌트인 주입) **이후** | Needs verification — 주입으로 단독 워커 제약이 깨질 수 있어 검증 순서 중요 |
| 에이전트 생성 | CREATE | compose / pipeline / v3-auto 3경로 | Needs verification — 전부 `CreateAgentUseCase` 경유인지 확인 필요 |
| 스케줄 선점 | UPDATE | `ScheduleRepository.claim_due` (트랜잭션은 호출측) | Needs verification — 집행 스케줄러가 같은 패턴을 **복제**할지 추상화를 공유할지 |
| 런 실행 | CREATE | `webhook_public_router`, 스케줄 실행, `background_job` | Needs verification — pending 종료 런의 job status 표현 |
| 벨 배지 | READ | `/api/v1/jobs/unseen-count` → `AppSidebar` 등 | Needs verification — 의미 확장이 기존 소비자를 깨지 않는지 |

### 6.3 Verification

- [ ] 위 소비자 전부 제안 변경과 호환 확인
- [ ] **`MiddlewareType` 동명이인 2개** 중 편입 대상 확정 및 다른 쪽 무영향 확인
- [ ] `MiddlewareBuilder`가 미지원 타입을 만났을 때의 기존 동작(예외 vs 무시) 확인
- [ ] `tool_catalog` upsert 보존 계약 테스트 추가 (V054 선례와 동형)
- [ ] 에이전트 생성 3경로가 모두 단독 워커 검증을 통과하는지
- [ ] 게이트 도구 0개 에이전트의 실행 경로가 기존과 동일한지
- [ ] `unseen-count` 의미 변경이 프론트 기존 소비자를 깨지 않는지

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| Starter | 단순 구조 | ☐ |
| Dynamic | 기능 단위 모듈, BaaS | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DI | ☑ |

기존 Thin DDD 유지.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 집행 모델 | A 제안→승인→집행 / B interrupt 재개 / A+Protocol | **A + Protocol** | checkpointer 0건. `SupervisorState`가 평면 직렬화 가능해 수동 스냅샷으로 재개 달성. B 여지는 `ApprovalGateInterface`로 보존 (`PlannerInterface` D9 선례) |
| 게이트 위치 | 도구 미들웨어 / 전용 초안도구+집행기 / supervisor 노드 | **도구 미들웨어** | `create_agent(middleware=…)` 체인 재사용. `requires_approval` 플래그 하나로 모든 도구에 일반 적용 |
| **에이전트별 제어** | 신규 설정 테이블 / **기존 미들웨어 카탈로그 편입** / 전역 고정 | **카탈로그 편입** | `MiddlewareCatalogEntry(is_builtin, is_enforced, default_config)` + `AgentMiddlewareRecord` + `MiddlewareConfigPolicy`가 이미 원하는 구조. 신규 테이블·검증·UI를 만들 이유가 없다 |
| **집행 시각** | 승인 즉시 / **예약 집행(execute_after)** / 자동 승인 조건식 | **예약 집행** | 금리 변경처럼 "판단은 미리, 반영은 정시"인 작업이 실재. 사람을 기계의 시간표에 묶지 않는다. 조건식(Phase 3)보다 먼저 필요하고 훨씬 단순 |
| **강제 정책** | 소유자 자율 / **관리자 강제(is_enforced)** / 도구 단위 고정 | **관리자 강제** | 안전 기능의 끌 권한을 당사자에게 주지 않는다. 기존 `is_enforced` 필드와 "스냅샷 ∪ enforced" 병합 시맨틱을 그대로 사용 |
| 게이트 발동 조건 | 도구 축만 / 에이전트 축만 / **합성** | **합성(FR-21)** | `도구.requires_approval` AND (`에이전트 적용` OR `enforced`). 도구 축은 "무엇이 위험한가", 에이전트 축은 "누가 통제받는가" — 직교하므로 둘 다 필요 |
| 재개 단위 | 워커 1홉 / react 루프 내부 / 워커 전체 재실행 | **워커 1홉** | 위키 "워커 산출물=`AIMessage(name)` 1건" 계약 덕에 내부 트레이스 복원 불필요. 단독 워커 제약이 유실 가능성을 구조적으로 제거 |
| 승인자 | 요청자 / **에이전트 소유자** / 역할 / 지정 | **에이전트 소유자** | `agent_definition.user_id` 재사용. `ApprovalPolicy.can_decide` 단일 지점 격리로 역할 기반 확장 대비 |
| 다중 승인 | **순차** / 일괄 / 1건 제한 | **순차** | 런당 활성 pending 1건 불변식이 동시성 문제를 통째로 제거 |
| 집행 실패 | 자동 재시도 / **사람 재판단** | **사람 재판단** | 비가역 작업의 자동 재시도는 이중 집행 위험. `failed`를 벨에 노출 |
| 플래그 SoT | 코드 상수 / DB 토글 / **이원화** | **이원화** | `tool_catalog.requires_approval`(런타임) + `ToolMeta` 기본값(시드). V054 `is_builtin`과 동형 |
| 거절 처리 | 런 종료 / **사유 주입 재개** / 수정 후 승인 | **사유 주입 재개** | 승인 경로와 동일 메커니즘 재사용 |
| 우회 차단 | 프롬프트 / **구조** | **구조** | 위키 `builtin-tools-optout-channel` §4 — 프롬프트 방어는 LLM이 뚫는다 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

src/domain/approval/
  entity.py        ApprovalRequest, ApprovalStatus, ResumeSnapshot(VO)
  policies.py      ApprovalPolicy.can_decide / is_expired / next_status
                   / should_gate(tool, applied_middleware)   ← FR-21 합성 규칙
  interfaces.py    ApprovalRepositoryInterface, ActionExecutorInterface

src/domain/middleware/              ← 기존 파일 확장
  entities.py      MiddlewareType.APPROVAL_GATE 추가
  config_policy.py APPROVAL_GATE case 추가

src/application/approval/
  gate_interface.py    ApprovalGateInterface (Protocol)  ← B 교체 지점
  gate_middleware.py   ApprovalGateMiddleware (StatelessGate)
  decide_use_case.py   승인/거절 → 예약 또는 즉시 집행
  execute_scheduler.py due 건 선점 후 집행 (claim_due 패턴)
  resume_use_case.py   스냅샷 복원 + 결과 주입 + 그래프 재진입

src/infrastructure/approval/
  models.py            ApprovalRequestModel
  repository.py        ApprovalRepository (claim_due 포함)
  mock_executor.py     MockActionExecutor

src/interfaces/schemas/approval.py   요청/응답 DTO
src/api/routes/approval_router.py    /api/v1/approvals

db/migration/
  V071__create_approval_request.sql
  V072__add_requires_approval_to_tool_catalog.sql
  V073__seed_approval_gate_middleware.sql

idt_front/src/pages/JobsPage/ApprovalTable.tsx   (+ 탭)
idt_front/src/types/approval.ts
idt_front/  (에이전트 미들웨어 설정 화면에 approval_gate 노출)
```

**에이전트별 config 형태 (안)**

```json
{
  "mode": "always",          // always | off  (enforced면 off 무시)
  "execute_after": null,     // cron 문자열 또는 null(즉시 집행)
  "expires_hours": 168,      // 1 ~ 720
  "on_expire": "expire"      // 현재 고정값
}
```

금리 변경 에이전트 예시: `{"mode":"always", "execute_after":"0 0 * * *", "expires_hours":24}`
→ 저녁 실행 → 초안 pending → 담당자 승인 → **다음 00:00에 자동 집행** → 재개.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 3종 / `idt/docs/rules/` 7종
- [x] `docs/wiki/_INDEX.md`
- [x] Flyway 마이그레이션 + DDL COMMENT 강제 테스트
- [x] pytest / Vitest + RTL + MSW
- [x] 미들웨어 카탈로그 + config 검증 (`MiddlewareConfigPolicy`)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 도구 메타 확장 | exists (`is_builtin`, `category`) | `requires_approval` 동형 추가 + upsert 보존 계약 테스트 | High |
| 미들웨어 타입 추가 | exists (4종) | **신규 타입 추가 절차** — Enum + Policy case + 카탈로그 시드 + Builder 분기 4곳 동시 갱신 체크리스트 | High |
| `MiddlewareType` 이원화 | 동명이인 2개 (`middleware/` vs `middleware_agent/`) | 어느 쪽이 정식인지 확정 + 위키 등재 | High |
| 미들웨어 조립 순서 | exists (`_instantiate` + budget) | 게이트의 체인 내 **순서** 규약 (budget 앞/뒤) | High |
| 상태 기계 표현 | 관례 부재 | `ApprovalStatus` 전이 규칙을 Policy 단일 지점에 | Medium |
| 스냅샷 직렬화 | 없음 | LangChain messages 직렬화 방식(`dumpd`/`load`) + 스키마 버전 필드 | High |
| 멱등 키 | 없음 | `idempotency_key` 생성 규칙 (run_id + worker_id + tool_call_id) | High |
| 선점 패턴 재사용 | exists (`claim_due`) | 복제 vs 공용 추상화 결정 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `APPROVAL_DEFAULT_EXPIRES_HOURS` | 만료 기본값 (168) — 카탈로그 `default_config` 시드에 사용 | Server | ☑ |
| `APPROVAL_SNAPSHOT_MAX_BYTES` | 스냅샷 상한 (262144) | Server | ☑ |
| `APPROVAL_EXECUTOR_TICK_SECONDS` | 집행 스케줄러 tick 주기 | Server | ☑ |

> `domain`은 env를 읽지 않는다 — 어댑터가 config에서 읽어 Policy에 주입 (`SlotLimits` 선례).

### 8.4 Pipeline Integration

해당 없음.

---

## 9. Next Steps

1. [ ] `/pdca design approval-gate` — 3가지 아키텍처 옵션 비교 후 확정
2. [ ] Design에서 확정할 미결 항목:
   - **`MiddlewareType` 동명이인 2개 중 편입 대상** (`domain/middleware/` 유력) + 다른 쪽 처리
   - `MiddlewareBuilder`가 신규 타입을 인스턴스화하는 경로 (게이트는 repo 의존성이 필요 → DI 주입 방식)
   - 미들웨어 체인 내 게이트 **순서** (tool_call_budget 앞/뒤)
   - `resume_snapshot` 직렬화 포맷 + 스키마 버전 전략
   - 집행 스케줄러를 `agent_schedule` 워커에 합칠지 독립 tick으로 둘지
   - pending / scheduled 런의 `background_job.status` 표현
   - `unseen-count` 확장 방식 (합산 vs 별도 카운트)
   - 에이전트 생성 3경로에서 단독 워커 검증을 거는 **정확한 지점**
3. [ ] 구현 세션 분할 (Design §11.3 Session Guide) — 게이트 코어 / 미들웨어 편입 / 예약 집행 / 재개 / 프론트

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-20 | 초안 — Checkpoint 1/2 확정 (집행모델 A+Protocol, MVP 골격+mock, 승인자=에이전트 소유자, 작업함 탭, 단독워커 제약, 순차 승인, 만료+버전검증, 거절 사유 주입 재개) | 배상규 |
| 0.2 | 2026-09-20 | **무인 시간대 대응 추가** — ① 기존 미들웨어 카탈로그 편입으로 에이전트별 제어(FR-18~22) ② `execute_after` 예약 집행 + 집행 스케줄러(FR-23~26) ③ `is_enforced` 관리자 강제 ④ 게이트 발동 합성 규칙(FR-21). FR 17개 → 26개 | 배상규 |
