# Background Jobs Planning Document

> **Summary**: 사용자가 요청해두고 채팅방을 나가도 서버가 알아서 끝까지 실행하는 **백그라운드 작업(job)** 체계 신설. DB 큐 + 인프로세스 워커 루프로 ad-hoc 작업을 실행하고, 기존 agent_schedule의 외부 cron 의존을 **서버 내장 스케줄러 틱**으로 대체하며, **작업함(내 작업) 페이지 + 헤더 벨 알림 + 채팅방 복귀 시 결과 표시**로 진행중/완료 확인과 작업물 열람을 제공하는 풀스택 사이클 (M1=백엔드, M2=프론트)
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-11
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 실행이 전부 **요청/연결 수명에 묶여 있다** — 채팅 실행은 HTTP/WS 응답을 기다려야 하고, 오래 걸리는 작업 중 채팅방을 나가면 결과를 받을 방법이 없다. 스케줄 기능(agent_schedule, V038)은 존재하지만 **외부 cron이 `/trigger` 엔드포인트를 때려줘야만 동작**하고, 실행 이력·결과를 한눈에 보는 화면과 완료 알림이 없어 "돌려놓고 잊어도 되는" 경험이 성립하지 않는다 |
| **Solution** | ① 신규 `agent_background_job` 테이블(V060) 기반 **DB 큐 + 인프로세스 워커 루프** — 작업을 등록하면 즉시 job_id를 돌려주고 서버가 뒤에서 실행, 서버 재시작에도 queued 작업 생존 ② 워커 루프에 **스케줄러 틱 내장** — 기존 `TriggerDueSchedulesUseCase`를 주기 호출해 외부 cron 불필요화(기존 엔드포인트는 백업 유지) ③ **작업함 페이지 + 헤더 벨 배지 + 채팅방 복귀 시 결과 표시** — 진행중/완료/실패 상태와 작업물(대화 답변)로 바로가기 ④ 완료 시 기존 outbound 웹훅 디스패처 재사용(source="job") |
| **Function/UX Effect** | 사용자가 "이 보고서 정리해줘"를 백그라운드로 넘기고 채팅방을 나가도, 완료되면 헤더 벨에 배지가 뜨고 작업함에서 결과 세션으로 바로 이동해 답변을 확인한다. 스케줄 등록만 하면 별도 인프라 없이 서버가 알아서 주기 실행한다 |
| **Core Value** | 에이전트 플랫폼이 "붙잡고 기다리는 도구"에서 **"맡겨두는 동료"로 전환** — 장시간 작업(조사·문서생성·배치)의 실용성이 열린다. RunAgentUseCase·schedule claim 패턴·outbound 디스패처 등 기존 실행 인프라 최대 재사용으로 신규 표면 최소화, ad-hoc job과 스케줄 실행을 하나의 확인 UX로 통합 (일반화 우선 원칙 부합) |

---

## 1. Overview

### 1.1 Purpose

하나의 "백그라운드 작업(job)" 개념으로 다음 세 가지를 통합한다:

- **ad-hoc 백그라운드 실행**: 채팅/빌더에서 요청한 에이전트 실행을 job으로 등록 →
  즉시 접수 응답(job_id) → 서버가 뒤에서 완료까지 실행 → 결과는 대화 세션 메시지로 저장.
- **서버 내장 스케줄링**: 워커 루프의 주기 틱이 due 스케줄을 자동 실행 (외부 cron 제거).
- **확인 체계**: 작업함 페이지(진행중/완료/실패 + 작업물 바로가기), 헤더 벨 알림(미확인 완료 배지),
  채팅방 복귀 시 결과 자연 표시, outbound 웹훅 발송.

### 1.2 Background (2026-08-11 코드 조사로 확정)

**재사용 가능한 기존 자산**:

| 구간 | 위치 | 상태 |
|------|------|------|
| 스케줄 CRUD + cron 계산 | `application/agent_schedule/` + `domain/agent_schedule/` (V038) | 기존재 (무변경) |
| due 선점(claim) 패턴 | `schedule_repository.claim_due` — 짧은 트랜잭션 선점 → 회차별 독립 세션 실행 | 선례 (job claim 동형 설계) |
| 실행 이력 sink | `infrastructure/agent_schedule/run_sink.py` — on_started/on_finished 자체 트랜잭션 즉시 커밋 | 선례 (job 상태 전이 동형) |
| 외부 트리거 진입점 | `TriggerDueSchedulesUseCase` + trigger_router — `status()`로 정지 감지 | 기존재 (**내장 틱이 이를 주기 호출** — 엔드포인트는 백업 유지) |
| 에이전트 실행 | `RunAgentUseCase` — 세션 생성 + user/assistant 메시지 저장까지 수행 (schedule 경로에서 이미 무헤드리스 재사용 중) | 기존재 (job 실행 본체로 재사용) |
| outbound 웹훅 발송 | 싱글턴 디스패처 — `dispatch(agent_id, result, source, request_id)`, raise 금지 계약(D16), source="webhook"/"schedule" | 기존재 (source="job" 추가만) |
| create_task 참조 보유 교훈 | `invoke_webhook_agent_use_case.py:58` — GC 회수 방지 위해 태스크 참조 유지 | 선례 (워커 루프는 lifespan이 참조 보유) |
| 세션 팩토리 주입 | `session_factory` 주입 + 단계별 짧은 트랜잭션 (DB-001) | 관례 (job 큐 동일 적용) |
| 프론트 스케줄 UI | 빌더 내 스케줄 설정 (`types/agentSchedule.ts`, `utils/scheduleCron.ts`) | 기존재 (무변경) |
| 마이그레이션 | 최신 V059(doc-generator, 미커밋) → 이번 사이클 **V060** | — |

**현재의 갭 (이번 기능이 채우는 것)**:

1. 채팅 실행이 요청/연결 수명과 결합 — 연결이 끊기면 결과 수신 경로가 없다.
2. 서버 안에 스스로 도는 스케줄러 루프가 없다 — 외부 cron이 정지하면 스케줄 전체가 침묵.
3. "내 작업이 지금 어떤 상태인가"를 보는 화면·알림이 없다 (스케줄 run 이력 API는 있으나 통합 뷰 부재).

**사전 결정 사항 (2026-08-11 사용자 확정)**:

1. **범위**: 통합 백그라운드 작업 — ad-hoc job + 내장 스케줄러 + 작업함을 한 사이클로.
2. **내구성**: **DB 큐 + 인프로세스 워커** — queued/running/success/failed 상태를 DB에 기록,
   서버 재시작 시 queued 생존. 외부 워커(Celery/Redis)는 도입하지 않음 (단일 서버 규모 적정).
3. **확인 UX**: 작업함 페이지 + 헤더 벨 알림 + 채팅방 복귀 시 결과 표시 + outbound 웹훅 재사용 — 4종 모두.
4. **작업물 1차 형태**: **대화 답변 = 작업물** — 실행 결과가 세션 메시지로 저장되고 작업함에서
   해당 세션으로 이동해 열람. 파일 산출물 전용 뷰는 후속 (doc-generator 결합 시점에 재검토).

### 1.3 Related Documents

- 스케줄 선례: `src/application/agent_schedule/` (claim·sink·trigger 구조) — V038
- 웹훅 outbound 선례: `docs/archive/2026-08/agent-webhook-outbound/` (디스패처 계약 D12·D16)
- HITL 선례: `docs/archive/2026-08/fix-agent-planner-hitl/` (stateless 질문 에코백 — §5 리스크 관련)
- DB 세션 규칙: `docs/rules/db-session.md` / 로깅: `docs/rules/logging.md`
- 계약 확장 관례: `docs/wiki/conventions/additive-contract-extension.md` (additive·독립 opt-in)
- 라우터 지도: `docs/wiki/backend/api/router-map.md`

---

## 2. Scope

### 2.1 In Scope — M1: 백엔드 (job 큐·워커 루프·스케줄러 틱·API)

- [ ] **S1. DB — V060 `agent_background_job` 테이블 신설** (기존 스키마 무변경):
      `id, user_id, agent_id(FK), source('chat'|'api'), query, session_id, run_id,`
      `status('queued'|'running'|'success'|'failed'), error_message, seen_at,`
      `queued_at, started_at, finished_at, request_id, created_at, updated_at`
      — 테이블+전 컬럼 COMMENT 필수, FK CHARSET/COLLATE 명시 금지(ENGINE=InnoDB만), SQLAlchemy `comment=` 동반.
- [ ] **S2. 도메인 — `domain/background_job/`**: job 엔티티·상태 전이 정책(허용 전이 검증),
      큐 정책(동시 실행 상한·오래된 running 판정 기준 — 값은 config), 인터페이스(repo·sink).
- [ ] **S3. 큐 저장소 — `infrastructure/background_job/`**: enqueue / claim(선점 UPDATE — claim_due 동형) /
      상태 전이 기록(자체 짧은 트랜잭션 — run_sink 동형) / 사용자별 목록·미확인 카운트 조회.
- [ ] **S4. 워커 루프 — lifespan 싱글턴**: 주기 폴링으로 ① queued job claim → `RunAgentUseCase`로
      실행(회차별 독립 세션) → 상태 기록 → outbound dispatch(source="job") ② **스케줄러 틱** —
      `TriggerDueSchedulesUseCase.execute()` 주기 호출(내장 스케줄러). 기동 시 **reconcile** —
      직전 crash로 running에 방치된 job을 명시 상태로 정리(재큐 vs failed는 Design 확정).
      shutdown 시 루프 정상 종료(진행 중 실행은 완료 대기 or 타임아웃 — Design 확정).
- [ ] **S5. API — job 라우터**: 등록(POST — agent_id·query·session_id(optional), 202 + job_id),
      내 작업 목록(GET — 상태 필터·페이징), 단건 조회, 미확인 완료 카운트, 확인 처리(mark-seen).
      기존 채팅 실행 API는 무변경 — 백그라운드는 **별도 엔드포인트 opt-in** (기존 enum·플래그 확장 금지 관례).
- [ ] **S6. 테스트 (TDD — Red 먼저)**: 상태 전이 정책 단위, claim 경쟁·중복 선점 방지,
      워커 루프 1회전(성공/실패/outbound 훅), reconcile, 스케줄러 틱 위임, API 인가(본인 job만),
      DDL COMMENT 검사 통과.

### 2.2 In Scope — M2: 프론트 (작업함·벨·채팅 연동)

- [ ] **S7. 작업함 페이지**: 내 작업 목록 — 상태 배지(진행중/완료/실패), 요청 시각·소요 시간,
      에러 메시지, **결과 바로가기(해당 대화 세션으로 이동)**. 진행중 항목은 폴링 갱신.
- [ ] **S8. 헤더 벨 알림**: 미확인 완료/실패 카운트 배지(폴링) + 드롭다운 최근 작업 → 클릭 시
      확인 처리 + 작업함/세션 이동.
- [ ] **S9. 채팅 백그라운드 전환**: 채팅 입력 영역에 "백그라운드로 실행" 액션 → job 등록 + 접수 안내
      메시지 표시. 채팅방 복귀 시 완료 결과는 세션 메시지로 자연 표시(기존 대화 로딩 재사용),
      진행중이면 진행중 표시.
- [ ] **S10. API 계약 동기화**: types/services/hooks + `constants/api.ts` (`api-contract-sync` 체크리스트).
- [ ] **S11. 테스트**: 작업함 목록·상태 배지 단위, 벨 배지·확인 처리, 채팅 전환 액션(MSW 통합) —
      `--pool=threads`, per-file listen 관례.

### 2.3 Out of Scope (이번 사이클 제외)

- **외부 워커/브로커 (Celery·Redis·RabbitMQ)** — 단일 서버 인프로세스로 충분, 수평 확장 시 후속
- **작업 취소·재시도 버튼** (작업함에서 running 중단/failed 재실행 — 수요 확인 후 후속)
- **진행률(%)·중간 산출물 스트리밍** — 상태 3단계(대기/진행/완료)만
- **파일 산출물 전용 뷰·다운로드 목록** — 대화 답변 1차 (doc-generator 완성 후 결합 재검토)
- **WebSocket 푸시 알림** — 폴링 1차, 실시간 푸시는 후속
- 우선순위 큐·예약 실행(특정 시각 1회) — 스케줄 기능과 중복 소지, 후속
- 스케줄 CRUD·빌더 스케줄 UI 변경 (기존 유지 — 트리거 방식만 내장화)

---

## 3. Requirements

### 3.1 Functional Requirements — M1

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 작업 등록 시 즉시 202 + job_id가 반환되고, 등록한 연결/채팅방과 무관하게 서버가 실행을 완료한다 | High | Pending |
| FR-02 | job 상태가 queued→running→success/failed로 DB에 기록되고 조회 API로 확인할 수 있다 (허용되지 않은 전이는 거부) | High | Pending |
| FR-03 | 실행 결과는 대화 세션 메시지로 저장되며(RunAgentUseCase 재사용), job 레코드가 session_id·run_id로 결과를 가리킨다 | High | Pending |
| FR-04 | 서버 재시작 시 queued job은 유실 없이 이어서 실행되고, running이던 job은 reconcile로 명시 상태 처리된다 (침묵 유실 금지) | High | Pending |
| FR-05 | 워커 루프의 스케줄러 틱이 주기적으로 due 스케줄을 자동 실행한다 — 외부 cron 없이 동작하며 기존 trigger 엔드포인트·status()는 유지된다 | High | Pending |
| FR-06 | job 완료/실패 시 outbound 웹훅이 발송된다 (source="job", 발송 실패는 job 상태에 불영향 — D16 이중 방어 동형) | Medium | Pending |
| FR-07 | 동시 실행 job 수가 config 상한을 넘지 않고, 초과분은 queued로 대기한다 | High | Pending |
| FR-08 | 본인 job만 조회·확인 처리할 수 있다 (user_id 인가) | High | Pending |
| FR-09 | 기존 동기 채팅·스케줄·웹훅 실행 경로가 변하지 않는다 (백그라운드는 별도 엔드포인트 opt-in, 무회귀) | High | Pending |

### 3.2 Functional Requirements — M2

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-10 | 작업함 페이지에서 내 작업 목록(상태·요청 시각·소요 시간·에러)을 보고, 완료 작업의 결과 세션으로 이동할 수 있다 | High | Pending |
| FR-11 | 헤더 벨에 미확인 완료/실패 개수 배지가 표시되고, 드롭다운에서 확인 처리하면 배지가 감소한다 | High | Pending |
| FR-12 | 채팅에서 "백그라운드로 실행" 액션으로 현재 질문을 job으로 등록하고 접수 안내를 받는다 | High | Pending |
| FR-13 | 백그라운드로 넘긴 대화 세션에 복귀하면 완료된 답변이 표시되고, 진행중이면 진행중 상태가 표시된다 | High | Pending |
| FR-14 | 진행중 작업은 폴링으로 상태가 자동 갱신된다 (폴링 주기 config/상수화) | Medium | Pending |

### 3.3 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 레이어 준수 | job 엔티티·전이 정책=domain(순수), 워커 루프·use case=application, 큐 저장소·루프 기동=infrastructure/lifespan | verify-architecture 스킬 |
| DDL | V060 테이블+전 컬럼 COMMENT, FK CHARSET/COLLATE 금지, SQLAlchemy `comment=` 동반 | `tests/db/test_migration_ddl_comments.py` |
| TDD | 테스트 선행 (Red → Green) — 신규 모듈 전부 테스트 파일 동반 | verify-tdd 스킬 |
| DB 세션 | Repository commit 금지, 쓰기 세션 begin(), 단계별 짧은 트랜잭션 — 워커 루프가 세션을 보유하지 않음 (DB-001) | 코드 리뷰 + db-session.md |
| 회귀 안전 | 기존 pytest·vitest 무회귀 (사전 실패 목록 제외 기준), agent_schedule 테스트 전체 통과 유지 | 격리 실행 |
| 설정화 | 폴링 주기·동시 상한·틱 주기·job 타임아웃·reconcile 기준 전부 config — 하드코딩 금지 | 코드 리뷰 |
| 관측 | StructuredLogger + request_id 관통 (job_id 태깅), 실패 스택 트레이스 필수, 루프 예외가 루프를 죽이지 않음 | verify-logging 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done — M1

- [ ] job 등록 → 202 즉시 응답 → (클라이언트 없이) 워커가 실행 완료 → 상태 success + 세션에 답변 저장 (테스트 단언)
- [ ] 실행 중 예외 → 상태 failed + error_message 기록, 루프는 다음 job 계속 처리 (테스트 단언)
- [ ] queued 2건 + 상한 1 → 순차 실행, 동시 초과 없음 (테스트 단언)
- [ ] 서버 재기동 시나리오: queued 잔존 job 재개 + 방치된 running 정리 (테스트 단언)
- [ ] 스케줄러 틱 → TriggerDueSchedulesUseCase 호출 위임 확인, 외부 cron 없이 due 스케줄 실행 (테스트 단언 + E2E 수동)
- [ ] 타 사용자 job 조회 시도 → 403/404 (테스트 단언)

### 4.2 Definition of Done — M2

- [ ] 작업 등록 → 작업함에 진행중 표시 → 완료 후 벨 배지 +1 → 드롭다운 확인 → 세션 이동해 답변 열람 (MSW 통합 + E2E 수동)
- [ ] 백그라운드 전환한 채팅방 재입장 → 완료 답변 표시 (MSW 통합)

### 4.3 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, 상한·주기 값 config화

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **백그라운드 실행 중 HITL 질문 발생** — planner HITL(fix-agent-planner-hitl)은 사용자 응답을 전제하는데 백그라운드엔 사용자가 없음 | High | Medium | Design에서 정책 확정: 1차 기본안은 "질문도 작업물" — 질문이 세션에 저장되고 job은 success(needs_input 표시 검토)로 종료, 사용자가 복귀해 이어서 답변. 백그라운드 job 프롬프트에 자율 진행 우선 가이드 주입 검토 |
| 같은 세션에 사용자가 계속 대화 + 백그라운드 job이 동시 기록 → 메시지 순서·컨텍스트 오염 | High | Medium | Design 확정: 진행중 job이 있는 세션은 프론트에서 입력 잠금 or job은 항상 등록 시점 스냅샷 컨텍스트로 실행. 최소한 동시 기록 시나리오를 테스트로 고정 |
| 워커 루프 예외로 루프 자체가 죽어 큐 전체 침묵 | High | Low | 루프 본체 try/except + 스택 트레이스 로깅, 틱 간 계속 진행. status 스냅샷(TriggerStatus 동형)으로 루프 생존 관측. 태스크 참조 lifespan 보유(GC 교훈) |
| running 중 서버 재시작 → 실행 중이던 작업의 애매한 상태 | Medium | Medium | 기동 reconcile: started_at 기준 오래된 running을 failed("서버 재시작으로 중단") 또는 재큐 — LLM 실행 비멱등성 고려해 Design에서 확정(기본안: failed + 사용자 재요청 유도) |
| 인프로세스 실행이라 무거운 job 다발 시 API 응답성 저하 | Medium | Medium | 동시 실행 상한 config(FR-07) + LLM 대기는 async라 이벤트 루프 비점유. 실측 후 상한 조정 |
| 다중 인스턴스 배포 시 중복 claim | Medium | Low | claim을 선점 UPDATE(조건부 WHERE status='queued')로 구현 — claim_due 선례. 현 단일 서버지만 패턴은 안전하게 |
| 내장 틱과 외부 cron 병행 시 스케줄 중복 실행 | Medium | Low | claim_due가 이미 선점 방식이라 중복 안전 — 문서에 "외부 cron 제거 권장" 명시, trigger 엔드포인트는 수동 백업으로 유지 |
| 벨/작업함 폴링 부하 | Low | Medium | 미확인 카운트는 경량 쿼리(user_id+seen_at 인덱스), 폴링 주기 보수적 설정(TanStack refetchInterval), 창 비활성 시 중단 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation | 기존 프로젝트 구조 | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 실행 내구성 | fire-and-forget task / **DB 큐+인프로세스 워커** / 외부 워커(Celery) | **DB 큐 + 인프로세스 워커** | 사용자 확정. 재시작 생존 + 상태 조회가 요구사항의 본질(작업함)이라 DB 기록은 필수 — 그 위에 인프로세스 루프면 신규 인프라 0. Celery는 단일 서버 규모에 과잉 |
| 스케줄 트리거 | 외부 cron 유지 / **워커 루프에 틱 내장** | **내장 틱 (기존 use case 호출)** | TriggerDueSchedulesUseCase를 그대로 주기 호출 — 스케줄 로직 무변경으로 cron 의존 제거. claim 선점 구조라 외부 cron 병행에도 중복 안전 |
| ad-hoc job 실행 본체 | 신규 실행 경로 / **RunAgentUseCase 재사용** | **RunAgentUseCase 재사용** | 스케줄 경로가 이미 헤드리스 재사용 중(세션 생성+메시지 저장 포함) — 결과가 세션에 남는 계약이 "채팅방 복귀 시 결과 표시"(FR-13)를 공짜로 해결 |
| job 등록 진입점 | 기존 채팅 API에 플래그 추가 / **별도 job 엔드포인트** | **별도 엔드포인트 (opt-in)** | 기존 계약 갈아끼우기 금지 관례(독립 opt-in 선호) — 동기 경로 무회귀(FR-09)를 구조로 보장 |
| 알림 전달 | WS 푸시 / **폴링(벨 카운트+작업함)** | **폴링 1차** | 사용자 확정 UX 4종 중 실시간성 요구 최소 수준 — 미확인 카운트 경량 쿼리 + refetchInterval로 충분. WS 푸시는 후속 |
| 작업물 연결 | job에 결과 본문 복사 저장 / **session_id·run_id 참조** | **참조 (세션이 원본)** | 대화 답변=작업물(사용자 확정) — 본문 이중 저장은 정합성 부채. 작업함은 세션으로 이동만 |
| 스케줄 run 이력과의 관계 | job 테이블로 통합 이관 / **별도 유지 + 조회 통합은 Design 검토** | **별도 유지** | agent_schedule_run 이관은 스키마 임의 변경 리스크 — 1차는 ad-hoc job만 신규 테이블, 작업함에서의 통합 표시 여부만 Design에서 결정 |

### 6.3 변경 대상 파일 (예상)

```
idt/
├── db/migration/
│   └── V060__create_agent_background_job.sql        # S1 (M1)
├── src/
│   ├── domain/background_job/                       # S2: 엔티티·상태 전이 정책·인터페이스 (순수)
│   ├── application/background_job/
│   │   ├── enqueue_job_use_case.py                  # S5: 등록 (202 + job_id)
│   │   ├── list_jobs_use_case.py / get·mark_seen    # S5: 조회·확인 처리 (user_id 인가)
│   │   └── worker_loop.py                           # S4: 폴링 루프 + 스케줄러 틱 + reconcile
│   ├── infrastructure/background_job/
│   │   ├── models.py + job_repository.py            # S1·S3: 큐 저장소 (claim 선점 UPDATE)
│   │   └── (상태 전이 sink — run_sink 동형)          # S3
│   └── api/
│       ├── routes/background_job_router.py          # S5
│       └── main.py                                  # DI 배선 + lifespan 루프 기동/종료
└── tests/ (domain·application·infrastructure·api)    # S6

idt_front/src/                                        # M2
├── constants/api.ts + types/ + services/ + hooks/   # S10: 계약 동기화
├── pages/JobsPage/ (+test)                          # S7: 작업함
├── components/layout/ (헤더 벨 +test)                # S8
└── components/chat/ (백그라운드 전환 액션 +test)      # S9
```

> job 스키마 필드 상세·claim SQL·HITL/세션 동시성 정책·reconcile 기준·폴링 주기 값·
> 작업함의 스케줄 run 통합 표시 여부는 Design 단계에서 확정.

---

## 7. Convention Prerequisites

- [x] DDL: 테이블+전 컬럼 COMMENT, FK CHARSET/COLLATE 금지 (errno 3780 선례), SQLAlchemy `comment=` 동반 — V060 적용
- [x] DB 세션: Repository 내 commit 금지, 쓰기 세션 begin(), 워커 루프는 세션 비보유 + 단계별 짧은 트랜잭션 (`docs/rules/db-session.md`, DB-001)
- [x] 로깅: StructuredLogger + request_id (job_id 태깅), 스택 트레이스 필수 (`docs/rules/logging.md`)
- [x] 백그라운드 태스크: create_task 참조 보유 (agent-webhook Check G1 교훈)
- [x] 독립 opt-in: 기존 실행 API 무변경, 별도 엔드포인트 신설 (prefer-independent-optin 관례)
- [x] 프론트 관례: vitest `--pool=threads`, MSW per-file listen, api-contract-sync 체크리스트, LoadingButton isPending (M2)
- [ ] Design 단계 확정 항목: HITL 질문 발생 시 job 종료 정책, 진행중 job 세션의 동시 대화 정책,
      reconcile 기준(failed vs 재큐)·shutdown 대기 정책, 워커 틱/폴링 주기·동시 상한 기본값,
      작업함의 스케줄 실행 이력 통합 표시 여부, 접수 안내 메시지의 세션 저장 여부
