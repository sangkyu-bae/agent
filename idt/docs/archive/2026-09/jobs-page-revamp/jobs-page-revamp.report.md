# jobs-page-revamp Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Completion Date**: 2026-09-04
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | jobs-page-revamp — 작업함 통합 이력 개편 + soft delete |
| Start Date | 2026-09-03 |
| End Date | 2026-09-04 |
| Duration | 2일 (세션 5회: Plan/Design 1, Do 3, Check+Act 1) |
| Final Match Rate | **96.5%** (목표 90%) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100%                       │
├─────────────────────────────────────────────┤
│  ✅ 완료:     16 / 16 FR                     │
│  ⏳ 이월:      0 / 16 FR                     │
│  ❌ 취소:      0 / 16 FR                     │
│                                              │
│  모듈: module-1 ~ module-5 전부 완료          │
│  변경: 24개 파일, +1,875 / −473 줄            │
│  테스트: 백엔드 150 + 프론트 42 = 192 passed  │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 작업함이 카드형 단순 나열이라 작업이 쌓이면 탐색이 불가능했고, 실패한 작업·테스트 찌꺼기를 **지울 방법이 전혀 없었다**. |
| **Solution** | 두 테이블(`agent_background_job` ∪ `agent_schedule_run`)을 DB에서 `union_all`로 정규화해 하나의 시간순 목록으로 만들고, 상태·유형·기간 3단 필터와 정확한 페이지네이션을 붙였다. 수동 작업에는 `deleted_at` 기반 soft delete(행 삭제 + 완료 항목 일괄 정리)를 제공한다. |
| **Function/UX Effect** | 시간/제목/상태/에이전트 4열 테이블 + 필터 10종 조합 + `N / M 페이지` 페이지네이션. 정렬·페이징·총건수를 **전부 DB가 계산**해 항목 누락·중복이 구조적으로 발생하지 않는다. 스케줄 정의 관리도 같은 화면에서 가능(활성 토글·삭제). |
| **Core Value** | 백그라운드 작업이 "던져두고 잊는 것"에서 **운영 가능한 목록**이 됐다 — 찾을 수 있고, 지울 수 있고, 데이터는 감사용으로 남는다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria (Plan §4) | 상태 | Evidence |
|---|---|:---:|---|
| SC-1 | FR-01 ~ FR-16 구현 완료 | ✅ Met | 16/16 (§3.1) |
| SC-2 | 백엔드 pytest Red→Green | ✅ Met | 150 passed |
| SC-3 | 프론트 Vitest (테이블·필터·삭제·페이지네이션) | ✅ Met | 42 passed (JobsPage 27 + Bell 11 + ChatPage 4) |
| SC-4 | api-contract-sync 동기화 | ✅ Met | `backgroundJob.ts` / `backgroundJobService.ts` / `api.ts` |
| SC-5 | 목표 스크린샷과 레이아웃 대조 | ✅ Met | 브라우저 런타임 확인 (Analysis §2) |
| SC-6 | `deleted_at IS NULL` 누락 경로 0건 | ✅ Met | §10.2 감사표 7/7 필터, 3/3 의도적 제외 |
| SC-7 | lint / 타입체크 에러 0 | ⚠️ Partial | ESLint 0, `vite build` 성공. `tsc -b`에 **기존 에러 다수** — 단 이 기능 파일은 0건 |
| SC-8 | 함수 40줄·if 중첩 2단 규칙 | ✅ Met | AST 검사 위반 0 |

**Success Rate: 7/8 (87.5%)** — SC-7만 부분. 저장소 전역의 선행 타입 에러(`CatalogTool`, vitest globals, `vite.config.ts`)는 이 사이클 범위 밖이며, 이 기능이 만든 에러는 0건이다.

## 1.5 Decision Record Summary

| Source | Decision | 준수 | Outcome |
|--------|----------|:---:|---------|
| [Plan] | 삭제는 soft delete (`deleted_at`) | ✅ | `run_id` 관측 추적·감사 이력 보존. V070 + `_active()` 헬퍼로 필터를 구조적으로 강제 |
| [Plan] | 삭제 대상은 수동 job만 | ✅ | 마이그레이션 1개로 축소. `deletable` 속성이 UI 분기까지 담당 |
| [Plan] | 정리 = 완료(success·failed) 전체 | ✅ | 진행 중 작업은 409로 보호 |
| [Plan] | 기존 `GET /jobs` 변경, 신규 엔드포인트 없음 | ⚠️ 부분 | module-5에서 `GET /api/v1/schedules` **신규 불가피** — 스케줄 CRUD가 에이전트별이라 가로지르는 조회가 불가능했다. Design v0.2에 사후 명세 반영 |
| [Design] | Option C — 기존 모듈 내 `union_all` | ✅ | 페이지네이션·`total` 정확. 유형 단일값이면 UNION 생략해 쿼리 단순화 |
| [Design] | 상태 공통 4값 정규화 | ✅ | `agent_schedule_run.status`가 부분집합이라 변환 로직 불필요 확인 |
| [Design] | KST 경계, 등록·예정 시각 기준 | ✅ | `period.py` + 경계값 단위 테스트 8건 (UTC/KST 날짜 불일치 케이스 포함) |
| [Design] | 복구 UI 없음 | ✅ | restore API·화면 미구현. `deleted_at`은 보존·감사 목적만 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [jobs-page-revamp.plan.md](../01-plan/features/jobs-page-revamp.plan.md) | ✅ v0.1 |
| Design | [jobs-page-revamp.design.md](../02-design/features/jobs-page-revamp.design.md) | ✅ v0.2 (Check 반영) |
| Check | [jobs-page-revamp.analysis.md](../03-analysis/jobs-page-revamp.analysis.md) | ✅ v0.2 (Act 반영) |
| Act | 본 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | 상태 | 근거 |
|----|---|:---:|---|
| FR-01 | `deleted_at` 컬럼 + 인덱스 | ✅ | `V070__…sql`, `models.py` |
| FR-02 | 전 조회/집계에서 `deleted_at IS NULL` 강제 | ✅ | `_active()` 헬퍼 + 파라미터화 테스트 7건 |
| FR-03 | `DELETE /jobs/{id}` 204 / 타인·미존재 404 | ✅ | `delete_use_cases.py`, `background_job_router.py` |
| FR-04 | 진행중 삭제 409 | ✅ | `JobDeletionPolicy` + repository WHERE 이중 방어 |
| FR-05 | `POST /jobs/cleanup` 일괄 정리 | ✅ | `soft_delete_completed` |
| FR-06 | 응답 `{items, total}` | ✅ | `JobListResponse` |
| FR-07 | 상태 필터 (all/running/done) | ✅ | `_STATUS_GROUPS` |
| FR-08 | 유형 필터 (all/manual/schedule) | ✅ | `_history_subquery` 분기 |
| FR-09 | 기간 필터 KST 경계 | ✅ | `period.py` |
| FR-10 | 4열 테이블 UI | ✅ | `JobHistoryTable.tsx` |
| FR-11 | 휴지통은 수동 job 행에만 | ✅ | `deletable` 속성 |
| FR-12 | 정리 버튼 + 확인 + 건수 토스트 | ✅ | `ConfirmDialog` 재사용 |
| FR-13 | 새로고침 — 목록 + 미확인 수 | ✅ | **Act에서 수정** (`refreshAll`) |
| FR-14 | `N / M 페이지` 페이지네이션 | ✅ | `JobPagination.tsx` |
| FR-15 | 스케줄 정의 목록·토글·삭제 | ✅ | `ScheduleDefinitionTable.tsx` + `GET /api/v1/schedules` |
| FR-16 | 삭제·정리 후 배지 즉시 제외 | ✅ | `invalidateJobs()` |

### 3.2 Non-Functional Requirements

| 항목 | 목표 | 달성 | 상태 |
|---|---|---|:---:|
| Data Integrity | soft delete 행 물리 보존 | `deleted_at` UPDATE만 수행, `run_id` 유지 | ✅ |
| Security | 본인 소유만, 타인 404 | 인가 가드 6/6 401 (런타임 확인) | ✅ |
| Compatibility | 계약 변경 후 기존 소비처 동작 | 3개 소비처 전부 동작 (1건은 사고 후 수정) | ⚠️ |
| Convention | 함수 40줄 / print 금지 / DB-001 | 위반 0 | ✅ |
| Performance | 통합 조회 p95 < 300ms | **미측정** — 데이터 0행이라 유의미한 측정 불가 | ⏳ |

### 3.3 Deliverables

| Deliverable | 위치 | 상태 |
|---|---|:---:|
| 마이그레이션 | `db/migration/V070__add_deleted_at_to_agent_background_job.sql` | ✅ 적용 확인 |
| 도메인 | `domain/background_job/{entity,interfaces,policies}.py` | ✅ |
| UseCase | `application/background_job/{period,delete_use_cases,query_use_cases,list_my_schedules_use_case}.py` | ✅ |
| Repository | `infrastructure/background_job/job_repository.py`, `infrastructure/agent_schedule/schedule_repository.py` | ✅ |
| API | `api/routes/background_job_router.py` (9 엔드포인트) | ✅ |
| 프론트 컴포넌트 | `pages/JobsPage/` (index + 5 컴포넌트) | ✅ |
| 프론트 계약 | `types/backgroundJob.ts`, `services/`, `hooks/`, `constants/api.ts` | ✅ |
| 테스트 | 백엔드 6파일 / 프론트 3파일 | ✅ |

---

## 4. Incomplete Items

### 4.1 다음 사이클 이월

| 항목 | 사유 | 우선순위 |
|---|---|---|
| **인증 L1 데이터 경로 검증** | 토큰 미확보 + `agent_background_job` 0행. 필터·페이징·삭제의 실제 응답은 SQL 조립 검증으로만 커버 | High |
| 성능 측정 (p95 < 300ms) | 데이터 없음 | Medium |
| Minor 6건 (M2 CAST, M3 queued 스피너, M5 정리 건수, M6 409 표시 위치, M7 모두 확인 버튼) | 영향 낮음, 근거는 Analysis §3에 기록 | Low |

### 4.2 취소/보류

| 항목 | 사유 | 대안 |
|---|---|---|
| 삭제 복구 UI (휴지통/Undo) | Plan에서 명시적 범위 제외 | `deleted_at`으로 데이터는 보존 — 필요 시 DB 복구 |
| 스케줄 실행 이력 전용 탭 | 작업 기록 탭의 `유형=스케줄` 필터가 대체 | 서버 엔드포인트 `/schedule-runs`는 계약 보존 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Check | Act 후 | Change |
|---|---|---|---|---|
| Design Match Rate | 90% | 94.7% | **96.5%** | +1.8%p |
| Structural | — | 98% | 98% | — |
| Functional | — | 96% | **99%** | +3%p |
| API Contract | — | 95% | **99%** | +4%p |
| Runtime | — | 92% | 92% | — |
| FR 충족 | 16 | 15.5 | **16/16** | +0.5 |
| Critical Issues | 0 | **0** | **0** | ✅ |
| soft delete 감사 | 100% | 100% | 100% | ✅ |

### 5.2 Resolved Issues

| Issue | 발견 경로 | 조치 | 결과 |
|---|---|---|:---:|
| `ChatPage`의 `useJobList` import 누락 → **앱 전체 마운트 실패** | 사용자 신고 | `useJobHistory({type:'manual', status:'running'})`로 전환 + 테스트 갱신 | ✅ |
| FR-13 — 새로고침이 벨 배지를 갱신하지 않음 | gap-detector | `invalidateUnseenCount()` 신설, `refreshAll()` | ✅ |
| `GET /api/v1/schedules` 설계 문서 미기재 | gap-detector | Design v0.2 §4.1·§4.2·§11.1 갱신 | ✅ |
| TOCTOU — 상태 확인 후 워커 claim 시 진행중 job 삭제 가능 | gap-detector | `soft_delete` WHERE에 상태 조건 추가 + 회귀 테스트 | ✅ |
| 죽은 상수 `MY_SCHEDULE_RUNS` | gap-detector | 제거 (서버 엔드포인트는 유지) | ✅ |
| 전폭 레이아웃 요청 시 탭이 화면 끝까지 벌어짐 | 사용자 요청 처리 중 발견 | 탭 `inline-flex` 전환 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 잘된 것 (Keep)

- **§10.2 "메서드 전수 점검표"를 설계 단계에서 표로 못 박은 것.** 프로젝트 첫 soft delete였는데, 필터가 필요한 메서드 7개와 **의도적으로 제외할 3개(워커 경로)를 근거와 함께** 미리 적어둔 덕에 구현·검증 모두 흔들림이 없었다. gap-detector 감사 결과 100%.
- **회귀 테스트를 구현보다 먼저 정한 것.** "삭제한 작업이 벨 배지에 되살아난다"는 실패 모드를 Plan 리스크로 지목하고 L1 #14~16으로 테스트를 지정해, `_active()` 적용 전에 파라미터화 테스트를 넣었다.
- **모듈 5분할.** 각 모듈이 독립적으로 Green이라 세션 경계에서 상태가 깨지지 않았고, module-5에서 백엔드 갭(에이전트별 스케줄 API)을 발견했을 때도 앞 모듈에 영향이 없었다.
- **설계안 3개 비교 시 UX 결함을 정량화한 것.** Option A(프론트 병합)를 "페이지네이션 부정확"으로 명시해 배제한 판단이 끝까지 유효했다.

### 6.2 개선할 것 (Problem)

- **Impact Analysis가 실제 소비처를 놓쳤다.** Plan §6.2에 `GET /jobs` 소비처를 2곳으로 적었으나 실제는 3곳(+테스트 1). `grep` 결과를 `head`로 자른 채 문서에 옮긴 것이 원인이고, 결과는 **앱 전체 화이트스크린**이었다. 사용자가 발견했다.
- **검증 명령이 아무것도 검증하지 않았다.** `tsc --noEmit`은 이 저장소 루트 `tsconfig.json`이 `"files": []` + project references라 **0개 파일을 검사**한다. 3개 세션에 걸쳐 "타입 에러 0"을 근거 없이 보고했다.
- **빌드를 한 번도 돌리지 않았다.** 단위 테스트는 훅을 모킹하므로 `MISSING_EXPORT`를 구조적으로 잡을 수 없다. `vite build` 1회면 즉시 잡혔을 사고다.
- **문서를 코드에 맞춰 갱신하지 않았다.** module-5에서 엔드포인트를 신설하고 `list_by_user`를 제거했으면서 Design 문서를 그대로 뒀고, Check에서야 I1으로 잡혔다.

### 6.3 다음에 시도할 것 (Try)

- **계약 변경 체크리스트**: 이름·시그니처·응답 형태를 바꿀 때 `grep -rn <심볼> src` 를 **`head` 없이** 돌리고, 결과 건수를 Plan §6.2에 그대로 옮긴다.
- **세션 종료 게이트**: 프론트 변경 세션은 `vite build` + `tsc -b`, 백엔드는 `pytest` 전체를 돌리고 끝낸다. 테스트 통과만으로 "완료"라고 하지 않는다.
- **검증 명령의 유효성 자체를 1회 확인**: 새 저장소에서 처음 쓰는 검증 명령은 "일부러 깨뜨렸을 때 실패하는지"를 한 번 확인한다.
- **모듈 완료 시 설계 문서 델타 반영**: `--scope` 세션이 끝날 때 그 모듈이 만든 문서 변경(신규 엔드포인트, 제거된 API)을 즉시 반영한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA 프로세스

| Phase | 현재 | 개선 제안 |
|---|---|---|
| Plan | Impact Analysis가 수동 grep 기반 | 소비처 조사 결과를 **명령어와 함께** 문서에 남겨 재현 가능하게 |
| Design | §10.2 전수 점검표가 매우 효과적이었음 | 횡단 관심사(soft delete, 권한, 캐시 무효화) 도입 시 **표준 산출물로 격상** |
| Do | 모듈별 종료 기준이 "테스트 통과"에 한정 | 빌드·타입체크·문서 델타를 종료 기준에 포함 |
| Check | gap-detector가 사람이 놓친 6건을 잡아냄 | 유지. 다만 **런타임 L1은 인증 픽스처가 없어 반쪽** — 테스트용 토큰 발급 경로 마련 |

### 7.2 도구/환경

| 영역 | 개선 제안 | 기대 효과 |
|---|---|---|
| 타입체크 | `package.json`의 `type-check` 스크립트를 `tsc -b`로 교정 | 잘못된 안심 제거 |
| 테스트 | 저장소 전역 선행 실패 58건(백엔드)·9건(프론트) 정리 | 신규 회귀와 기존 실패 구분 비용 제거 |
| 검증 | 인증 토큰 픽스처 + 시드 데이터 | L1 데이터 경로 자동 검증 가능 |

---

## 8. Next Steps

### 8.1 즉시

- [ ] 실제 데이터로 동작 확인 (작업 등록 → 목록·필터·삭제·정리)
- [ ] 성능 측정 (p95 < 300ms)
- [ ] `/pdca archive jobs-page-revamp`

### 8.2 다음 PDCA 사이클 후보

| 항목 | 우선순위 |
|---|---|
| 테스트 인증 픽스처 + 시드 (L1 데이터 경로 자동화) | High |
| `type-check` 스크립트 교정 + 저장소 선행 타입 에러 정리 | High |
| 작업 재실행(retry) / 취소(cancel) | Medium |
| 남은 Minor 6건 | Low |

---

## 9. Changelog

### jobs-page-revamp (2026-09-04)

**Added:**
- `agent_background_job.deleted_at` 소프트 삭제 (V070) + 복합 인덱스
- `DELETE /api/v1/jobs/{job_id}` — 단건 소프트 삭제 (204 / 409 / 404)
- `POST /api/v1/jobs/cleanup` — 완료 작업 일괄 정리
- `GET /api/v1/schedules` — 내 스케줄 정의 전체 (작업함 스케줄 작업 탭)
- 작업함 테이블 UI: 필터 3종(상태·유형·기간), 페이지네이션, 행별 삭제, 정리·새로고침
- 스케줄 작업 탭: 스케줄 정의 목록 + 활성 토글 + 삭제

**Changed:**
- `GET /api/v1/jobs` — 응답 배열 → `{items, total}`, 수동 job + 스케줄 실행 통합 이력으로 확장
- `JobsPage` 카드형 → 전폭 테이블형 전면 개편
- `NotificationBell` — `type=manual` 고정으로 배지·목록 일관성 확보

**Removed:**
- `BackgroundJobRepository.list_by_user` / `ListJobsUseCase` (통합 조회로 완전 대체)
- 프론트 스케줄 실행 이력 클라이언트 코드 (서버 엔드포인트는 계약 보존)

**Fixed:**
- `ChatPage`가 이름이 바뀐 훅을 import해 앱 전체가 렌더되지 않던 문제
- 새로고침이 미확인 배지를 갱신하지 않던 문제 (FR-13)
- 진행 중 작업이 경합 상황에서 삭제될 수 있던 TOCTOU

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-04 | 완료 보고서 작성 — Match Rate 96.5%, FR 16/16 | 배상규 |
