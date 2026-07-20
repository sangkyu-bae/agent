# agent-memory Planning Document

> **Summary**: 에이전트 장기 메모리 **Phase 1** — 사용자가 직접 등록·관리하는 구조화 메모리(프로필/선호/도메인 용어)를 MySQL에 저장하고, General Chat 시스템 프롬프트에 토큰 캡 내에서 자동 주입한다. 자동 추출·정합기·org 승인 큐는 Phase 2/3로 이월하되, 스키마(tier/scope/status/source_run_id)는 확장 가능하게 선반영
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 풀스택)
> **Author**: 배상규
> **Date**: 2026-07-18
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | RAG 에이전트가 무상태(stateless)라서 "심사팀 소속이고 근거 조문 인용을 선호하며 사내에서 '한도'는 특정 의미"라는 문맥을 사용자가 매 질문마다 실어줘야 한다. 일반 사용자는 이런 컨텍스트 주입을 못 하고, 매 세션 처음부터 다시 설명하는 경험이 반복된다. |
| **Solution** | `agent_memory` 테이블(V050) 신설 + 사용자 본인 메모리 CRUD API + SettingsPage "AI가 기억하는 내용" 관리 UI. General Chat 유스케이스가 시스템 프롬프트 조립 시 해당 사용자의 active 메모리를 토큰 캡(≈800 tokens) 내에서 자동 주입한다. Phase 1은 **수동 등록만** — 주입 경로의 품질 효과를 먼저 검증하고, 자동 추출(Phase 2)·org 사전/승인 큐·위키 패턴(Phase 3)은 같은 스키마 위에 후속으로 쌓는다. |
| **Function/UX Effect** | 사용자가 설정 화면에서 자기 정보(부서/역할/응답 선호/용어)를 한 번 등록하면, 이후 모든 General Chat 답변이 그 문맥을 반영한다. 메모리 목록/수정/삭제가 투명하게 노출되어 "AI가 나에 대해 뭘 아는지"를 사용자가 완전히 통제한다. |
| **Core Value** | "매번 설명하는 AI"에서 "나를 아는 AI"로 — 엔터프라이즈 신뢰의 전제인 **투명성(본인 열람·삭제)과 통제권**을 갖춘 최소 루프를 먼저 열고, 성장형 에이전트(피드백 기반 자동 축적)로 가는 확장 기반(tier/scope/status 스키마)을 확보한다. |

---

## 1. Overview

### 1.1 Purpose

사용자별 장기 메모리의 최소 루프를 구축한다: 구조화 저장(MySQL) → 관리 UI(투명성) → 시스템 프롬프트 주입.
Phase 1은 추출 난이도를 0으로 만들고(수동 입력) **주입이 답변 품질을 올리는지**부터 검증한다.

### 1.2 Background (현재 구조 분석 — 2026-07-18 확인)

| 항목 | 현재 상태 | 근거 코드 |
|------|-----------|----------|
| 시스템 프롬프트 조립 | `general_chat/use_case.py`가 시스템 프롬프트를 구성해 LLM 호출 — 주입 지점 후보 확정 | `src/application/general_chat/use_case.py` |
| General Chat 우선 선례 | 차트 렌더링도 General Chat 경로에만 우선 연결 (Excel/Supervisor 후속) — 동일 전략 채택 | 메모리: chart-rendering-general-chat-only |
| user_id 타입 | 대화 계열 테이블은 `String(255)` (`conversation.py` user_id) — 메모리 테이블도 일치시킴 | `src/infrastructure/persistence/models/conversation.py:23` |
| 마이그레이션 | 최신 V049 — 신규는 **V050**. FK COLLATE 명시 금지(errno 3780 선례), ENGINE=InnoDB만 | `db/migration/`, 메모리: mysql-fk-collation |
| 프론트 설정 화면 | `SettingsPage` 기존 존재 — 메모리 관리 섹션 추가 지점 | `idt_front/src/pages/SettingsPage/` |
| 유사 CRUD 선례 | search_history(kb_id) 시리즈 — repository/use_case/router/프론트 훅 패턴 재사용 | `src/infrastructure/collection_search/search_history_repository.py` |
| 대화 메모리 정책 | "대화 기록 vector DB 저장 금지" — 본 기능은 **정제된 사실만 MySQL 저장**이라 원칙과 충돌 없음 | `docs/rules/conversation-memory.md` |
| 장기 메모리 저장소 | **없음** — 세션 대화 이력만 존재, 세션 간 사용자 문맥 지속 수단 부재 | `src/application/general_chat/` 확인 |

### 1.3 Related Documents

- 방향 논의: 본 대화(2026-07-18) — 계층형 메모리(MemGPT), reflection, LLM 위키 패턴 검토 후 Phase 1 범위 확정
- 규칙: `idt/CLAUDE.md`, `docs/rules/conversation-memory.md`, `docs/rules/db-session.md`, 루트 `CLAUDE.md` §4-1(API 계약 동기화)

### 1.4 사용자 확정 사항 (대화 2026-07-18)

| 질문 | 결정 |
|------|------|
| 저장소 | **MySQL 구조화 테이블** (벡터 DB 아님 — 소량·CRUD·감사·승인 상태 관리가 본질) |
| 주입 방식 | Tier 0 상주 주입(전량 로드 + 하드캡) — 검색 아님. 위키/온디맨드 도구는 Phase 3 |
| Phase 1 범위 | **수동 등록만** (자동 추출 없음) — 주입 경로 효과 먼저 검증 |
| 스키마 선반영 | `tier`/`scope`/`status`/`source_run_id`/`confidence` 컬럼 포함 — Phase 2/3 마이그레이션 재작업 방지 |
| 무한 누적 방지 | 사용자당 활성 메모리 개수 상한 + 주입 토큰 캡을 Phase 1부터 강제 |

---

## 2. Scope

### 2.1 In Scope

**백엔드 (idt/)**
- [ ] `agent_memory` SQLAlchemy 모델 + **V050** 마이그레이션: id, scope(`user`|`org`), user_id(String(255)), tier(TINYINT, 기본 0), mem_type(`profile`|`preference`|`domain_term`|`episode`), content(TEXT), source_run_id(NULL — Phase 1은 항상 NULL), confidence(기본 100 — 수동 입력), status(`pending`|`active`|`rejected`|`expired`), expires_at(NULL), created_at/updated_at
- [ ] 메모리 CRUD API (인증 사용자 본인 것만): `GET/POST /api/v1/memories`, `PATCH/DELETE /api/v1/memories/{id}` — Phase 1은 scope=`user`·status=`active` 고정 생성
- [ ] 사용자당 활성 메모리 개수 상한(config, 예: 30건) — 초과 시 422
- [ ] `domain/memory/`: Memory 엔티티 + MemoryPolicy(개수 상한·주입 우선순위 규칙) + Repository/LoggerInterface
- [ ] `application/memory/`: CRUD 유스케이스 + **MemoryContextAssembler**(active 메모리 로드 → 우선순위 정렬(profile > domain_term > preference > episode) → 토큰 캡 절단 → 프롬프트 섹션 렌더링)
- [ ] `general_chat/use_case.py` 시스템 프롬프트 조립부에 MemoryContextAssembler 호출 1개 추가 — 메모리 0건이면 섹션 자체 미주입, 조회 실패는 warn 로그 후 **주입 없이 정상 응답**(메모리 장애가 채팅 장애로 전파 금지)
- [ ] pytest 선행 작성 (TDD: 엔티티/정책, CRUD 유스케이스, 조립기 캡·정렬·빈 상태, 라우터 401/본인 소유 검증, general_chat 주입 통합)

**프론트엔드 (idt_front/)**
- [ ] SettingsPage에 "AI가 기억하는 내용" 섹션: 목록(타입 뱃지 + 내용) / 추가 폼(타입 선택 + 내용) / 인라인 수정 / 삭제
- [ ] API 계약 동기화: `constants/api.ts` 상수, `types/memory.ts`, `services/memoryService.ts`, `hooks/useMemories.ts`(TanStack Query) — Vitest+MSW 테스트 선행 (`--pool=threads`, MSW 파일별 3종 훅)
- [ ] 개수 상한 도달 시 안내 UI (422 에러 표면화)

### 2.2 Out of Scope (Phase 2/3 이월 — 스키마는 준비됨)

- 대화로부터 자동 추출·정합기(reconciler)·reflection/사서 잡 (Phase 2)
- org 스코프 메모리 + admin 승인 큐(pending→active), 용어 사전 공유 (Phase 3)
- episode 검색·위키 인덱스+온디맨드 read_memory 도구 노드 (Phase 3)
- Excel/Supervisor 등 General Chat 외 경로 주입 (차트 렌더링과 동일하게 후속)
- 피드백(👍/👎) 수집·검증된 답변 승격 (별도 feature: feedback-loop)
- expires_at 기반 자동 만료 배치 (Phase 1은 컬럼만)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 인증 사용자는 본인 메모리를 생성/조회/수정/삭제할 수 있다 — 타인 메모리 접근 시 404/403 | High | Pending |
| FR-02 | 생성 시 mem_type 4종 중 선택, content 필수(최대 길이 제한, 예: 500자) — 검증 실패 422 | High | Pending |
| FR-03 | 사용자당 활성 메모리 개수 상한 초과 생성 시 422 + 명확한 에러 메시지 | High | Pending |
| FR-04 | General Chat 요청 시 해당 사용자의 active 메모리가 시스템 프롬프트의 전용 섹션으로 주입된다 | High | Pending |
| FR-05 | 주입 섹션은 토큰 캡을 넘지 않는다 — 우선순위(profile > domain_term > preference > episode) 순 포함, 초과분 절단 시 debug 로그 | High | Pending |
| FR-06 | 메모리 0건이면 섹션 자체가 주입되지 않는다 (빈 헤더 금지) | Medium | Pending |
| FR-07 | 메모리 조회 실패(DB 오류) 시 채팅은 주입 없이 정상 진행되고 warn 로그(request_id 포함)가 남는다 | High | Pending |
| FR-08 | SettingsPage에서 메모리 목록·추가·수정·삭제가 동작하고 변경이 즉시 목록에 반영된다 | High | Pending |
| FR-09 | 주입된 프롬프트 섹션에 "자동 축적 정보이며 불확실하면 사용자에게 확인" 지침이 포함된다 (보수적 동작) | Medium | Pending |
| FR-10 | 프론트 타입/서비스/훅/엔드포인트 상수가 백엔드 계약과 동기화된다 (루트 CLAUDE.md §4-1) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | 정책(상한·우선순위)은 domain, 흐름은 application, DB는 infrastructure. domain→infra 참조 금지, Repository 내 commit 금지, 한 유스케이스 단일 세션 | `/verify-architecture` |
| 성능 | 주입 경로 추가 쿼리는 user_id 인덱스 단건 SELECT 1회 — 채팅 지연 영향 최소화. LLM 호출 없음(Phase 1) | 쿼리 리뷰 |
| 격리 | 메모리 기능 장애가 채팅 실패로 전파되지 않음 (FR-07) — try/except 격리 | 주입 실패 테스트 |
| 호환성 | general_chat 기존 테스트 회귀 0, 기존 테이블 스키마 무변경(신규 테이블만) | pytest (Windows 격리 실행 기준) |
| TDD | 신규 모듈 테스트 선행 작성 (Red→Green) | `/verify-tdd` |
| 로깅 | 주입 건수/절단 여부/실패를 request_id 포함 구조화 로그로 기록 (print 금지) | `/verify-logging` |
| 확장성 | Phase 2/3에서 스키마 변경 없이 추출기·승인 큐·tier 승강만 추가 가능해야 함 | Design 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR 전체 구현: 설정에서 메모리 등록 → General Chat 질문 → 답변이 메모리 문맥 반영(예: 선호 형식 준수) → 삭제 후 미반영 확인
- [ ] 주입 프롬프트 실측 확인 (LangSmith trace에서 섹션 포함 여부)
- [ ] pytest 선행 작성(Red→Green) + general_chat 회귀 0
- [ ] Vitest(MSW 파일별 3종 훅, `--pool=threads`) 통과
- [ ] Gap 분석(Check) ≥ 90%

### 4.2 Quality Criteria

- [ ] 레이어 의존성 규칙 위반 0 (`/verify-architecture`)
- [ ] 신규 함수 40줄 이하, if 중첩 2단계 이하
- [ ] 사전 실패 테스트(백엔드 api 28건·infra 30건, 프론트 8건)는 기존 이슈 — 신규 회귀로 오인 금지
- [ ] E2E(실서버에서 메모리 등록→채팅 반영) 수동 검증 — V050 적용 선행, 공통 이월 체크리스트 등재

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 주입 메모리가 답변을 오염 (잘못된 자기 등록 정보를 사실로 단정) | Medium | Medium | FR-09 보수적 지침 문구 + 사용자 본인이 등록·삭제하는 투명 구조라 자정 가능. 금융 도메인 보수 동작 원칙 준수 |
| 주입으로 기존 프롬프트 토큰 증가 → 비용/컨텍스트 압박 | Low | High | 하드캡(≈800토큰)·개수 상한을 Phase 1부터 강제 — 무한 누적이 구조적으로 불가능 |
| general_chat 프롬프트 조립부 수정이 기존 동작 회귀 유발 | High | Low | 주입은 호출 1개 추가 + 실패 격리(FR-07). 기존 테스트 전체 회귀 확인 |
| Phase 2/3 요구가 스키마와 안 맞아 재작업 | Medium | Low | tier/scope/status/source_run_id/confidence 선반영 — 대화에서 확정한 확장 경로(추출기·승인 큐·위키) 기준으로 Design에서 재검증 |
| 토큰 카운팅 정확도 (한글 토큰 추정 오차) | Low | Medium | 정밀 카운트 불필요 — 문자수 기반 보수적 근사(예: 2자/token)로 캡 적용, Design에서 방식 확정 |
| user_id 타입 불일치 (auth의 사용자 식별자 vs String(255)) | Medium | Low | conversation 계열 선례(String(255)) 일치 — Design에서 auth 의존성의 실제 반환 타입 확인 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

기존 프로젝트 편입 — Thin DDD(Domain→Application→Infrastructure) 현행 유지.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 저장소 | ① Qdrant 임베딩 ② MySQL 구조화 테이블 | ② MySQL | 사용자당 수십 건 규모 — 벡터 검색 불필요. 필요한 건 CRUD/승인/감사/출처추적 = RDB 영역. 대화 원문 임베딩 오염 방지, conversation-memory 규칙 부합 |
| 주입 방식 | ① 관련성 검색 후 주입 ② active 전량 로드 + 하드캡 상주 | ② 상주 주입 | profile/preference는 "항상 참인 배경" — 검색 누락이 곧 UX 실패. 소량이라 전량 주입 가능. 온디맨드 도구는 Phase 3(episode 증가 시) |
| Phase 1 입력 경로 | ① 자동 추출부터 ② 수동 등록부터 | ② 수동 | 주입 경로가 먼저 검증돼야 추출 투자가 유효 — 추출 난이도 0으로 만들고 주입 효과만 순수 검증 |
| 주입 대상 경로 | ① 전 에이전트 경로 ② General Chat만 | ② General Chat만 | 차트 렌더링 선례 동일 — 최다 사용 경로에서 검증 후 확산 |
| 스키마 범위 | ① Phase 1 최소 컬럼 ② 확장 컬럼 선반영 | ② 선반영 | tier/scope/status/source_run_id/confidence — Phase 2/3에서 ALTER 재작업 방지, 컬럼 비용 미미 |
| 누적 제어 | ① 무제한 후 필요 시 정리 ② 개수 상한+토큰 캡 즉시 | ② 즉시 강제 | "무엇을 안 넣느냐"가 메모리 시스템의 본질 — 폭주를 구조적으로 차단 |
| 신규 API 위치 | ① 기존 라우터 확장 ② `memory_router` 신설 | ② 신설 (`/api/v1/memories`) | 단일 책임 — 기존 라우터들과 등록 패턴 동일 |

### 6.3 Clean Architecture Approach

`domain/memory/`: Memory 엔티티·MemoryPolicy(상한/우선순위/캡 규칙 — 순수 로직)·Repository 인터페이스.
`application/memory/`: CRUD 유스케이스 + MemoryContextAssembler(주입 문자열 생성).
`infrastructure/memory/`: SQLAlchemy 모델·repository(기존 세션 팩토리 DI 패턴, commit은 유스케이스 경계).
`interfaces/`: `memory_router` + request/response 스키마. general_chat은 Assembler 의존성 1개 추가만.

---

## 7. Convention Prerequisites

- [x] `idt/CLAUDE.md` + `docs/rules/testing.md` 준수 (TDD 필수)
- [x] 로깅: LoggerInterface + request_id (print 금지)
- [x] DB: Repository 내 commit 금지, 단일 세션, V050 마이그레이션(FK COLLATE 명시 금지·ENGINE=InnoDB)
- [x] 프론트: API 상수 `constants/api.ts` 집중, MSW 파일별 3종 훅, Vitest `--pool=threads`
- [x] 개수 상한·토큰 캡은 config로 (하드코딩 금지)

신규 환경변수 없음(상한값은 기존 config 체계에 추가).

---

## 8. Next Steps

1. [ ] `/pdca design agent-memory` — agent_memory DDL 확정(인덱스: user_id+status), CRUD 스키마·에러 계약, MemoryContextAssembler 시그니처와 general_chat 주입 지점 실코드 확정, 토큰 근사 방식, SettingsPage 섹션 UI 설계
2. [ ] 구현 (TDD: domain 정책 → repository → 유스케이스/조립기 → 라우터 → general_chat 주입 → 프론트 타입/서비스/훅 → SettingsPage)
3. [ ] `/pdca analyze agent-memory`
4. [ ] 후속 feature 분리 기획: agent-memory-extraction(Phase 2), agent-memory-org-wiki(Phase 3), feedback-loop

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-18 | Initial draft — Phase 1(수동 메모리 + General Chat 주입) 범위 확정, MySQL·상주 주입·확장 스키마 선반영 결정 (아키텍처 대화 반영) | 배상규 |
