# Agent Subscription & Customization Planning Document

> **Summary**: 공유 에이전트를 구독(선택)하고, 포크(전체 복사)하여 개인화하는 기능
>
> **Project**: sangplusbot (idt)
> **Version**: -
> **Author**: 배상규
> **Date**: 2026-05-04
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

현재 에이전트는 visibility(전체/부서/개인)로 공개할 수 있지만, 공유된 에이전트를 **사용자가 자신의 목록에 추가(구독)** 하거나 **커스터마이징(포크)** 하는 기능이 없다.

이 기능을 통해:
- 사용자는 공개/부서 에이전트를 **구독**하여 "내 에이전트" 목록에서 바로 접근
- 구독한 에이전트를 **포크(전체 복사)**하여 시스템 프롬프트, 도구 구성, LLM 모델 등을 자유롭게 커스터마이징
- 원본 에이전트 삭제/비공개 전환 시 구독자에게 **자동 포크 전환**으로 서비스 연속성 보장

### 1.2 Background

- 에이전트 빌더 시스템이 이미 `agent_definition` + `agent_tool` 테이블로 구현됨
- visibility(private/department/public) 및 `VisibilityPolicy` 접근 제어 완비
- 하지만 "다른 사람의 에이전트를 내 것처럼 사용/수정"하는 경로가 없음
- 조직 내에서 에이전트를 공유→커스터마이징하는 워크플로우가 핵심 사용성 요구사항

### 1.3 Related Documents

- 기존 에이전트 정의: `src/domain/agent_builder/schemas.py`
- Visibility 정책: `src/domain/agent_builder/policies.py`
- 에이전트 API: `src/api/routes/agent_builder_router.py`
- DB 마이그레이션: `db/migration/V007__alter_agent_definition_add_sharing.sql`

---

## 2. Scope

### 2.1 In Scope

- [ ] **구독(Subscription) 기능**: 공유 에이전트를 "내 목록"에 추가/제거
- [ ] **포크(Fork) 기능**: 구독한 에이전트를 전체 복사하여 독립 에이전트 생성
- [ ] **포크 에이전트 전체 커스터마이징**: 프롬프트, 이름, temperature, 도구, LLM 모델
- [ ] **원본 삭제 시 자동 포크 전환**: 원본 접근 불가 시 마지막 상태 스냅샷으로 자동 전환
- [ ] **"내 에이전트" 통합 목록 API**: 내가 만든 + 구독한 + 포크한 에이전트 통합 조회
- [ ] **DB 마이그레이션**: subscription 테이블, agent_definition에 forked_from 컬럼 추가

### 2.2 Out of Scope

- 포크된 에이전트의 재공유(포크 → public/department 공개)는 이후 버전
- 원본 에이전트 업데이트 알림(notification) 시스템
- 에이전트 버전 관리(versioning)
- 에이전트 마켓플레이스 UI (프론트엔드는 별도 Plan)
- 에이전트 사용 통계/분석

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 사용자가 public/department 에이전트를 구독(내 목록에 추가)할 수 있다 | High | Pending |
| FR-02 | 구독한 에이전트를 구독 해제(내 목록에서 제거)할 수 있다 | High | Pending |
| FR-03 | 구독한 에이전트를 포크하여 독립적인 커스텀 에이전트를 생성할 수 있다 | High | Pending |
| FR-04 | 포크 시 원본의 모든 필드(name, system_prompt, temperature, tools, llm_model_id)가 복사된다 | High | Pending |
| FR-05 | 포크된 에이전트는 모든 필드를 자유롭게 수정할 수 있다 | High | Pending |
| FR-06 | 포크된 에이전트의 visibility는 기본 private이며, 포크 소유자가 변경 가능하다 | Medium | Pending |
| FR-07 | "내 에이전트" 목록에서 소유/구독/포크를 구분하여 조회할 수 있다 | High | Pending |
| FR-08 | 원본 에이전트 삭제/비공개 전환 시, 해당 구독자에게 자동으로 포크를 생성한다 | High | Pending |
| FR-09 | 포크된 에이전트에서 원본 출처(forked_from)를 확인할 수 있다 | Low | Pending |
| FR-10 | 구독에 즐겨찾기(pin) 기능을 지원한다 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 구독/포크 API 응답 시간 < 500ms | API 로그 측정 |
| Data Integrity | 포크 시 원본 데이터 100% 정합성 | 단위 테스트 |
| Cascading | 원본 삭제 시 자동 포크 전환 누락 0건 | 통합 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 모든 Functional Requirements 구현
- [ ] 단위 테스트 작성 및 통과 (domain, application 레이어)
- [ ] 기존 에이전트 CRUD API에 영향 없음 확인
- [ ] DB 마이그레이션 스크립트 작성 및 적용
- [ ] API 문서 업데이트

### 4.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상
- [ ] 기존 테스트 전체 통과
- [ ] mypy / lint 에러 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 포크 시 대량 도구 복사로 트랜잭션 지연 | Medium | Low | 단일 트랜잭션 내 bulk insert, 도구 수 제한(max 20) |
| 원본 삭제 시 다수 구독자 자동 포크로 DB 부하 | High | Low | 비동기 처리 또는 soft-delete 후 배치 포크 |
| forked_from 참조 무결성 (원본 hard-delete) | High | Medium | forked_from은 FK 아닌 일반 컬럼으로, 원본 삭제 허용 |
| 구독 테이블 인덱스 미설계로 조회 성능 저하 | Medium | Medium | 복합 인덱스 (user_id, agent_id) 설계 |

---

## 6. Architecture Considerations

### 6.1 Project Level

**Enterprise** (Thin DDD) — 기존 프로젝트 아키텍처 유지

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 포크 저장 방식 | 오버레이(delta) / 포크(full copy) | **포크 (full copy)** | 원본과 완전 독립, 기존 agent_definition 구조 재사용 |
| 구독-커스텀 관계 | 통합 테이블 / 분리 테이블 | **분리 테이블** | 구독(bookmark)과 포크(full entity)는 성격이 다름 |
| forked_from 저장 | FK 제약 / 일반 컬럼 | **일반 컬럼 (nullable)** | 원본 삭제 시에도 포크 유지 필요 |
| 원본 삭제 정책 | 사용불가 / 자동 포크 | **자동 포크 전환** | 사용자 서비스 연속성 보장 |
| 자동 포크 트리거 | DB trigger / Application 레벨 | **Application 레벨** | DDD 원칙 준수, 테스트 용이 |

### 6.3 DB Schema Changes

```
기존 테이블 수정:
┌─────────────────────────────────────────────────────┐
│ agent_definition                                     │
│   + forked_from VARCHAR(36) NULLABLE                │
│   + forked_at   DATETIME    NULLABLE                │
│   (FK 없음 — 원본 삭제 허용)                          │
│   INDEX: ix_agent_forked_from                        │
└─────────────────────────────────────────────────────┘

신규 테이블:
┌─────────────────────────────────────────────────────┐
│ user_agent_subscription                              │
│   id              VARCHAR(36) PK                     │
│   user_id         VARCHAR(100) FK → users            │
│   agent_id        VARCHAR(36)  FK → agent_definition │
│   is_pinned       BOOLEAN DEFAULT FALSE              │
│   subscribed_at   DATETIME                           │
│                                                      │
│   UNIQUE: (user_id, agent_id)                        │
│   INDEX:  ix_subscription_user                       │
│   INDEX:  ix_subscription_agent                      │
└─────────────────────────────────────────────────────┘
```

### 6.4 레이어별 구현 범위

```
domain/agent_builder/
  ├── schemas.py          → AgentDefinition에 forked_from, forked_at 추가
  ├── policies.py         → ForkPolicy 추가 (포크 가능 여부 판단)
  └── subscription.py     → Subscription 엔티티, SubscriptionPolicy (NEW)

application/agent_builder/
  ├── subscribe_use_case.py       → 구독/구독해제 (NEW)
  ├── fork_agent_use_case.py      → 포크 생성 (NEW)
  ├── list_my_agents_use_case.py  → 통합 목록 (NEW)
  └── auto_fork_use_case.py       → 원본 삭제 시 자동 포크 (NEW)

infrastructure/agent_builder/
  ├── models.py                            → forked_from 컬럼 추가
  ├── subscription_model.py                → SubscriptionModel (NEW)
  ├── agent_definition_repository.py       → fork 관련 메서드 추가
  └── subscription_repository.py           → 구독 CRUD (NEW)

api/routes/
  └── agent_builder_router.py   → 구독/포크/내 목록 엔드포인트 추가
```

---

## 7. API Endpoints (예상)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/agents/{agent_id}/subscribe` | 에이전트 구독 |
| DELETE | `/api/v1/agents/{agent_id}/subscribe` | 구독 해제 |
| PATCH | `/api/v1/agents/{agent_id}/subscribe` | 구독 설정 변경 (pin 등) |
| POST | `/api/v1/agents/{agent_id}/fork` | 에이전트 포크 (전체 복사) |
| GET | `/api/v1/agents/my` | 내 에이전트 통합 목록 (소유+구독+포크) |
| GET | `/api/v1/agents/{agent_id}/forks` | 특정 에이전트의 포크 수/목록 (원본 소유자용) |

---

## 8. User Flow

```
[사용자가 에이전트 목록 탐색]
         │
         ▼
[공개/부서 에이전트 발견]
         │
    ┌────┴────┐
    ▼         ▼
 [바로 사용]  [구독(내 목록에 추가)]
              │
         ┌────┴────┐
         ▼         ▼
    [그대로 사용]  [포크(커스터마이징)]
                   │
                   ▼
           [독립 에이전트 생성]
           [전체 필드 수정 가능]
           [visibility=private]

--- 원본 삭제/비공개 전환 시 ---

[원본 에이전트 삭제/비공개]
         │
         ▼
[구독자 목록 조회]
         │
    ┌────┴────┐
    ▼         ▼
 [이미 포크됨] [구독만 한 상태]
 → 영향 없음   → 자동 포크 생성
               → 구독 → 포크로 전환
```

---

## 9. Convention Prerequisites

### 9.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section
- [x] Thin DDD 레이어 구조 확립
- [x] DB 세션 규칙: `docs/rules/db-session.md`
- [x] 테스트 규칙: `docs/rules/testing.md`
- [x] Flyway 마이그레이션 형식 사용 중

### 9.2 Environment Variables Needed

추가 환경변수 없음 — 기존 MySQL 연결 설정 사용.

---

## 10. Implementation Order (예상)

1. DB 마이그레이션 (`V017__add_agent_subscription_and_fork.sql`)
2. Domain 레이어: Subscription 엔티티, ForkPolicy
3. Infrastructure 레이어: SubscriptionModel, SubscriptionRepository, fork 메서드
4. Application 레이어: SubscribeUseCase, ForkAgentUseCase, ListMyAgentsUseCase
5. Application 레이어: AutoForkUseCase (원본 삭제 시 자동 포크)
6. API 레이어: 엔드포인트 추가
7. 기존 delete 로직에 자동 포크 트리거 연동

---

## 11. Next Steps

1. [ ] Design 문서 작성 (`agent-subscription-customization.design.md`)
2. [ ] 팀 리뷰 및 승인
3. [ ] TDD 기반 구현 시작

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-04 | Initial draft | 배상규 |
