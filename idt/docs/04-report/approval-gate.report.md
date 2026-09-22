# approval-gate 완료 보고서

> **Status**: Complete (운영 조치 2건 잔여 — §8.1)
>
> **Project**: sangplusbot (idt / idt_front)
> **Author**: 배상규
> **Completion Date**: 2026-09-21
> **PDCA Cycle**: #1 (Check 1회 + Act 1회)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | approval-gate — 비가역 도구 호출용 공통 승인 게이트 + 예약 집행 + 런 재개 |
| Start Date | 2026-09-20 |
| End Date | 2026-09-21 |
| Duration | 2일 (Plan → Design → Do 5모듈 → Check → Act-1 → Report) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 83% (Check) → 94% (최종)        │
├─────────────────────────────────────────────┤
│  ✅ Complete:     25 / 26 FR                 │
│  ⚠️ Partial:       1 / 26 FR  (FR-06)        │
│  ❌ Cancelled:     0 / 26 FR                 │
│  Gap: G1~G10·G12·G13 해소 / G11 이월          │
│  라이브 L1: 16/16 PASS (V074 적용 후)         │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트가 메일 발송·건의사항 답변·금리 변경 같은 되돌릴 수 없는 작업을 사람 검증 없이 실행했다. 새벽 집행 작업은 사람을 그 시각에 묶어 둬야 했다. |
| **Solution** | 게이트 미들웨어가 도구를 호출하지 않고 승인 요청을 남긴 뒤 런을 종료한다. 사람이 미리 승인하면 에이전트별 cron(KST 기준)에 맞춰 워커가 정확히 1회 집행하고, 멈춘 지점부터 런을 재개한다. |
| **Function/UX Effect** | 관리자는 도구 화면의 스위치로, 소유자는 에이전트 편집 화면에서 게이트를 켠다. 승인·거절은 작업함 '승인 대기' 탭과 벨 배지에서 처리한다. 백엔드 테스트는 +108건(9,586 passed, 신규 실패 0)이고 라이브 API는 16/16 통과했다. |
| **Core Value** | 안전을 프롬프트가 아니라 **접근 경로 분리**로 보장한다. 이중 집행은 3중으로 막는다. 에이전트 코드를 고치지 않고 도구 플래그만으로 확장되는 공통 모듈이다. |

---

## 1.4 Success Criteria Final Status

> Plan §4.1 Definition of Done 기준. "Check 시점"은 Act 전 판정이다.

| # | Criteria | Check 시점 | 최종 | Evidence |
|---|---------|:-:|:------:|----------|
| SC-1 | FR-01~26 구현 | ⚠️ | ✅ | 25✅ / 1⚠️(FR-06 — 라우팅 종료로 사실상 성립) |
| SC-2 | TDD 준수 | ✅ | ✅ | 모듈마다 Red→Green. Act에서는 **결함을 정답으로 인코딩하던 테스트**(G13 UTC 기대값)를 먼저 교정 |
| SC-3 | 즉시 집행 E2E (적재→승인→집행→재개→최종 답변) | ⚠️ | ✅ | G1 해소. 재개 테스트가 모킹 없이 실제 `_save_assistant_message`를 탄다. 실 LLM 라이브 E2E는 미실행(§4.1) |
| SC-4 | 예약 집행 E2E (금리 시나리오) | ❌ | ✅ | G13: `ApprovalPolicy.next_execute_after`가 `0 0 * * *`를 KST 00:00(UTC 15:00)으로 계산. G5: 워커 루프에 tick이 합류(single-flight). 라이브 L1-08 tick 가드 통과 |
| SC-5 | 거절 → 사유 주입 재개 | ⚠️ | ✅ | 재개 경로가 SC-3과 같다 |
| SC-6 | 우회 차단 | ✅ | ✅ | `gate_middleware.py` handler 미호출. `_boom` handler로 sync·async 모두 고정 |
| SC-7 | `is_enforced` + `mode=off` → 발동 | ✅ | ✅ | `test_enforced는_mode_off를_무시하고_발동`. 설정 API도 enforced면 off 저장을 거부 |
| SC-8 | 멱등 (동시 승인 10 / claim 5워커 → 1회) | ✅ | ✅ | UNIQUE idempotency_key + 조건부 UPDATE + `FOR UPDATE SKIP LOCKED` |
| SC-9 | 마이그레이션 + 전 컬럼 COMMENT | ✅ | ✅ | V071~V074. `test_migration_ddl_comments.py` 통과, 로컬 DB 적용 확인 |
| SC-10 | 프론트 탭 + 에이전트 설정 노출 | ⚠️ | ✅ | `ApprovalGateSettingsPanel`을 `LeftConfigPanel` 편집 모드에 마운트, 관리자 도구 '승인 필요' 스위치 |

**Success Rate**: 10/10 (Check 시점 5/10). Context Anchor의 SUCCESS 3요소(승인 없이 0회 / 지정 시각에 정확히 1회 / 멈춘 지점부터 최종 답변)가 모두 성립한다. 단, SC-3·SC-5는 인프로세스 수준 검증이다.

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 기존 clarification 3경로는 유지하고 신규 공통 모듈을 둔다 | ✅ | 기존 경로 변경 0. 회귀 베이스라인 동일 |
| [Plan] | 집행 모델 A(무상태 종료 + 스냅샷 재개) + Protocol 교체 지점 | ✅ | `StatelessGate`가 `ApprovalGateInterface`를 구현한다. 컴파일러는 Protocol을 경유(G9) |
| [Plan] | 승인자 = 소유자, 역할 기반으로 쉽게 확장 | ✅ | `ApprovalPolicy.can_decide` + `ListApprovalsUseCase._owned_agent_ids` **두 지점**만 바꾸면 된다 |
| [Plan] | 기존 미들웨어 카탈로그 편입 + 에이전트별 제어 | ✅ | `MiddlewareType.APPROVAL_GATE`, `MergePolicy` config 오버라이드, 전용 설정 API |
| [Plan] | `execute_after` 예약 집행 (새벽 무인 집행) | ✅ | Check에서 KST 9시간 어긋남(G13)과 호출자 부재(G5)가 드러났고 Act에서 해소 |
| [Plan] | 관리자 강제(`is_enforced`) — 소유자는 끌 수 없음 | ✅ | 병합·API 양쪽에서 보장 |
| [Plan] | 게이트 도구 단독 워커 제약 | ✅ | 생성·수정 공용 `validate_gated_workers`(G10) |
| [Design] | Option C — 순수 미들웨어 + `_wrap_worker` 리프트 → `__end__` | ✅ | ToolErrorPolicy.summarize와 같은 패턴. 게이트는 DB를 모른다 |
| [Design] | 게이트 빌드 실패 시 fail-closed | ✅ | `middleware_builder` 재던짐 |
| [Design] | 스냅샷 = 런 최종 상태 (승인된 이탈) | ✅ | 재개 시 승인 결과를 `AIMessage(name=worker_id)`로 주입 후 supervisor 재진입 |

승인된 이탈 6건: 워커별 게이트 팩토리 / 스냅샷=최종 상태 / `resume_from_snapshot` + Protocol / 집행 후 정산 / repo가 agent_ids 수신 / ORM FK 제거.

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [approval-gate.plan.md](../01-plan/features/approval-gate.plan.md) v0.2 | ✅ Finalized |
| Design | [approval-gate.design.md](../02-design/features/approval-gate.design.md) v0.2 | ✅ Finalized |
| Check | [approval-gate.analysis.md](../03-analysis/approval-gate.analysis.md) v0.2 | ✅ Complete |
| Report | 현재 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| 그룹 | FR | Status | Notes |
|------|----|--------|-------|
| 게이트 골격 | FR-01 상태 기계 | ✅ | 표 기반 `_TRANSITIONS`, executed 종결 |
| | FR-02 requires_approval 이원화 | ✅ | 카탈로그 런타임 SoT. sync UPDATE에서 제외. 관리자 토글(G2)과 default 시드(G10) |
| | FR-03 게이트 차단 | ✅ | 마커 ToolMessage만 반환 |
| | FR-05 단독 워커 | ✅ | 생성·수정 공용 |
| | FR-06 런당 1건 | ⚠️ | 첫 게이트에서 `__end__` 라우팅으로 사실상 성립. `find_active_by_run`는 미호출 |
| | FR-07 승인 API | ✅ | list/detail/approve/reject/seen + internal tick |
| | FR-08 can_decide | ✅ | |
| | FR-09 Executor + Mock | ✅ | 실도구는 Phase 2 |
| | FR-10 멱등 | ✅ | 3중 방어 |
| | FR-16 감사 필드 | ✅ | decided_by/at, 집행 결과 |
| 미들웨어 편입 | FR-18 APPROVAL_GATE + 시드 | ✅ | V073 |
| | FR-19 config 검증 | ✅ | mode/execute_after/expires_hours/on_expire/**timezone** |
| | FR-20 is_enforced 우선 | ✅ | |
| | FR-21 합성 규칙 | ✅ | `ApprovalPolicy.should_gate` 단일 지점 |
| | FR-22 설정 화면 | ✅ | Check ❌ → Act에서 마운트 + 저장 API |
| 예약 집행 | FR-23 execute_after cron | ✅ | 타임존 인식(기본 Asia/Seoul) |
| | FR-24 claim_due 선점 | ✅ | 워커 내장 tick |
| | FR-25 실패·자동 재시도 없음 | ✅ | |
| | FR-26 window 검증 | ✅ | expires_at < execute_after면 승인 거부 |
| 재개 | FR-04 스냅샷 | ✅ | ≤256KB 절단, SCHEMA_VERSION=1 |
| | FR-11 결과 주입 재개 | ✅ | 원래 session_id(V074)로 저장 |
| | FR-12 거절 재개 | ✅ | |
| | FR-13 만료 | ✅ | 에이전트별 expires_hours(G4) |
| | FR-14 정의 변경 대조 | ✅ | 집행은 진행, 재개만 거부 — 요구사항 원문과 일치(G8) |
| | FR-15 작업함 탭 + unseen 합산 | ✅ | `{count, jobs, approvals}` |
| | FR-17 Gate Protocol | ✅ | StatelessGate |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 안전성 | 승인 없이 0회 | handler 미호출을 구조로 보장 + 회귀 테스트 | ✅ |
| 멱등성 | N회 승인·다중 워커 → 1회 | 3중 방어, SQL 컴파일 테스트 | ✅ |
| 강제 불가역성 | enforced는 비활성화 불가 | 병합 + 설정 API 거부 | ✅ |
| 무회귀 | 게이트 없는 에이전트 동일 | 백엔드 53 failed = 베이스라인 목록 동일 | ✅ |
| 예약 정확도 | 지연 ≤ tick 주기 | tick 60s(`APPROVAL_EXECUTOR_TICK_SECONDS`) | ✅ |
| 스냅샷 용량 | ≤256KB | `dumps_with_limit` 절단 + 경고 | ✅ |
| 레이어 | domain 외부 미참조 | `domain/approval`은 표준 라이브러리 + croniter만 사용 | ✅ (verify 스킬 미실행, 수동 확인) |
| DDL COMMENT | 전 컬럼 | V071~V074 테스트 통과 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 마이그레이션 | `idt/db/migration/V071~V074` | ✅ (로컬 적용 완료) |
| Domain | `idt/src/domain/approval/` (entity, policies, interfaces) | ✅ |
| Application | `idt/src/application/approval/` (gate, decide, scheduler, list, gate_settings, resume_interface) | ✅ |
| 공용 배선 | `workflow_compiler`, `supervisor_*`, `run_agent_use_case`(적재·재개), `middleware_builder/provider`, `background_job/worker` | ✅ |
| Infrastructure | `idt/src/infrastructure/approval/` (models, repository, snapshot, mock_executor) | ✅ |
| API | `approval_router.py` (3개 라우터), `tool_catalog_router` requires_approval | ✅ |
| Frontend | `types/approval.ts`, `approvalService`, `useApprovals`, JobsPage 승인 탭, `ApprovalGateSettingsPanel`, AdminToolsPage 스위치 | ✅ |
| Tests | 백엔드 +108(Act) / approval 관련 340+, 프론트 approval 관련 60+ | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| 실도구 Executor (메일·MCP 등) | Plan상 Phase 2 범위. `approval-gate-phase2-mcp-executor`로 진행 중 | High | 별도 사이클 |
| 실 LLM 라이브 E2E (적재→승인→재개) | 현재 인프로세스·단위 수준 검증. 라이브는 API 계약(L1)까지만 확인 | Medium | 0.5일 |
| G11 승인 즉시 집행·재개가 HTTP 요청 안에서 동기 실행 | background_job 위임은 아키텍처 변경이라 사용자 승인 필요 | Medium | 1일 |
| FR-06 `find_active_by_run` 미사용 | 라우팅 종료로 사실상 성립. 방어 심화용 | Low | 0.5h |
| 목록 `agent_id` 필터 | Design §4에 있으나 UI 미사용 | Low | 1h |

### 4.2 Cancelled/On Hold

| Item | Reason | Alternative |
|------|--------|-------------|
| - | - | - |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Check | Act-1 | **최종** |
|--------|:-:|:-:|:-:|
| Structural | 95 | 98 | **98** |
| Functional | 79 | 98 | **98** |
| Contract | 83 | 95 | **95** |
| Runtime | 80 | 85 | **90** — V074 적용 후 라이브 L1 16/16 |
| **Overall** | ≈83 | ≈93 | **≈94** |

`98×0.15 + 98×0.25 + 95×0.25 + 90×0.35 = 94.45`. Runtime을 100으로 두지 않은 이유는 실 LLM 라이브 E2E를 돌리지 않았기 때문이다.

라이브 L1 (localhost:8000, 실 DB, 비변경 요청만):

| # | 검증 | 결과 |
|---|---|:-:|
| 01~09 | 목록 shape / 무인증 401 / size 422 / 404·422 / tick 토큰 가드 503 / 벨 배지 합산 | ✅ 9/9 |
| 10~12 | G3 게이트 설정 조회 200 / 타인 에이전트 조회·저장 403(쓰기 전 차단) | ✅ 3/3 |
| 13~14 | G2 `requires_approval=null` 400 / 카탈로그 응답 노출 | ✅ 2/2 |
| 15 | G7 타인 건 seen은 조용히 204(존재 비노출) | ✅ |
| 16 | V074 적용 후 전 상태 목록 200 (이전 500) | ✅ |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| G1 재개 답변 유실 (`SessionId("")`) | V074 session_id 영속 + 모킹 없는 저장 테스트 | ✅ |
| G13 예약 시각 KST +9h | `to_local → croniter → UTC`, config timezone | ✅ |
| G2 관리자가 게이트를 켤 입구 없음 | PATCH metadata + 관리자 스위치 | ✅ |
| G3 에이전트별 config 입구 없음 | GET/PUT approval-gate + 패널 마운트 | ✅ |
| G5 tick 호출자 없음 | 워커 루프 합류(single-flight) | ✅ |
| G4 expires_hours 고정 168h | 적재·승인이 같은 config 해석 함수 공유 | ✅ |
| G7 /seen 권한 누락 | 소유 agent_ids 범위 | ✅ |
| G6/G12/G8/G9/G10 | 에이전트명, UTC 직렬화, 정책 명시, Protocol 구현, 수정 경로 검증 | ✅ |
| (추가) 에이전트 수정 시 미들웨어 config 소실 | `_sync_middleware` config 보존 | ✅ |
| (추가) 게이트 행을 두 경로가 다툼 | `SEPARATELY_MANAGED_MIDDLEWARE_TYPES` | ✅ |
| (추가) 추상 메서드 추가로 앱 기동 실패 | 읽기 전용 구현체 가드 + 전 구현체 인스턴스화 테스트 | ✅ |
| (추가) cron 입력에 공백 불가 | 입력 중 trim 제거 | ✅ |
| (Do) sqlite 통합 테스트 91건 붕괴 | LONGTEXT variant + repo의 agent_definition ORM 참조 제거 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **기존 패턴 재사용**: ToolErrorPolicy 리프트, agent_schedule의 `claim_due`/타임존, 미들웨어 병합 시맨틱을 그대로 따랐다. 새 개념이 적어 리뷰 범위가 작았다.
- **회귀를 실측 베이스라인과 비교**: stash로 베이스라인을 측정해 "선행 실패"라는 추정을 바로잡았다(Do의 sqlite 91건은 실제로 신규였다).
- **Check가 실제 경로를 따라갔다**: 테스트 통과율이 아니라 "사용자가 실제로 쓸 수 있는가"로 판정했고, Critical 4건을 찾아냈다.

### 6.2 What Needs Improvement (Problem)

- **모킹이 결함 지점을 정확히 덮었다 (G1)**: 저장 함수를 모킹해 "호출됐다"만 확인했는데, 실패는 그 함수 안에서 났다.
- **시각 테스트가 한 기준계 안에서만 비교했다 (G13)**: "KST 00시"라는 사용자 문장이 테스트 어디에도 없었다.
- **"만들었다" ≠ "쓸 수 있다" (G2·G3·FR-22)**: 컬럼·파라미터·컴포넌트는 만들었지만, 그걸 켜는 입구(관리자 API, 설정 API, 페이지 마운트)를 Do 범위에 넣지 않았다.
- Do 보고에서 "금리 시나리오가 코드로 성립"이라고 한 것은 단위 테스트 기준이었다. 실행 경로 기준으로는 틀린 말이었다.

### 6.3 What to Try Next (Try)

- 핵심 경로마다 **모킹 없는 테스트 1개**를 두는 것을 Do 완료 조건으로 삼는다.
- 사용자의 시간·로캘 표현("새벽 0시")은 **그 표현 그대로** 테스트 이름과 기대값에 옮긴다.
- Design §11 모듈맵에 "입구(누가 이 값을 켜는가)" 열을 추가한다.

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Design | 데이터·로직 중심 모듈맵 | 설정값마다 쓰기 입구(API/UI)를 명시 |
| Do | 모듈 단위 단위 테스트 | 모듈 종료 시 실제 배선 경로 테스트 1건 필수 |
| Check | 정적 + L1 | 라이브 E2E(실 LLM 1회) 시나리오를 Design §8에 고정 |
| 운영 | 마이그레이션 적용 누락으로 로컬 500 | 기능 PR에 `ops/migration-deploy-deps` 등재 체크 |

---

## 8. Next Steps

### 8.1 Immediate (사용자 조치)

- [ ] `idt/.env.example`에 `APPROVAL_EXECUTOR_TICK_SECONDS=60` 한 줄 추가 (bkit 스코프 정책으로 자동 편집 차단됨. 미설정이어도 기본 60초로 동작)
- [ ] 배포 시 **V071~V074 선행 적용** (미적용 시 `/approvals`가 500을 반환한다 — 로컬에서 실측)
- [ ] 변경분 커밋/PR (현재 미커밋)

### 8.2 Next PDCA Cycle

| Item | Priority | Status |
|------|----------|--------|
| approval-gate-phase2-mcp-executor — 실도구 Executor | High | Design 진행 중 |
| G11 비동기 집행 위임 | Medium | 미착수 |

---

## 9. Changelog

### v1.0.0 (2026-09-21)

**Added:**
- 공통 승인 게이트 미들웨어(`approval_gate`)와 승인 요청 상태 기계, 3중 멱등 방어
- 에이전트별 게이트 설정(mode / execute_after cron / timezone / expires_hours) API·UI
- 예약 집행 스케줄러(워커 내장 tick + internal tick 엔드포인트)
- 승인·거절 후 런 재개 (최종 상태 스냅샷 복원 + 결과 주입)
- 작업함 '승인 대기' 탭, 벨 배지 `{count, jobs, approvals}`, 관리자 '승인 필요' 스위치
- V071~V074 마이그레이션

**Changed:**
- 에이전트 수정 시 미들웨어 config 보존, 게이트 행은 전용 API가 소유
- 게이트 도구 단독 워커 제약을 생성·수정 경로에 공통 적용

**Fixed:**
- (Act) 재개 답변 유실, 예약 시각 KST 어긋남, 응답 datetime UTC 미표기, /seen 권한 누락

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-21 | 완료 보고서 작성 — 최종 Match Rate ≈94%, 라이브 L1 16/16 | 배상규 |
