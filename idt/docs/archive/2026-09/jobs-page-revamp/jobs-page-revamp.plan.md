# jobs-page-revamp Planning Document

> **Summary**: 작업함(작업 기록/스케줄 작업) 화면을 테이블형으로 개편하고, 수동 작업의 soft delete·정리·필터·페이지네이션을 추가한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-09-03
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 작업함이 카드형 단순 목록이라 작업이 쌓이면 원하는 항목을 찾을 수 없고, 실패한 작업·테스트 찌꺼기를 지울 방법이 전혀 없다. |
| **Solution** | 작업 기록 탭을 수동 job + 스케줄 실행 통합 테이블로 재구성하고, 상태·유형·기간 3단 필터와 페이지네이션을 붙인다. 수동 job에 한해 `deleted_at` 기반 soft delete(행 삭제 + 완료 항목 일괄 정리)를 제공한다. |
| **Function/UX Effect** | 시간/제목/상태/에이전트 4열 테이블에서 필터로 원하는 작업을 즉시 좁혀 보고, 끝난 작업을 정리해 목록을 깨끗하게 유지할 수 있다. 두 번째 탭에서 등록된 스케줄 정의를 함께 관리한다. |
| **Core Value** | 백그라운드 작업을 "던져두고 잊는 것"이 아니라 **운영 가능한 목록**으로 만든다 — 찾을 수 있고, 지울 수 있고, 데이터는 남는 작업함. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 작업이 누적되면 탐색·정리가 불가능해 작업함이 사실상 방치된다 |
| **WHO** | P2 — 에이전트를 소유·운영하며 백그라운드/스케줄 작업을 반복 등록하는 KB 운영자 |
| **RISK** | `GET /api/v1/jobs` 응답 계약 변경(배열 → `{items,total}`)이 NotificationBell 등 기존 소비처를 깨뜨릴 수 있음 |
| **SUCCESS** | 필터 3종·페이지네이션 동작, 삭제/정리 후 목록·벨 배지에서 즉시 제외, 삭제 행은 DB에 `deleted_at`으로 보존 |
| **SCOPE** | S1 백엔드(마이그레이션·통합 조회·삭제 API) → S2 프론트(테이블 UI·필터·페이지네이션·삭제) → S3 스케줄 정의 탭 |

---

## 1. Overview

### 1.1 Purpose

네비바 → `/jobs` 작업함 페이지를 목표 스크린샷 레이아웃으로 개편하고, 누락된 **정리(삭제)** 기능을 soft delete 방식으로 추가한다.

### 1.2 Background

- `background-jobs` 기능(2026-08 아카이브)으로 등록·조회·확인(seen) API와 워커 루프는 이미 완성되어 있다.
- 그러나 현재 작업함은 카드형 2탭(`요청 작업` / `스케줄 실행`)의 단순 나열이며, **필터·정렬·페이지네이션·삭제가 전무**하다.
- 실패한 작업과 테스트 중 만든 작업이 목록에 영구히 남아, 사용할수록 화면이 나빠지는 구조다.
- 물리 삭제는 `run_id`(ai_run 관측)·감사 추적을 끊으므로 **soft delete**로 간다.

### 1.3 Related Documents

- 선행 기능 아카이브: `docs/archive/2026-08/background-jobs/` (plan/design/analysis/report)
- 목표 화면: `samples/job_1.png`
- 규칙: `idt/CLAUDE.md` §3 (DDL COMMENT 필수), `docs/rules/db-session.md`, `docs/rules/testing.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] `agent_background_job.deleted_at` 컬럼 추가 (마이그레이션 V070) + 전 조회 경로 필터
- [ ] `DELETE /api/v1/jobs/{job_id}` — 단건 soft delete (본인 소유만, 타인 404)
- [ ] `POST /api/v1/jobs/cleanup` — 완료(success/failed) 항목 일괄 soft delete
- [ ] `GET /api/v1/jobs` 확장 — 응답 `{items, total}`, 상태 그룹/유형/기간 필터 파라미터
- [ ] 수동 job + 스케줄 실행 **통합 조회** (유형 필터 `전체/수동/스케줄`)
- [ ] 작업 기록 탭: 시간/제목/상태/에이전트 테이블 + 새로고침 + 정리 + 행별 삭제 + 페이지네이션
- [ ] 스케줄 작업 탭: 등록된 스케줄 **정의** 목록 (기존 `agent_schedule` API 재사용)
- [ ] 프론트 타입/서비스/훅 동기화 (`api-contract-sync` 규칙)

### 2.2 Out of Scope

- 스케줄 실행 이력(`agent_schedule_run`)의 삭제 — 스케줄 삭제 시 CASCADE로 정리됨
- 삭제 복구 UI / 휴지통 화면 / Undo 토스트 (`deleted_at`은 데이터 보존·감사 목적만)
- 작업 재실행(retry), 취소(cancel), 상세 결과 모달
- 별도 `title` 컬럼 신설 — 제목 열은 job의 `query`, 스케줄 실행의 `schedule_name`을 매핑
- 스케줄 정의 탭의 신규 생성 플로우 (기존 에이전트 상세 화면 유지)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `agent_background_job`에 `deleted_at DATETIME NULL` 추가, 인덱스·COMMENT 포함 | High | Pending |
| FR-02 | 목록·단건·unseen-count·seen-all 등 **모든 조회/집계에서 `deleted_at IS NULL` 강제** | High | Pending |
| FR-03 | `DELETE /api/v1/jobs/{job_id}` — 본인 소유 job soft delete, 204. 타인/없음 404(사유 비구분) | High | Pending |
| FR-04 | 진행중(queued/running) job 삭제 시도는 409 Conflict — 실행 중 작업 보호 | High | Pending |
| FR-05 | `POST /api/v1/jobs/cleanup` — 본인의 success/failed job 전체 soft delete, `{deleted: N}` 반환 | High | Pending |
| FR-06 | `GET /api/v1/jobs` 응답을 `{items: [...], total: N}`으로 변경 | High | Pending |
| FR-07 | 상태 필터: `all` / `running`(queued+running) / `done`(success+failed) | High | Pending |
| FR-08 | 유형 필터: `all` / `manual`(수동 job) / `schedule`(스케줄 실행) — 통합 목록 | High | Pending |
| FR-09 | 기간 필터: `all` / `1h` / `today` / `week`, **KST 기준** 경계(자정·월요일), 기준 시각은 job=`queued_at`, 스케줄=`scheduled_for` | High | Pending |
| FR-10 | 프론트 작업 기록 탭 — 시간/제목/상태/에이전트 테이블, 실패는 빨간 상태 배지 | High | Pending |
| FR-11 | 행별 휴지통 버튼 — **수동 job 행에만 노출**, 스케줄 실행 행은 아이콘 숨김 | High | Pending |
| FR-12 | 헤더 `정리` 버튼 — 확인 다이얼로그 후 일괄 정리, 삭제 건수 토스트 | Medium | Pending |
| FR-13 | 헤더 `새로고침` 버튼 — 목록·미확인 수 재조회 | Medium | Pending |
| FR-14 | 페이지네이션 — `total` 기반 `N / M 페이지`, 이전/다음 버튼 | Medium | Pending |
| FR-15 | 스케줄 작업 탭 — 스케줄 정의 목록(이름/주기/다음 실행/활성 여부), 활성 토글·삭제는 기존 API 사용 | Medium | Pending |
| FR-16 | 삭제·정리 후 미확인 배지(`unseen-count`)에서 즉시 제외 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 통합 목록 조회 p95 < 300ms (본인 데이터 1,000건 기준) | 로컬 측정 / 쿼리 EXPLAIN |
| Data Integrity | soft delete된 행은 물리 삭제되지 않고 `run_id` 추적 유지 | DB 직접 조회 검증 |
| Security | 모든 job 경로는 소유자 검증, 타인 접근은 404(사유 비구분 — 기존 정책 유지) | pytest 인가 테스트 |
| Compatibility | 응답 계약 변경 후 NotificationBell·JobsPage 모두 정상 동작 | Vitest + 수동 확인 |
| Convention | DDL 테이블·전 컬럼 COMMENT (V054+ 규칙) | `tests/db/test_migration_ddl_comments.py` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-16 구현 완료
- [ ] 백엔드 pytest: 삭제/정리/필터/페이지네이션 케이스 Red → Green
- [ ] 프론트 Vitest: 테이블 렌더·필터 전환·삭제 확인 플로우·페이지네이션
- [ ] `api-contract-sync` — `types/backgroundJob.ts`, `services/backgroundJobService.ts`, `constants/api.ts` 동기화
- [ ] 목표 스크린샷과 레이아웃 대조 확인

### 4.2 Quality Criteria

- [ ] `deleted_at IS NULL` 누락 경로 0건 (repository 전 메서드 검토)
- [ ] lint / tsc 에러 0
- [ ] 함수 40줄·if 중첩 2단 규칙 준수 (CLAUDE.md §3)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `GET /jobs` 응답 배열 → `{items,total}` 변경이 NotificationBell을 깨뜨림 | High | High | 훅(`useJobList`)에서 `items`를 언래핑해 컴포넌트 계약 유지. NotificationBell 테스트 선수정 후 구현 |
| 조회 경로 일부에 `deleted_at` 필터 누락 → 삭제한 작업이 배지/목록에 재등장 | High | Medium | repository 인터페이스의 전 메서드를 체크리스트화, 각 메서드별 테스트 1건 강제 |
| 수동 job과 스케줄 실행의 통합 정렬·페이징이 두 테이블 UNION이라 복잡 | Medium | High | Design 단계에서 UNION 쿼리 vs 애플리케이션 병합 비교 후 선택. 유형 필터가 단일값일 땐 단일 테이블 쿼리로 분기 |
| KST 경계 계산 오류(오늘/이번 주)로 항목 누락 | Medium | Medium | 서버에서 KST 경계 → UTC naive 변환 후 비교, 경계값 단위 테스트(자정 직전/직후, 일요일/월요일) |
| 진행중 작업을 정리로 지워 워커가 고아 상태를 남김 | Medium | Low | FR-04로 진행중 삭제 차단, cleanup은 success/failed만 대상 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `agent_background_job` | DB Model | `deleted_at` 컬럼 추가 (V070), `(user_id, deleted_at, queued_at)` 인덱스 검토 |
| `GET /api/v1/jobs` | API | 응답 `{items,total}`로 변경 + `status`/`type`/`period`/`limit`/`offset` 파라미터 |
| `DELETE /api/v1/jobs/{job_id}` | API | 신규 |
| `POST /api/v1/jobs/cleanup` | API | 신규 |
| `JobRepositoryInterface` | Domain | `soft_delete`, `soft_delete_completed`, `count_by_user` 추가 / `list_by_user` 시그니처 확장 |
| `types/backgroundJob.ts` | Frontend Type | `deleted_at`, `JobListResponse`, 필터 타입 추가 |
| `pages/JobsPage/index.tsx` | Frontend Page | 카드형 → 테이블형 전면 개편 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `GET /api/v1/jobs` | READ | `pages/JobsPage/index.tsx` → `useJobList()` | Breaking — 응답 구조 변경, 전면 개편 대상 |
| `GET /api/v1/jobs` | READ | `components/layout/NotificationBell.tsx:33` → `useJobList({limit:20})` | Breaking — 훅에서 `items` 언래핑으로 흡수 |
| `GET /api/v1/jobs` | READ | `components/layout/NotificationBell.test.tsx` (mock 다수) | Breaking — mock 반환 형태 수정 필요 |
| `GET /jobs/unseen-count` | READ | `NotificationBell` 배지 | Needs verification — `deleted_at` 필터 반영 확인 |
| `POST /jobs/seen-all` | UPDATE | `JobsPage` 모두 확인 버튼 | Needs verification — 삭제된 행 제외 |
| `agent_background_job` | READ/UPDATE | `application/background_job/worker.py` (`claim_queued`, `finish`, `reconcile_orphan_running`) | Needs verification — 진행중 삭제 차단으로 영향 없어야 함 |
| `GET /api/v1/schedule-runs` | READ | `JobsPage` 스케줄 탭 | Needs verification — 통합 목록으로 흡수, 엔드포인트 자체는 유지 |
| `agent_schedule` CRUD | READ/UPDATE/DELETE | 에이전트 상세 화면 스케줄 관리 | None — 스케줄 작업 탭에서 재사용만 |

### 6.3 Verification

- [ ] 위 소비처 전부 변경 후 동작 확인
- [ ] 인가 정책(본인 소유만, 타인 404) 변경 없음 확인
- [ ] 워커 루프의 job 상태 전이가 `deleted_at` 도입 후에도 동일하게 동작

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| Starter | 단순 구조 | 정적 사이트 | ☐ |
| Dynamic | 기능 단위 모듈 | 웹앱 MVP | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DI | 기존 Thin DDD 구조 유지 | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 삭제 방식 | 물리 삭제 / soft delete | **soft delete (`deleted_at`)** | `run_id` 관측 추적·감사 이력 보존, 복구 여지 확보 |
| 삭제 대상 | job만 / job+스케줄 실행 | **수동 job만** | 스케줄 실행은 스케줄 삭제 시 CASCADE로 정리, 마이그레이션 1건으로 축소 |
| 정리 기준 | 완료 전체 / 필터 조건 / 기간 | **완료(success·failed) 전체** | 실수 위험 최소, API 파라미터 단순 |
| API 계약 | 기존 변경 / 신규 엔드포인트 | **기존 `GET /jobs` 변경** | 소비처가 2곳뿐이라 파급 작음, 유사 엔드포인트 난립 방지 |
| 기간 기준 | 등록·예정 시각 / 종료 시각 | **등록·예정 시각, KST 경계** | 진행중 항목도 기간 필터에 일관되게 포함 |
| 복구 UX | 없음 / 휴지통 / Undo | **없음** | 이번 범위 최소화, `deleted_at`은 데이터 보존 목적 |
| 상태 관리 | Zustand / TanStack Query | **TanStack Query** | 기존 `useBackgroundJobs` 훅 패턴 유지 |
| 테스트 | pytest / Vitest+RTL | **양쪽 모두** | 프로젝트 TDD 공통 원칙 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

idt/
  domain/background_job/          entity(deleted_at), interfaces(soft_delete/count)
  application/background_job/     delete_job / cleanup_jobs / list(통합·필터) use case, schemas
  infrastructure/background_job/  models(deleted_at), repository(필터 강제)
  api/routes/                     background_job_router.py (DELETE, cleanup, 확장 GET)
  db/migration/                   V070__add_deleted_at_to_agent_background_job.sql

idt_front/
  src/pages/JobsPage/             index.tsx (테이블 개편) + 하위 컴포넌트
  src/hooks/useBackgroundJobs.ts  useDeleteJob / useCleanupJobs / 필터 파라미터
  src/services/backgroundJobService.ts, src/types/backgroundJob.ts, src/constants/api.ts
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` (루트 + idt + idt_front) 코딩 규칙 존재
- [x] `idt/docs/rules/` 세부 규칙 (db-session, logging, testing)
- [x] ESLint / TypeScript / pytest 설정 존재

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| DDL COMMENT | exists (V054+ 강제) | `deleted_at` 컬럼 COMMENT + SQLAlchemy `comment=` 동반 | High |
| soft delete 패턴 | missing | 프로젝트 첫 soft delete — 조회 필터 강제 규칙을 repository 레벨에 고정 | High |
| 목록 응답 형태 | 혼재 | `{items, total}` 페이지네이션 응답 형태를 기준으로 삼을지 결정 | Medium |
| 프론트 상수 export | exists | 런타임 상수는 컴포넌트 파일에서 export 금지 → `src/types/*.ts` | Medium |

### 8.3 Environment Variables Needed

없음 (신규 환경변수 불필요).

---

## 9. Next Steps

1. [ ] 설계 문서 작성 — `/pdca design jobs-page-revamp` (통합 조회 방식 3안 비교 포함)
2. [ ] 마이그레이션 번호 확정 (현재 최신 V069 → V070)
3. [ ] TDD로 구현 — 백엔드 → 프론트 순

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-03 | 최초 작성 (Checkpoint 1·2 확정 반영) | 배상규 |
