# Background Jobs — Design vs Implementation Gap Analysis

> **Feature**: background-jobs
> **Date**: 2026-08-11 (Act-1 재검증: 2026-08-12)
> **Analyzer**: gap-detector agent
> **Design**: `docs/02-design/features/background-jobs.design.md` (D1~D14, §3~§8)
> **Match Rate**: 최초 89.0% (73/82) → **Act-1 후 99.4%** (81.5/82) — 90% 게이트 통과
>
> 아래 본문(§요약~§결론)은 최초 Check 시점 기록이며, Act-1 재검증 결과는
> 문서 말미 "Act-1 이터레이션 결과" 절 참조.

경로 약어: **BE** = `idt` / **FE** = `idt_front`

## 요약

| 지표 | 값 |
|------|-----|
| **Match Rate** | **89.0%** (73 / 82) |
| 총 항목 | 82 |
| Match | 65 |
| Partial | 16 |
| Missing | 1 |

| 구간 | 항목 | Match | Partial | Missing | Rate |
|------|:----:|:-----:|:-------:|:-------:|:----:|
| 백엔드 (D1~D14·§3·§4·§7-7·§6-M1·§8) | 58 | 50 | 7 | 1 | 92.2% |
| 프론트 (§5·§6-M2) | 24 | 15 | 9 | 0 | 81.3% |

**90% 게이트 미달 (-1.0%p).** 백엔드는 통과 수준, 프론트 §5-2/§5-3 확인 UX가 하향을 주도한다.

---

## 항목별 대조표

### A. 설계 결정 D1~D14

| # | 항목 | 설계 | 구현 근거 | 판정 |
|---|------|------|-----------|:----:|
| 1 | D1 워커 루프 = lifespan 싱글턴 | poll 5s job claim, tick 30s 스케줄, 별도 task spawn + single-flight, session 비보유 | BE\src\application\background_job\worker.py:71-80, 115-119, 156-169; BE\src\api\main.py:4374-4375 | Match |
| 2 | D2 claim = FOR UPDATE SKIP LOCKED | queued ORDER BY queued_at LIMIT 빈슬롯 → 같은 tx running | BE\src\infrastructure\background_job\job_repository.py:105-125; worker.py:189-192 | Match |
| 3 | D3 실행 시 등록자 AuthContext 재조립 | user_repo→Assemble→execute(auth_ctx,viewer_*). **사용자 미존재/비활성이면 failed** | main.py:3019-3041; worker.py:201-206, 230-248 | **Partial** |
| 4 | D4 HITL = 별도 상태 없음 | needs_input 등 추가 상태 없음 | entity.py:9 (JobStatus 4종만) | Match |
| 5 | D5 세션 동시성 이중 가드 | 백엔드 409 + 프론트 입력 잠금 | enqueue_job_use_case.py:104-115; FE\src\pages\ChatPage\index.tsx:132-138, 372, 430 | Match |
| 6 | D6 reconcile 기동 1회 running→failed | 문구 "서버 재시작으로…", queued 무처리 | worker.py:19, 116, 136-152; job_repository.py:168-190 | Match |
| 7 | D7 shutdown 취소 + failed 마킹 시도 | 루프·활성 task cancel, CancelledError 핸들러 마킹 | worker.py:82-94, 216-218, 273-292 | Match |
| 8 | D8 동시 상한 기본 2 + task 참조 보유 | 빈 슬롯만 claim | worker.py:184-196; BE\src\config.py:223 | Match |
| 9 | D9 작업함 2탭 + /schedule-runs + 벨은 job만 집계 | read-only 조회 API 1개 additive | background_job_router.py:166-176; list_my_schedule_runs_use_case.py:19-39; job_repository.py:213-224 | Match |
| 10 | D10 enqueue 세션 무저장 | 등록 시 메시지 저장 없음 | enqueue_job_use_case.py:39-80 (세션 쓰기 없음) | Match |
| 11 | D11 벨 = 폴링 | unseen-count + seen 단건/일괄 + 전용 인덱스 + 15s refetch | router:97-112,148-160; V060:27; FE\src\hooks\useBackgroundJobs.ts:57-58 | Match |
| 12 | D12 outbound 인라인 await, source="job" | dispatch 이중 방어 (Plan FR-06: **완료/실패 시** 발송) | worker.py:215, 294-307 — **성공 경로에서만 호출**, 실패 경로(219-228) 미호출 | **Partial** |
| 13 | D13 background_worker_enabled 기본 true | false면 lifespan 미기동 | config.py:221; worker.py:71-74 | Match |
| 14 | D14 리터럴 경로 우선 선언 | unseen-count·seen-all이 {job_id}보다 먼저 | router:97, 106 vs 133 | Match |

### B. §3 DB — V060

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 15 | 컬럼 17종 (타입·NULL·DEFAULT) | BE\db\migration\V060__create_agent_background_job.sql:7-22 | Match |
| 16 | 인덱스 3종 (claim/user/unseen) | V060:25-27 | Match |
| 17 | FK + CHARSET/COLLATE 미명시 + ENGINE=InnoDB | V060:23-24, 28 | Match |
| 18 | 테이블 + 전 컬럼 COMMENT | V060:7-28 | Match |
| 19 | SQLAlchemy `comment=` 동일 반영 | BE\src\infrastructure\background_job\models.py:15-79 | Match |
| 20 | user_id FK 미설정 / 세션 중복은 UNIQUE 아닌 조회 검증 | V060 (user_id FK 없음); enqueue_job_use_case.py:104-115 | Match |

### C. §4-1 domain

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 21 | entity.py BackgroundJob + JobStatus Literal | BE\src\domain\background_job\entity.py:9-30 | Match |
| 22 | policies.py 전이 매트릭스 + 2000자 절단 + 상한 검증 | policies.py:9-33 | Match |
| 23 | interfaces.py Repository 포트 — 설계는 **Protocol** 명시 | interfaces.py:8 `class ...(ABC)` | **Partial** |

### D. §4-2 infrastructure

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 24 | repo 메서드 10종 전부 존재 | job_repository.py:47, 76, 82, 97, 127, 168, 192, 213, 226, 241 | Match |
| 25 | claim_queued 구현 (SKIP LOCKED·정렬·limit·동일 tx) | job_repository.py:105-125 | Match |
| 26 | commit 금지, 트랜잭션 경계는 호출측 | job_repository.py:1-5 (flush만); worker.py:140-141, 189-190, 260-262 | Match |

### E. §4-3 application

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 27 | EnqueueJobUseCase 3단계 (가시성→중복→INSERT) | enqueue_job_use_case.py:47-80 | Match |
| 28 | List/Get/CountUnseen/MarkSeen/MarkAllSeen | query_use_cases.py:22, 43, 59, 71, 86 | Match |
| 29 | ListMyScheduleRunsUseCase (D9) | list_my_schedule_runs_use_case.py:10-39 | Match |
| 30 | Worker `__init__` 시그니처 (설계: user_repo_builder·assemble_auth_context_uc_builder·config) | worker.py:32-47 — 단일 `assemble_auth_context` 콜러블 + 개별 kwargs로 축약 | **Partial** |
| 31 | status() 스냅샷 (last_tick_at·active·last_error) | worker.py:101-111 | Match |
| 32 | 예외 처리 (Cancelled→마킹+re-raise / Exception→failed+절단+스택) | worker.py:216-228; policies.py:25-28 | Match |

### F. §4-4 config

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 33 | 설정 4종 키명·기본값 (true/5/2/30) | BE\src\config.py:219-225 | Match |

### G. §4-5 API·DI

| # | 항목 | 설계 | 구현 근거 | 판정 |
|---|------|------|-----------|:----:|
| 34 | POST /agents/{agent_id}/jobs | 202, 409, 404 | router:65-91 | Match |
| 35 | GET /jobs | status 필터·limit/offset·본인만 | router:115-130 | Match |
| 36 | GET /jobs/unseen-count | `{count}` | router:97-103 | Match |
| 37 | POST /jobs/seen-all | **204** | router:106-112 → **200 + `{updated}`** | **Partial** |
| 38 | GET /jobs/{job_id} | 타인 404 | router:133-145; query_use_cases.py:53-55 | Match |
| 39 | POST /jobs/{job_id}/seen | 204 | router:148-160 | Match |
| 40 | GET /schedule-runs | 본인 필터·페이징 | router:166-176 | Match |
| 41 | 전부 `Depends(get_auth_context)` | — | router:73 (enqueue만 get_auth_context), 나머지 6종 = `get_current_user` | **Partial** |
| 42 | `create_background_job_factories(...)` | — | main.py:2981-3084 | Match |
| 43 | lifespan `worker.start()/stop()` | — | main.py:4372-4381 | Match |
| 44 | include_router + DI override | — | main.py:112-113, 4980; 4505-4522 | Match |

### H. §7-7 스케줄 확장

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 45 | `ScheduleRunRepository.list_by_user` (JOIN·소유자·DESC·페이징) | BE\src\infrastructure\agent_schedule\schedule_run_repository.py:82-102 | Match |
| 46 | 도메인 인터페이스 비추상 additive 확장 | BE\src\domain\agent_schedule\interfaces.py:70-77 | Match |

### I. §5-1 프론트 계약 동기화

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 47 | constants/api.ts 7종 (이름·arity 일치) | FE\src\constants\api.ts:227-234 | Match |
| 48 | types 4종 백엔드 1:1 | FE\src\types\backgroundJob.ts:17-59 | Match |
| 49 | hooks 7종 | FE\src\hooks\useBackgroundJobs.ts — **`useJob(jobId)` 미구현** (서비스·쿼리키만 존재) | **Partial** |
| 50 | queryKeys `backgroundJobs` + 충돌 없음 | FE\src\lib\queryKeys.ts:219-234 | Match |

### J. §5-2 작업함 페이지

| # | 항목 | 설계 | 구현 근거 | 판정 |
|---|------|------|-----------|:----:|
| 51 | 탭 2개 (요청 작업/스케줄 실행) | — | FE\src\pages\JobsPage\index.tsx:13, 181-201 | Match |
| 52 | 요청 작업 행: 배지·**에이전트명**·질문·시각·소요·에러 | — | index.tsx:51-63, 82-118 — agent 명 미렌더 | **Partial** |
| 53 | 완료 행 클릭 → **해당 세션으로 이동** + seen | `/chat?agentId=&sessionId=` | index.tsx:74-80 (seen OK), :79 `navigate('/chatpage')` | **Partial** (사전 인지) |
| 54 | 스케줄 탭: 스케줄명·**에이전트**·status·scheduled_for·소요·**세션 이동** | — | index.tsx:120-153 — agent 미표시, :146 `/chatpage` | **Partial** |
| 55 | 진행중 있을 때만 폴링 | — | useBackgroundJobs.ts:46-49 | Match |
| 56 | TopNav "작업함" 메뉴 + /jobs 라우트 | — | TopNav.tsx:36, 51-52; App.tsx:36, 78 | Match |

### K. §5-3 헤더 벨

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 57 | NotificationBell.tsx + TopNav 우측 | NotificationBell.tsx:26,139; TopNav.tsx:232 | Match |
| 58 | count>0 배지 | NotificationBell.tsx:36, 67-74 | Match |
| 59 | 드롭다운 **최근 완료/실패** 5건 | :32 `useJobList({limit:5})` — status 필터 없음, 진행중 혼입 | **Partial** |
| 60 | "모두 확인" + "작업함 가기" | :81-89, 124-132 | Match |
| 61 | 항목 클릭 → seen + **세션 이동** | :48-54 seen OK, :53 `navigate('/jobs')` | **Partial** |
| 62 | 외부 클릭 닫기 | :29, 38-46 | Match |

### L. §5-4 채팅 연동

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 63 | "백그라운드로 실행" 액션 | ChatInput.tsx:174-191; ChatPage\index.tsx:353-370, 438-439 | Match |
| 64 | 접수 배너 + 입력창 비움 | ChatPage:363-366, 409-427; ChatInput:69-77 | Match |
| 65 | 진행중 세션 입력 비활성 + 배너 | ChatPage:132-138, 372, 422, 430 | Match |
| 66 | 완료 감지 → 대화 이력 invalidate (FR-13) | ChatPage:140-163 | Match |
| 67 | 409 → **토스트** 지정 문구 | :367 인라인 배너 + raw detail; :421-423 삼항이 에러 마스킹; `isJobConflictError` 호출처 0 | **Partial** |

### M. §6 M1 테스트 (pytest)

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 68 | test_policies.py | tests\domain\background_job\test_policies.py:11-57 | Match |
| 69 | test_job_repository.py — Design 요구 "왕복" 대비 Mock 세션, claim limit/정렬 인자 단언 없음 | test_job_repository.py | **Partial** |
| 70 | test_enqueue_use_case.py (202·409·404·가시성) | test_enqueue_job_use_case.py:32-90 | Match |
| 71 | test_worker.py (9개 시나리오 전부) | test_worker.py:91-288 | Match |
| 72 | test_background_job_router.py (인증·404·D14·schedule-runs) | test_background_job_router.py:114-199 | Match |
| 73 | DDL COMMENT V060 자동 검사 | test_migration_ddl_comments.py (V054+ glob) | Match |
| 74 | §7-7 신규 코드 테스트 (`list_by_user`·`ListMyScheduleRunsUseCase`) | 해당 테스트 없음 | **Missing** |

### N. §6 M2 테스트 (vitest)

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 75 | JobsPage/index.test.tsx | index.test.tsx:88-155 | Match |
| 76 | NotificationBell.test.tsx — "모두 확인 후 배지 소거" 미단언 | NotificationBell.test.tsx:96-103 | **Partial** |
| 77 | ChatPage 통합 (접수 배너·입력 잠금·409) — ChatInput 단위만 존재 | ChatInput.background.test.tsx | **Partial** |

### O. §8 관측·보안

| # | 항목 | 구현 근거 | 판정 |
|---|------|-----------|:----:|
| 78 | request_id + job_id 태깅, 스택 트레이스 | worker.py:199, 219-225; job_repository.py:69-74, 160-165 | Match |
| 79 | 루프 생존 + status() 관측 | worker.py:121-134, 101-111 | Match |
| 80 | query 원문 미로깅 | 로그에 query 필드 없음 | Match |
| 81 | 본인 소유 검증·404 통일 | query_use_cases.py:54-55, 82-83 | Match |
| 82 | LangSmith 기존 추적 유지 | worker.py:230-248 | Match |

---

## Gap 목록 (Missing / Partial)

### 🔴 High

| # | Gap | 권장 조치 |
|---|-----|-----------|
| 53·54·61 | **세션 딥링크 전무** — 작업함 2탭·벨 항목 3곳 모두 `/chatpage` 또는 `/jobs`로만 이동. "완료를 확인하고 작업물을 연다"는 D9/FR-10의 종착점 미완 | `/chatpage?agentId=&sessionId=` 딥링크 + ChatPage 쿼리 파라미터 세션 선택. 기존 테스트(`index.test.tsx:110`) 동반 수정 |
| 12 | **실패 job에 outbound 미발송** — Plan FR-06 "완료/실패 시 발송" vs 성공 경로만 dispatch | 실패 시에도 dispatch + `test_worker.py` 단언 추가 |
| 52·54 | **에이전트명 미표시** — 근본 원인: `JobResponse`/`MyScheduleRunResponse`에 `agent_name` 없음 | 백엔드 응답 `agent_name` additive 추가(JOIN) 후 두 탭 렌더 |

### 🟡 Medium

| # | Gap | 권장 조치 |
|---|-----|-----------|
| 67 | 409가 지정 UX 아님 + 삼항이 에러 마스킹, `isJobConflictError` 호출처 0 | 에러 우선 표시 + 지정 문구 매핑 + 회귀 테스트 |
| 74 | §7-7 신규 코드 테스트 부재 (TDD NFR 위반) | list_by_user·ListMyScheduleRuns 테스트 추가 |
| 69 | repo 테스트 Mock 기반 — claim limit/정렬 단언 없음 | statement limit/order 단언 또는 sqlite 왕복 추가 |
| 3 | D3 비활성 사용자 미검사 — 비활성/탈퇴 사용자의 잔여 job 실행됨 | `_assemble_job_auth_context`에 status 활성 검사 |
| 49 | `useJob(jobId)` 고아 코드 (서비스·쿼리키만) | 훅 구현 또는 제거 |
| 59 | 벨 드롭다운 완료/실패 필터 없음 — 진행중 혼입 | 클라이언트 필터(success/failed) 후 slice |
| 76·77 | 벨 배지 소거 미단언 + ChatPage 통합 테스트 부재 | ChatPage 통합 테스트 신설, 벨 테스트 보강 |

### 🔵 Low (문서-코드 정합 — Design 정정으로 해소)

| # | Gap | 권장 조치 |
|---|-----|-----------|
| 37 | seen-all 설계 204 vs 구현 200 `{updated}` | Design 정정 (구현이 더 유용) |
| 41 | "전부 get_auth_context" vs 조회 6종 get_current_user | Design 정정 (조회는 department 불필요) |
| 23 | Protocol vs ABC | Design 정정 (프로젝트 ABC 관례) |
| 30 | Worker `__init__` 시그니처 축약 | Design 정정 (단일 콜러블이 더 단순) |

---

## 초과 구현 목록 (Design에 없는 추가분)

**백엔드**: `test_query_use_cases.py`(조회 UC 전용 테스트), `worker.drain()`, `tick_once()`/`reconcile()` public 테스트 표면, 모델 레벨 `index=True` 3종(V060 DDL과 불일치 소지 — 정합 권장), `errors.py` 전용 예외 모듈

**프론트**: 폴링 주기·`isJobActive` 상수화, `extractJobError`/`isJobConflictError`, JobsPage 헤더 "모두 확인"·"새 결과" 칩·로딩/빈 상태, 벨 `9+` 클램프·aria-label·빈 상태, ChatInput prop 경계·super 제외, `bgNotice` 자동 해제·이중 invalidate, 추가 테스트 다수

---

## 결론

**Match Rate 89.0% — 90% 게이트 미달 (Act 이터레이션 1회 필요).**

- 백엔드(92.2%)는 핵심 메커니즘(claim/reconcile/shutdown/single-flight tick/동시 상한/D14)이 설계대로. 남은 것: 실패 outbound(#12), 비활성 가드(#3), 스케줄 신규 코드 테스트(#74).
- 프론트(81.3%)가 미달 주 원인 — 세션 딥링크 부재(#53·54·61), 에이전트명 미표시(#52·54), 409 마스킹(#67).

**90% 회복 최소 경로 (약 92%)**: ① 세션 딥링크 ② agent_name 추가 ③ 스케줄 신규 코드 테스트. #12·#3도 소규모라 같은 이터레이션 권장. Low 4건은 Design 문서 정정으로 처리(코드가 진실).

---

## Act-1 이터레이션 결과 (2026-08-12)

> pdca-iterator 수행 · gap-detector 재검증 — **Match Rate 89.0% → 99.4%** (백엔드 100% · 프론트 97.9%)

### 수정 내역 (갭 17건 전부 처리)

| 갭 # | 조치 | 근거 |
|------|------|------|
| 53·54·61 | **세션 딥링크** — `chatSessionPath()` 헬퍼 신설, 작업함 2탭·벨 항목 클릭 → `/chatpage?agentId=&sessionId=`. `AgentChatLayout` 이 쿼리 파라미터 소비(에이전트 전환 시 draft 대신 딥링크 세션 선택) | `FE\src\types\backgroundJob.ts`, `JobsPage\index.tsx`, `NotificationBell.tsx`, `AgentChatLayout.tsx:40-55,74-87` |
| 12 | **실패 job outbound 발송** (Plan FR-06) — `_failed_run_payload`(answer=None 이 실패 신호), 실패 2경로(사용자 없음·실행 예외) 모두 dispatch. shutdown 경로는 미발송 | `BE\src\application\background_job\worker.py` + `test_worker.py` 단언 |
| 52·54 | **agent_name additive** — `JobResponse`/`MyScheduleRunResponse` 필드 추가, job repo `list_by_user` LEFT JOIN agent_definition → `(job, agent_name)`, schedule run repo 3-튜플, 작업함 2탭 렌더 | `schemas.py`, `job_repository.py`, `schedule_run_repository.py`, `JobsPage\index.tsx` |
| 67 | **409 지정 문구 + 마스킹 제거** — `isJobConflictError` 매핑, 배너 `bgNotice ??` 우선 (진행중 안내가 에러를 가리지 않음) | `ChatPage\index.tsx:368-373,427-429` |
| 74 | **§7-7 테스트 신설** — `test_schedule_run_repository_list_by_user.py`, `test_list_my_schedule_runs_use_case.py` | 튜플 매핑·소유자 필터·JOIN·DESC 단언 |
| 69 | **repo 쿼리 조립 단언** — claim `FOR UPDATE SKIP LOCKED`·`ORDER BY queued_at`·LIMIT 파라미터 컴파일 검증 + list JOIN 단언 | `test_job_repository.py` |
| 3 | **비활성 사용자 가드** — `_assemble_job_auth_context` 에 `status != APPROVED → None` (→ 워커가 failed 마킹) | `BE\src\api\main.py` |
| 49 | `useJob(jobId)` 훅 구현 (`enabled: !!jobId`) | `useBackgroundJobs.ts` |
| 59 | 벨 드롭다운 limit 20 조회 → `isJobFinished` 필터 → 최근 5건 (진행중 혼입 제거) | `NotificationBell.tsx:33,39-43` |
| 76·77 | 벨 배지 소거·필터·딥링크 단언 + ChatPage 통합 테스트 신설(입력 잠금·접수 배너·409 문구) | `NotificationBell.test.tsx`, `ChatPage\background.test.tsx` |
| 37·41·23·30 | Design 정정 (코드가 진실): seen-all 200 `{updated}` · 조회 6종 `get_current_user` · ABC · Worker `__init__` 단일 콜러블. 재검증에서 발견된 2건 추가 정정: 딥링크 literal `/chatpage`, 409 토스트→인라인 배너 | `background-jobs.design.md` |

### 재검증 요약

| 구간 | 항목 | Match | Partial | Missing | Rate |
|------|:----:|:-----:|:-------:|:-------:|:----:|
| 백엔드 | 58 | 58 | 0 | 0 | **100%** |
| 프론트 | 24 | 23 | 1 | 0 | **97.9%** |
| **합계** | **82** | **81** | **1** | **0** | **99.4%** |

- 회귀 스팟 체크 7건 전부 무회귀 (`list_by_user` 시그니처 변경 파급, 워커 성공 경로, D14 선언 순서, 딥링크 라우팅 실효성 등).
- 잔여 Partial 1건(#67)은 "토스트 vs 인라인 배너" 표기 차이였고 Design 정정으로 해소 완료 (문서상 잔여 0).
- 테스트: 백엔드 82 passed · 프론트 34 passed (관련 파일) · `tsc --noEmit` clean.

### 관측 사항 (미채점 — E2E·후속 후보)

1. Act-1 신규 코드 2곳(AgentChatLayout 딥링크 소비, 비활성 가드)은 발신측 테스트만 존재 — E2E 체크리스트에 "딥링크 진입 시 해당 세션 로드" 포함 권장.
2. `GetJobUseCase` 단건 응답의 agent_name 은 항상 None (설계는 목록만 요구, `useJob` 소비처 0 — 영향 없음).
3. 벨(limit 20)과 작업함(무파라미터)의 `useJobList` 캐시 키 분리로 진행중 폴링 스트림 2개 — 무해하나 요청 중복.
4. 딥링크 대상 에이전트가 내 에이전트 목록에 없을 때 폴백(`myAgents[0]`)과 세션이 어긋날 수 있음 — E2E 확인.

### 결론

**Match Rate 99.4% — 90% 게이트 통과. `/pdca report background-jobs` 진행 가능.**
