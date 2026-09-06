# jobs-page-revamp Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: sangplusbot (idt + idt_front)
> **Analyst**: 배상규
> **Date**: 2026-09-04
> **Design Doc**: [jobs-page-revamp.design.md](../02-design/features/jobs-page-revamp.design.md)
> **Plan Doc**: [jobs-page-revamp.plan.md](../01-plan/features/jobs-page-revamp.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 작업이 누적되면 탐색·정리가 불가능해 작업함이 사실상 방치된다 |
| **WHO** | P2 — 에이전트를 소유·운영하며 백그라운드/스케줄 작업을 반복 등록하는 KB 운영자 |
| **RISK** | `GET /api/v1/jobs` 응답 계약 변경(배열 → `{items,total}`)이 NotificationBell 등 기존 소비처를 깨뜨릴 수 있음 |
| **SUCCESS** | 필터 3종·페이지네이션 동작, 삭제/정리 후 목록·벨 배지에서 즉시 제외, 삭제 행은 DB에 `deleted_at`으로 보존 |
| **SCOPE** | S1 백엔드 → S2 프론트 → S3 스케줄 정의 탭 (module-1 ~ module-5, 전부 완료) |

---

## Strategic Alignment Check

### Plan Alignment

| 요소 | 기대 | 상태 |
|------|------|:----:|
| Core Problem (WHY) | 누적된 작업의 탐색·정리 불가 | ✅ 필터 3종 + 페이지네이션 + soft delete 정리로 해소 |
| Target User (WHO) | P2 KB 운영자 | ✅ 본인 소유 자원만 조회·삭제 (타인 404) |
| Core Value | "운영 가능한 목록" | ✅ 찾을 수 있고, 지울 수 있고, DB엔 보존 |

**RISK 검증 결과**: 계약 변경이 실제로 소비처를 깨뜨렸다. Plan §6.2에 소비처를 2곳(JobsPage·NotificationBell)으로 기재했으나 실제로는 **`ChatPage/index.tsx`가 세 번째 소비처**였고, 이를 놓쳐 `MISSING_EXPORT`로 **앱 전체가 마운트 실패**했다. 사용자 신고 후 수정 완료(`ChatPage/index.tsx:18, 129-137`). Impact Analysis의 실효성 결함으로 §5에 기록한다.

### Success Criteria Status

| # | Criteria (Plan §4) | 상태 | Evidence |
|---|---|:---:|---|
| SC-1 | FR-01 ~ FR-16 구현 완료 | ✅ 16/16 | FR-13은 Act에서 해소 (§6 참조) |
| SC-2 | 백엔드 pytest Red→Green | ✅ | 149 passed (`background_job`, `agent_schedule`, router, db) |
| SC-3 | 프론트 Vitest (테이블·필터·삭제·페이지네이션) | ✅ | 42 passed (JobsPage 27 + Bell 11 + ChatPage bg 4) |
| SC-4 | api-contract-sync (types/services/constants) | ✅ | `backgroundJob.ts`, `backgroundJobService.ts`, `api.ts` 동기화 |
| SC-5 | 목표 스크린샷과 레이아웃 대조 | ✅ | 런타임 확인 (§4 참조) |
| SC-6 | `deleted_at IS NULL` 누락 경로 0건 | ✅ | §10.2 표 7/7 필터, 3/3 의도적 제외 |
| SC-7 | lint / tsc 에러 0 | ⚠️ | ESLint 0. `tsc -b`는 **기존 에러 다수** — 단 jobs-page-revamp 파일에는 0건 |
| SC-8 | 함수 40줄·if 중첩 2단 규칙 | ✅ | AST 검사 위반 0 |

**Success Rate: 6/8 완전 충족, 2건 부분**

### Decision Record Verification

| Source | Decision | 준수 | 비고 |
|---|---|:---:|---|
| [Plan] | soft delete (`deleted_at`) | ✅ | V070 + `_active()` 헬퍼 |
| [Plan] | 삭제 대상 수동 job만 | ✅ | `deletable` 속성으로 UI 분기 |
| [Plan] | 정리 = 완료(success·failed) 전체 | ✅ | `soft_delete_completed` |
| [Plan] | 기존 `GET /jobs` 변경 (신규 엔드포인트 X) | ⚠️ | `GET /api/v1/schedules` **신규 추가** — module-5에서 불가피, 설계 문서 미갱신 (I1) |
| [Design] | Option C — UNION 조회 | ✅ | `_history_subquery`, 유형 단일값이면 UNION 생략 |
| [Design] | 상태 공통 4값 정규화 | ✅ | 변환 불필요 확인 |
| [Design] | KST 경계, 등록·예정 시각 기준 | ✅ | `period.py` + 경계값 테스트 8건 |
| [Design] | 복구 UI 없음 | ✅ | restore API·화면 없음 |

---

## 1. Match Rate

**런타임 검증 실행됨** → `Overall = (Structural × 0.15) + (Functional × 0.25) + (Contract × 0.25) + (Runtime × 0.35)`

| 축 | 점수 | 근거 |
|---|:---:|---|
| Structural | 98% | Design §11.1 전 파일 + §5.3 전 컴포넌트 존재. §4.1 대비 엔드포인트 1개 초과(문서 미기재) |
| Functional | 96% | §5.4 체크리스트 18항목 중 17.25 충족. placeholder·TODO·mock 데이터 0 |
| Contract | 95% | 8/8 엔드포인트 Design↔router↔client 일치. 1개가 §4.2에 없음 |
| Runtime | 92% | L2 브라우저 검증 통과, L1 인가·라우팅 통과. **인증 토큰이 필요한 데이터 경로 L1은 미실행** |

**Overall Match Rate: 94.7%** (목표 90% 초과)

보조 지표: 소프트 삭제 감사 100% (7/7 필터, 3/3 의도적 제외), FR 충족 15.5/16.

---

## 2. Runtime Verification 결과

| 항목 | 결과 |
|---|---|
| 백엔드 `/health` | 200 |
| 프론트 `:5173` | 200 |
| **V070 마이그레이션** | **적용됨** — `agent_background_job.deleted_at` 컬럼 + `ix_agent_background_job_user_deleted_queued` 인덱스 실재 확인 |
| OpenAPI 라우팅 | 8개 경로 전부 등록, 쿼리 파라미터 `pattern`·기본값 설계와 일치 |
| 인가 가드 (L1) | `GET /jobs`, `/jobs/cleanup`, `/schedules`, `/jobs/unseen-count`, `DELETE /jobs/{id}`, `POST /jobs/cleanup` → **6/6 401** |
| UI 렌더 (L2) | `/jobs` 정상 렌더. 헤더(정리·새로고침)·탭 2종·필터 3종·테이블·페이지네이션 `1 / 1 페이지` 표시 |
| 탭 전환 (L2) | 스케줄 작업 탭 전환 시 필터 사라지고 스케줄 목록 영역 표시 |
| 빈 상태 (L2) | "조건에 맞는 작업이 없습니다" / "등록된 스케줄이 없습니다" |
| 콘솔 에러 | 0건 |
| 레이아웃 | 목표 스크린샷과 일치 (전폭, 네비바 정렬) |

> **미실행**: 인증 토큰이 필요한 데이터 경로 L1 (#1~#16 중 필터·페이징·삭제·정리의 실제 응답 검증). `agent_background_job` 테이블 행 수가 0이라 의미 있는 데이터 검증도 불가했다. 해당 시나리오는 단위·통합 테스트(SQL 조립 검증)로만 커버된다.

---

## 3. Gap List

### Critical

**없음.** 누락 엔드포인트·계약 불일치·`deleted_at` 필터 누락 모두 0건.

### Important

| ID | 내용 | 근거 | 조치 |
|---|---|---|---|
| **I1** | `GET /api/v1/schedules`가 설계 문서에 없음 | `background_job_router.py:222` 존재 / `design.md:176-185` §4.1 미기재 | 설계 문서 §4.1·§4.2·§11.1 갱신 (코드가 진실 — 문서를 옮긴다) |
| **I2** | FR-13 부분 미충족 — 새로고침이 미확인 수를 재조회하지 않음 | `index.tsx:164` `refetch()`는 `useJobHistory`만 갱신. `useUnseenCount`는 무효화 안 됨 (15초 자체 폴링에만 의존). §5.4(`design.md:372`)는 둘 다 요구 | `unseenCount` 키 무효화 추가 + 테스트 강화 |

### Minor

| ID | 내용 | 근거 |
|---|---|---|
| M1 | TOCTOU — `find_by_id`로 상태 확인 후 `soft_delete`까지 사이에 워커가 claim하면 `running` job이 삭제될 수 있음 | `delete_use_cases.py:34-43` / `job_repository.py:369-378` WHERE에 상태 조건 없음. 영향은 낮음 (`finish`는 필터 없이 종결 기록 → 고아 없음) |
| M2 | §4.3이 요구한 `title` 명시적 CAST 미적용 | `job_repository.py:91, 121` — MySQL 암묵 승격에 의존 (동작함, 이식성 가정) |
| M3 | `queued`도 `running`과 같은 스피너 표시 | `StatusBadge.tsx:13` `isJobActive` 사용. 라벨은 "대기 중"으로 정확 |
| M4 | 죽은 프론트 상수 잔존 | `constants/api.ts:268` `MY_SCHEDULE_RUNS` — 참조처 0 (서버 엔드포인트는 설계대로 유지) |
| M5 | 정리 다이얼로그에 건수 미표시 | §5.2(`design.md:341`)는 "N건" 문구. 사전 건수는 추가 질의 없이는 불가 — 사후 토스트로 대체 |
| M6 | 409가 토스트가 아닌 다이얼로그 내부에 표시 | §6.1/§8.3 #6. 행 유지는 동일 |
| M7 | JobsPage에서 "모두 확인" 버튼 소실 | Plan §6.2(`plan.md:166`)에 소비처로 기재. 기능은 NotificationBell에만 남음. §5.4 체크리스트엔 없어 설계 위반은 아님 |
| M8 | `deletable`이 dataclass 필드가 아닌 `@property` | `entity.py:59-62`. `type`과 어긋날 수 없어 오히려 안전 — 조치 불필요 |

---

## 4. Convention & Architecture Compliance

| 항목 | 결과 |
|---|:---:|
| 함수 40줄 초과 | ✅ 0건 (AST 검사, 12개 파일) |
| `print()` 사용 | ✅ 0건 |
| Repository 내 `commit()/rollback()` (DB-001) | ✅ 0건 |
| domain → infrastructure 참조 | ✅ 0건 (SQLAlchemy import 없음) |
| DDL COMMENT (V054+) | ✅ `tests/db/test_migration_ddl_comments.py` 통과 |
| 프론트 상수 export 위치 | ✅ 런타임 상수 전부 `types/backgroundJob.ts` |
| ESLint (기능 파일) | ✅ exit 0 |

---

## 5. 프로세스 회고 — 이번 사이클에서 드러난 검증 결함

| 결함 | 결과 | 재발 방지 |
|---|---|---|
| **Impact Analysis 소비처 누락** | `ChatPage`를 놓쳐 앱 전체 마운트 실패. 사용자가 "페이지 안 뜬다"로 발견 | 계약 변경 시 `grep`을 `head` 없이 전수 확인하고, 결과 건수를 Plan §6.2에 그대로 옮긴다 |
| **무의미한 타입체크 명령 보고** | `tsc --noEmit`은 루트 `tsconfig.json`이 `"files": []` + project references라 **아무 파일도 검사하지 않음**. 3개 세션에 걸쳐 "타입 에러 0"을 근거 없이 보고 | 이 저장소의 타입체크는 `tsc -b`. 빌드 검증은 `vite build`로 별도 확인 |
| **빌드 미실행** | 단위 테스트는 모듈을 모킹하므로 `MISSING_EXPORT`를 잡지 못했다 | 프론트 변경 세션 종료 전 `vite build` 1회 필수 |

---

## 6. 조치 결과 (Act — 2026-09-04)

Checkpoint 5에서 **Important 2건 + M1·M4** 수정을 선택해 즉시 반영했다.

| ID | 조치 | 결과 |
|---|---|---|
| **I2** | `invalidateUnseenCount()` 신설(`useBackgroundJobs.ts`), `refreshAll()` 핸들러가 목록·배지를 함께 갱신(`index.tsx`) | ✅ FR-13 완전 충족. 테스트가 두 호출을 모두 검증하도록 강화 |
| **I1** | Design 문서 v0.2 — §4.1 엔드포인트 표에 `GET /api/v1/schedules` 추가, §4.2에 상세 명세(배치 근거 포함), §11.1에 `list_by_user`/`ListJobsUseCase` 제거 기록 | ✅ 코드-문서 일치 회복 |
| **M1** | `soft_delete` WHERE 에 `status.in_(_FINISHED_STATUSES)` 추가 | ✅ TOCTOU 차단. 회귀 테스트 `test_where_excludes_active_jobs` 추가 |
| **M4** | `constants/api.ts` 의 `MY_SCHEDULE_RUNS` 제거 | ✅ 죽은 클라이언트 설정 제거 (서버 엔드포인트는 유지) |

**미조치 (문서화만)**: M2(CAST 생략), M3(queued 스피너), M5(정리 다이얼로그 건수), M6(409 표시 위치), M7(모두 확인 버튼 이동), M8(`deletable` property — 조치 불필요).

### 조치 후 검증

| 항목 | 결과 |
|---|---|
| 백엔드 pytest | **150 passed** (M1 회귀 테스트 1건 추가) |
| 프론트 Vitest (기능) | **42 passed** |
| `vite build` | ✅ 성공 |
| 함수 40줄 규칙 | ✅ 위반 0 |

**조치 후 Match Rate: 96.5%** — I2 해소로 Functional 96→99%, I1 해소로 Contract 95→99%, FR 충족 16/16.

---

## 7. Next Steps

1. `/pdca report jobs-page-revamp` — 완료 보고서
2. (선택) 인증 토큰을 확보해 L1 데이터 경로 시나리오 #1~#16 실행 — 현재는 SQL 조립 검증으로만 커버
3. (선택) 남은 Minor 6건 처리

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-04 | 최초 작성 — gap-detector 정적 분석 + 런타임(L1 인가·L2 UI) 검증 | 배상규 |
| 0.2 | 2026-09-04 | Act 반영 — I1·I2·M1·M4 수정 완료, Match Rate 94.7% → 96.5% | 배상규 |
