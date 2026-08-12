# Background Jobs Design Document

> **Summary**: DB 큐(`agent_background_job`, V060) + lifespan 워커 루프 싱글턴으로 ad-hoc 백그라운드 작업을 실행하고, 같은 루프의 스케줄러 틱이 기존 `TriggerDueSchedulesUseCase`를 주기 호출해 외부 cron을 대체한다. 실행 본체는 `RunAgentUseCase.execute` 재사용(세션 생성·메시지 저장 포함), 확인 UX는 작업함 2탭(요청 작업/스케줄 실행) + 헤더 벨 폴링 + 채팅방 복귀 자연 표시
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-11
> **Status**: Draft
> **Plan**: `docs/01-plan/features/background-jobs.plan.md`

---

## 1. 설계 요약

```
[등록 — M1 API]
POST /api/v1/agents/{agent_id}/jobs  (query, session_id?)
  → 같은 세션에 진행중 job 있으면 409 (D5)
  → agent_background_job INSERT (status=queued) → 202 {job_id}
  → 세션에는 아무것도 저장하지 않음 (D10 — user 메시지는 실행 시점 단일 저장)

[실행 — lifespan 워커 루프 싱글턴]
BackgroundJobWorker._loop (poll_interval마다):
  ① reconcile (기동 직후 1회): running 잔존 → failed("서버 재시작으로 중단") (D6)
  ② claim: SELECT ... FOR UPDATE SKIP LOCKED (queued, 오래된 순,
     빈 슬롯 수만큼) → status=running (D2)
  ③ job마다 asyncio task spawn (참조 보유, 동시 상한 max_concurrency) →
     AuthContext 재조립 (D3) → RunAgentUseCase.execute
     → success + session_id·run_id 역기입 / failed + error_message
     → outbound_dispatcher.dispatch(source="job") (D12)
  ④ 스케줄러 틱 (schedule_tick_interval마다, single-flight):
     TriggerDueSchedulesUseCase.execute() spawn — 외부 cron 대체 (D1)

[확인 — M2]
작업함 /jobs (2탭: 요청 작업=job 목록 / 스케줄 실행=내 스케줄 이력) (D9)
헤더 벨: unseen-count 폴링 → 배지 → 드롭다운 → seen 처리 (D11)
채팅방 복귀: job이 저장한 assistant 메시지가 기존 이력 API로 자연 표시,
  진행중이면 배너 + 입력 잠금 (D5)
```

### 코드 확인으로 확정된 사실 (2026-08-11)

| 사실 | 위치 |
|------|------|
| `RunAgentUseCase.execute`는 헤드리스 안전 — session_id 미지정 시 생성, user/assistant 메시지 저장, `RunAgentResponse(answer, session_id, run_id)` 반환. 스케줄 경로가 이미 커넥션 없이 재사용 중 | `run_agent_use_case.py:345-391`, `trigger_due_schedules_use_case.py:132-150` |
| HITL(planner 질문)은 **stateless 에코백** — 질문이 일반 답변으로 반환·저장되고 그래프는 정상 종료. 백그라운드에서 blocking interrupt 없음 | fix-agent-planner-hitl 아카이브 (질문 에코백 패턴) |
| `CancelledError` 시 `fail_run` 기록 후 re-raise — shutdown 취소 경로 안전 | `run_agent_use_case.py:311-318` |
| claim 선점 선례 — `FOR UPDATE SKIP LOCKED` + 같은 트랜잭션에서 상태 갱신 | `schedule_repository.claim_due:130-167` |
| 상태 전이 sink 선례 — on_started/on_finished 자체 짧은 트랜잭션 즉시 커밋 | `infrastructure/agent_schedule/run_sink.py` |
| `TriggerDueSchedulesUseCase`는 싱글턴 + session_factory만 보유(DB-001), `status()` 스냅샷 제공 — 내장 틱이 그대로 호출 가능 | `trigger_due_schedules_use_case.py:34-87` |
| outbound 디스패처는 앱 수명 싱글턴, `dispatch(agent_id, result, source, request_id)` raise 금지(D16), source 문자열 자유 | `main.py:2863-2895`, 스케줄 훅 선례 |
| 헤드리스 AuthContext 재조립 선례 — user_repo.find_by_id → AssembleAuthContextUseCase | `invoke_webhook_agent_use_case.py:144-158` |
| lifespan 패턴 — startup에서 싱글턴 생성, yield, shutdown 정리 | `main.py:4197-4270` |
| DI 배선 지점 — `create_agent_schedule_factories(build_run_agent_uc, outbound_dispatcher)` 동형으로 job 팩토리 신설 | `main.py:2770-2860, 4359, 4825` |
| 라우터 인증 — `Depends(get_auth_context)` → AuthContext(user_id, department_ids) | `agent_builder_router.py:270-287` |
| V038 DDL 스타일 — FK CHARSET/COLLATE 미명시, ENGINE=InnoDB만. V054+ 규칙으로 V060은 전 컬럼 COMMENT 필수 | `db/migration/V038__create_agent_schedule.sql` |
| user_message는 별도 세션 즉시 commit (FK 락 1205 회피) — job 실행도 동일 경로라 자동 준수 | `run_agent_use_case.py:986-1006`, general-chat-attach-lock-1205-fix |
| 프론트 통합 지점 — `TopNav.tsx`(벨), `pages/ChatPage/index.tsx`(전환 액션), `constants/api.ts`(스케줄 runs 엔드포인트 기존재) | idt_front 확인 |

---

## 2. 설계 결정 (Decisions)

| ID | 결정 | 근거 |
|----|------|------|
| **D1** | **워커 루프 = lifespan 싱글턴 1개** — `BackgroundJobWorker`가 poll_interval(기본 5s)마다 job claim·spawn, schedule_tick_interval(기본 30s)마다 스케줄 틱. 스케줄 틱은 **별도 task로 spawn + single-flight 가드**(직전 틱 미완이면 skip) — 스케줄 N건 직렬 실행(수십 초~분)이 job 처리를 막지 않도록. AsyncSession 비보유, session_factory만 (DB-001) | TriggerDueSchedulesUseCase 싱글턴 관례 동형. 외부 cron 정지 = 스케줄 전체 침묵 문제 제거. 기존 trigger 엔드포인트·status()는 수동 백업으로 유지 (claim 선점이라 병행 중복 안전) |
| **D2** | **claim = `FOR UPDATE SKIP LOCKED`** — `status='queued' ORDER BY queued_at LIMIT {빈 슬롯}` 선택 후 같은 트랜잭션에서 `status='running', started_at` 갱신·커밋. 커밋 즉시 가시화 | claim_due 실측 선례 그대로 — 다중 인스턴스에도 이중 클레임 없음. 상태 갱신을 SELECT와 같은 짧은 트랜잭션에 묶어 "선택됐지만 running 표시 전 crash" 창 최소화 |
| **D3** | **실행 시 등록자 AuthContext 재조립** — user_repo.find_by_id(user_id) → AssembleAuthContextUseCase → `execute(auth_ctx=, viewer_user_id=, viewer_department_ids=)`. 사용자 미존재/비활성이면 job failed | webhook D3 동형 — UI 실행과 동작 동등성(RAG auth filter·가시성 검사). 스케줄 경로(viewer_user_id만)보다 강한 보장 |
| **D4** | **HITL 질문 = 작업물, 별도 상태 없음** — stateless HITL은 질문을 일반 답변으로 에코백하므로 job은 success로 종료되고 질문이 세션에 저장된다. 사용자가 복귀해 세션에서 이어서 답변 | 코드 실측: blocking interrupt가 없어 백그라운드에서 멈출 수 없음. needs_input 별도 표시는 YAGNI — 답변 열람 시 자연 인지. Plan 리스크 §5 해소 |
| **D5** | **세션 동시성 = 이중 가드** — ① 백엔드: enqueue 시 같은 session_id에 queued/running job 존재하면 409 ② 프론트: 진행중 job 있는 세션은 입력 비활성 + "백그라운드 작업 진행 중" 배너. 실행 컨텍스트는 **실행 시점 히스토리**(RunAgentUseCase._build_messages 그대로 — 등록~실행 사이 초 단위 지연은 수용) | 같은 세션 동시 기록으로 인한 turn_index 경합·컨텍스트 오염 차단. 등록 시점 스냅샷 재구현은 _build_messages 우회라 회귀 위험 — 기존 경로 무변경이 우선 |
| **D6** | **reconcile = 기동 시 1회, running → failed** — error_message="서버 재시작으로 실행이 중단되었습니다. 다시 요청해 주세요." queued는 무처리(루프가 자연 소비) | LLM 실행 비멱등(중복 답변·중복 비용) — 자동 재큐보다 명시 실패 + 사용자 재요청이 안전. Plan 기본안 채택 |
| **D7** | **shutdown = 루프 취소 + 실행 중 job failed 마킹 시도** — worker.stop()이 루프·활성 task cancel, 각 task의 CancelledError 핸들러가 failed("서버 종료로 중단") 기록 시도(실패해도 다음 기동 reconcile이 이중 방어). RunAgentUseCase는 CancelledError에서 fail_run 후 re-raise하므로 관측성도 정리됨 | graceful 대기(완료까지 수십 초 점유)는 배포 중단 시간을 늘림 — 취소+명시 실패가 단순하고 결정적 |
| **D8** | **동시 상한 = config `background_job_max_concurrency` 기본 2** — 루프가 활성 task 수를 세어 빈 슬롯만큼만 claim. task 참조는 worker가 보유(GC 교훈) | FR-07. LLM 대기는 async라 이벤트 루프 비점유 — 상한은 LLM 비용·API 응답성 보호용. 실측 후 조정 |
| **D9** | **작업함 = 2탭 (요청 작업 / 스케줄 실행)** — 스케줄 실행 탭은 신규 read-only API `GET /api/v1/schedule-runs`(agent_schedule_run ⋈ agent_schedule.user_id = 나) 로 내 스케줄 이력 전체 조회. **벨 배지는 job만 집계** (스케줄은 반복 실행이라 노이즈) | 사용자 원 요청("스케줄 돌린 것도 진행중/완료 확인")을 하나의 확인 UX로 충족하되, 테이블 통합 이관(스키마 변경)은 회피 — additive 조회 API 1개만 |
| **D10** | **enqueue는 세션에 아무것도 저장하지 않는다** — user 메시지는 실행 시점에 RunAgentUseCase가 단일 저장(중복 방지). 접수 직후 표시는 프론트 로컬(배너/placeholder)이 담당 | _save_user_message가 실행 경로에 내장 — 등록 시점에도 저장하면 이중 기록. 등록~실행 지연은 poll_interval(5s) 수준이라 가시성 공백 미미 |
| **D11** | **벨 = 폴링** — `GET /api/v1/jobs/unseen-count`(success/failed & seen_at IS NULL), 단건 `POST /jobs/{id}/seen` + 일괄 `POST /jobs/seen-all`. 프론트 refetchInterval 15s + 창 포커스 시 refetch | 사용자 확정(폴링 1차). 전용 인덱스(user_id, seen_at, status)로 경량. WS 푸시는 후속 |
| **D12** | **outbound 발송 = job task 안에서 인라인 await, source="job"** — dispatch raise 금지 계약이지만 스케줄 훅과 동일하게 try/except 이중 방어(발송 실패는 job 상태 불영향) | 이미 백그라운드 문맥이라 비차단 spawn 불필요 (스케줄 D12 선례 — 지연 무해) |
| **D13** | **테스트·운영 스위치 `background_worker_enabled` (기본 true)** — false면 lifespan이 워커를 기동하지 않음. 기존 pytest 스위트는 워커 미기동 상태로 무회귀 | optional 의존성 무회귀 패턴 (agent-memory 선례). Windows 이벤트 루프 teardown flaky 이력상 테스트에서 루프 미기동이 안전 |
| **D14** | **라우터 선언 순서: 리터럴 경로 우선** — `/jobs/unseen-count`, `/jobs/seen-all`을 `/jobs/{job_id}`보다 먼저 선언 | wiki tree 라우트 선언 순서 계약 교훈 (wiki-user-facing) |

---

## 3. DB 설계 — V060

```sql
-- background-jobs: ad-hoc 백그라운드 작업 큐 + 이력
-- Design: docs/02-design/features/background-jobs.design.md §3
-- ⚠️ FK 콜레이션 주의(errno 3780, V037/V038 선례): 테이블 레벨 CHARSET/COLLATE
-- 미명시로 DB 기본값 상속 → agent_definition FK 컬럼 정합. ENGINE=InnoDB만 명시.

CREATE TABLE agent_background_job (
  id            VARCHAR(36)  PRIMARY KEY                COMMENT '작업 ID (uuid4)',
  user_id       VARCHAR(100) NOT NULL                   COMMENT '등록 사용자 ID (실행 신원·조회 인가 기준)',
  agent_id      VARCHAR(36)  NOT NULL                   COMMENT '실행 대상 에이전트 ID',
  source        VARCHAR(10)  NOT NULL DEFAULT 'chat'    COMMENT '등록 경로 (chat|api)',
  query         TEXT         NOT NULL                   COMMENT '실행할 사용자 질문',
  session_id    VARCHAR(36)  NULL                       COMMENT '대화 세션 ID (미지정 시 실행 시 생성 후 역기입)',
  run_id        VARCHAR(36)  NULL                       COMMENT 'ai_run 연결 (AGENT-OBS-001)',
  status        VARCHAR(10)  NOT NULL DEFAULT 'queued'  COMMENT '상태 (queued|running|success|failed)',
  error_message TEXT         NULL                       COMMENT '실패 사유 (2000자 절단)',
  seen_at       DATETIME     NULL                       COMMENT '사용자 결과 확인 시각 (NULL=미확인, 벨 배지 집계 기준)',
  queued_at     DATETIME     NOT NULL                   COMMENT '등록 시각 (UTC, claim 순서 기준)',
  started_at    DATETIME     NULL                       COMMENT '실행 시작 시각 (UTC)',
  finished_at   DATETIME     NULL                       COMMENT '실행 종료 시각 (UTC)',
  request_id    VARCHAR(64)  NOT NULL                   COMMENT '등록 요청 추적 ID',
  created_at    DATETIME     NOT NULL                   COMMENT '생성 시각 (UTC)',
  updated_at    DATETIME     NOT NULL                   COMMENT '수정 시각 (UTC)',
  CONSTRAINT fk_bg_job_agent
    FOREIGN KEY (agent_id) REFERENCES agent_definition(id) ON DELETE CASCADE,
  INDEX idx_bg_job_claim (status, queued_at),
  INDEX idx_bg_job_user (user_id, queued_at),
  INDEX idx_bg_job_unseen (user_id, seen_at, status)
) ENGINE=InnoDB COMMENT='ad-hoc 백그라운드 작업 큐·이력 (background-jobs)';
```

- SQLAlchemy `AgentBackgroundJobModel`에 동일 `comment=` 반영 (`tests/db/test_migration_ddl_comments.py` 대상).
- user_id는 FK 미설정 (agent_schedule.user_id 선례와 일관).
- 세션 중복 가드(D5)는 UNIQUE 제약이 아닌 enqueue 시 조회 검증 — session_id NULL 다건 허용 필요.

---

## 4. 백엔드 상세 설계 — M1

### 4-1. domain/background_job/

```
entity.py        BackgroundJob dataclass (V060 컬럼 대응) + JobStatus = Literal[...]
policies.py      JobTransitionPolicy.can_transition(cur, new):
                   queued→running, queued→failed, running→success, running→failed 만 허용
                 JobQueuePolicy: error_message 2000자 절단, 동시 상한 검증(>=1)
interfaces.py    BackgroundJobRepositoryInterface (ABC — 프로젝트 포트 관례):
                   enqueue, claim_queued(limit), mark_running… (아래 repo 시그니처)
```

순수 파이썬만 — 외부 import 금지 (verify-architecture).

### 4-2. infrastructure/background_job/

```
models.py            AgentBackgroundJobModel (comment= 전 컬럼)
job_repository.py    BackgroundJobRepository(session, logger) — commit 금지 (DB-001)
  enqueue(job)                              INSERT
  find_active_by_session(session_id)        queued|running 존재 확인 (D5)
  claim_queued(limit)                       SELECT ... WHERE status='queued'
                                            ORDER BY queued_at LIMIT :limit
                                            FOR UPDATE SKIP LOCKED
                                            → status='running', started_at 갱신 (D2)
  finish(job_id, status, *, session_id, run_id, error_message)
                                            종료 기록 + finished_at (running→만 허용)
  reconcile_orphan_running(error_message)   UPDATE status='failed' WHERE status='running' (D6)
  list_by_user(user_id, status?, limit, offset)  agent_definition LEFT JOIN →
                                            (job, agent_name) 쌍 (작업함 표시용)
  find_by_id(job_id)
  count_unseen(user_id) / mark_seen(job_id, user_id) / mark_all_seen(user_id)
```

각 쓰기 메서드는 워커/라우터가 `session_factory() + begin()` 블록으로 감싼다
(run_sink 동형 — 실행 수십 초와 상태 기록 트랜잭션 분리).

### 4-3. application/background_job/

**EnqueueJobUseCase** (요청 스코프, `Depends(get_session)`):
1. agent 존재·실행 가시성 확인 (`VisibilityPolicy.can_access` — run_agent 동형)
2. session_id 지정 시 `find_active_by_session` → 있으면 `JobConflictError` (409)
3. BackgroundJob(queued) 저장 → `EnqueueJobResponse(job_id, status)` (202)

**ListJobsUseCase / GetJobUseCase / MarkSeenUseCase(단건·일괄) / CountUnseenUseCase**:
user_id 인가 — 본인 소유만 (타인 job은 404 통일, D8 웹훅 사유 비구분 선례).

**ListMyScheduleRunsUseCase** (D9): agent_schedule_run ⋈ agent_schedule
(+ agent_definition LEFT JOIN → agent_name) WHERE agent_schedule.user_id = 나,
started_at DESC, 페이징. 조회 전용 — 기존 agent_schedule 모듈 무변경
(schedule_run_repository에 조회 메서드 1개 추가).

**BackgroundJobWorker** (lifespan 싱글턴 — session_factory·빌더 주입, 세션 비보유):

```python
class BackgroundJobWorker:
    # AuthContext 재조립은 단일 콜러블(assemble_auth_context)로 주입 —
    # user_repo/assemble_uc 빌더 2종보다 워커-DI 결합이 얇다. config 는 개별 kwargs.
    def __init__(self, *, session_factory, job_repo_builder, run_agent_uc_builder,
                 assemble_auth_context, logger, schedule_trigger_uc=None,
                 outbound_dispatcher=None, poll_interval_sec=5.0,
                 schedule_tick_interval_sec=30.0, max_concurrency=2,
                 enabled=True, now_fn=...): ...

    def start(self):   # lifespan startup — enabled=False면 no-op (D13)
        self._task = asyncio.create_task(self._run())   # 참조 보유 (GC 교훈)

    async def stop(self):  # lifespan shutdown (D7)
        루프 task cancel → 활성 job task 전부 cancel →
        각 task의 CancelledError 핸들러가 failed("서버 종료로 중단") 기록 시도

    async def _run(self):
        await self._reconcile()          # D6 — 기동 1회
        while True:
            try:
                self._maybe_tick_schedules()   # D1 — single-flight spawn
                await self._claim_and_spawn()  # D2·D8
            except Exception as e:
                self._logger.error("worker tick failed", exception=e)  # 루프 생존
            await asyncio.sleep(self._config.poll_interval)

    async def _execute_job(self, job):   # spawn된 task 본체
        owner, ctx = await self._assemble_ctx(job.user_id)   # D3 — 실패 시 failed
        async with self._session_factory() as s, s.begin():
            uc = self._run_agent_uc_builder(s)
            resp = await uc.execute(job.agent_id,
                RunAgentRequest(query=job.query, user_id=job.user_id,
                                session_id=job.session_id),
                request_id, auth_ctx=ctx, viewer_user_id=job.user_id,
                viewer_department_ids=list(ctx.department_ids))
        await self._finish(job.id, "success", session_id=resp.session_id,
                           run_id=resp.run_id)
        await self._dispatch_outbound(job.agent_id, resp)    # D12 — 이중 방어
```

- `status()` 스냅샷(last_tick_at, active_count, last_error) — 로그·후속 admin 노출용.
- 예외 처리: `_execute_job`의 `except CancelledError` → failed 마킹 시도 후 re-raise,
  `except Exception` → failed + error_message[:2000], 스택 트레이스 로깅.
- 실패 시에도 outbound 발송 (Plan FR-06 "완료/실패 시") — run-동형 페이로드에
  `answer=None` 이 실패 신호. shutdown(Cancelled) 경로는 미발송.

### 4-4. config (src/config.py 추가)

| 키 | 기본값 | 용도 |
|----|--------|------|
| `background_worker_enabled` | `True` | 워커 기동 스위치 (D13 — 테스트 false) |
| `background_job_poll_interval_sec` | `5` | job claim 폴링 주기 |
| `background_job_max_concurrency` | `2` | 동시 실행 상한 (D8) |
| `background_schedule_tick_interval_sec` | `30` | 스케줄러 틱 주기 (D1) |

### 4-5. API — background_job_router.py

| Method | Path | 응답 | 비고 |
|--------|------|------|------|
| POST | `/api/v1/agents/{agent_id}/jobs` | 202 `{job_id, status}` | 409=세션 중복(D5), 404=에이전트/권한 |
| GET | `/api/v1/jobs` | 목록 (status 필터·limit/offset) | 본인만 |
| GET | `/api/v1/jobs/unseen-count` | `{count}` | **`/jobs/{job_id}`보다 먼저 선언** (D14) |
| POST | `/api/v1/jobs/seen-all` | 200 `{updated}` | D14 동일 — 처리 건수 반환 |
| GET | `/api/v1/jobs/{job_id}` | 단건 | 타인=404 |
| POST | `/api/v1/jobs/{job_id}/seen` | 204 | |
| GET | `/api/v1/schedule-runs` | 내 스케줄 실행 이력 (페이징) | D9, read-only |

등록(POST /agents/{agent_id}/jobs)만 `Depends(get_auth_context)`(가시성 검사에
department_ids 필요), 조회·확인 6종은 `Depends(get_current_user)`(본인 소유
검증만 필요). 목록 응답(`JobResponse`/`MyScheduleRunResponse`)에는 작업함
표시용 `agent_name` 이 additive 로 포함된다. DI는 `create_background_job_factories(
build_run_agent_uc, outbound_dispatcher, schedule_trigger_uc)` — 요청 스코프
팩토리 + 워커 싱글턴 반환, lifespan에서 `worker.start()/stop()` 배선.

---

## 5. 프론트 설계 — M2

### 5-1. 계약 동기화 (S10)

- `constants/api.ts`: `AGENT_JOBS(agentId)`, `JOBS`, `JOBS_UNSEEN_COUNT`,
  `JOBS_SEEN_ALL`, `JOB_DETAIL(jobId)`, `JOB_SEEN(jobId)`, `MY_SCHEDULE_RUNS`
- `types/backgroundJob.ts`: `BackgroundJob`, `JobStatus`, `EnqueueJobResponse`,
  `MyScheduleRun` — 백엔드 스키마 1:1
- `services/backgroundJobService.ts` + `hooks/useBackgroundJobs.ts`:
  `useJobList(status?)`, `useJob(jobId)`, `useUnseenCount()`(refetchInterval 15s,
  refetchOnWindowFocus), `useEnqueueJob()`, `useMarkSeen()/useMarkAllSeen()`,
  `useMyScheduleRuns()`
- `lib/queryKeys.ts`에 `backgroundJobs` 네임스페이스 추가 — **기존 키와 충돌 검사**
  (eval-hub queryKeys 충돌 회귀 교훈)

### 5-2. 작업함 페이지 (S7, `/jobs`)

- `pages/JobsPage/index.tsx` — 탭 2개 (D9):
  - **요청 작업**: 상태 배지(진행중=스피너/완료/실패), 에이전트명, 질문 프리뷰,
    요청 시각, 소요 시간(finished-started), 실패 시 error_message,
    완료 행 클릭 → 해당 세션으로 이동(`/chatpage?agentId=&sessionId=` — AgentChatLayout 이 쿼리 소비) + seen 처리
  - **스케줄 실행**: 스케줄명·에이전트·status·scheduled_for·소요·세션 이동
- 진행중 항목 있으면 목록 폴링(useJobList refetchInterval), 없으면 폴링 중단
- 라우팅·메뉴: TopNav "에이전트" 드롭다운에 "작업함" 항목 추가

### 5-3. 헤더 벨 (S8)

- `components/layout/NotificationBell.tsx` (+test) — TopNav 우측(사용자 메뉴 옆)
- unseen count > 0 → 배지. 클릭 → 드롭다운: 최근 완료/실패 job 5건
  (useJobList 재사용) + "모두 확인" + "작업함 가기"
- 항목 클릭 → mark seen + 세션 이동. 드롭다운 외부 클릭 닫기(TopNav 기존 패턴)

### 5-4. 채팅 연동 (S9)

- `pages/ChatPage/index.tsx` 입력 영역에 "백그라운드로 실행" 액션(보조 버튼) —
  현재 입력 query + 현재 session_id로 `useEnqueueJob` → 성공 시 로컬 접수 배너
  ("백그라운드에서 실행 중 — 작업함에서 확인") 표시, 입력창 비움
- 현재 세션에 진행중 job 존재(`useJobList` 필터) → 입력 비활성 + 배너 (D5 프론트 가드),
  완료 감지 시(폴링) 대화 이력 쿼리 invalidate → 답변 자연 표시 (FR-13)
- 409 응답 → 지정 문구 인라인 배너(role=status) — bgNotice 가 진행중 안내보다 우선 표시

---

## 6. 테스트 전략 (TDD — Red 먼저)

### M1 (pytest)

| 파일 | 검증 |
|------|------|
| `tests/domain/background_job/test_policies.py` | 전이 허용/거부 매트릭스, error 절단 |
| `tests/infrastructure/background_job/test_job_repository.py` | enqueue→claim(limit·순서)→finish 왕복, claim 경쟁(동시 2회 호출 시 중복 0 — sqlite는 SKIP LOCKED 미지원이므로 순차 검증 + MySQL 구문은 E2E 이월), reconcile, unseen count/seen |
| `tests/application/background_job/test_enqueue_use_case.py` | 202 접수, 세션 중복 409(D5), 미존재 에이전트 404, 가시성 거부 |
| `tests/application/background_job/test_worker.py` | 1틱: claim→실행(mock run_uc)→success·session_id 역기입→outbound 호출(source="job"), 실행 예외→failed+루프 생존, 동시 상한 준수(D8), 스케줄 틱 위임+single-flight(D1), reconcile(D6), stop 시 failed 마킹(D7), enabled=False no-op(D13) |
| `tests/api/test_background_job_router.py` | 인증 필수, 본인 외 404, unseen-count 라우팅(D14 — `/jobs/unseen-count`가 `{job_id}`에 안 삼켜짐), schedule-runs 본인 필터 |
| `tests/db/test_migration_ddl_comments.py` | V060 자동 검사 (기존 테스트) |

### M2 (vitest — `--pool=threads`, MSW per-file listen)

| 파일 | 검증 |
|------|------|
| `JobsPage/index.test.tsx` | 탭 전환, 상태 배지, 실패 메시지, 세션 이동+seen |
| `NotificationBell.test.tsx` | count 배지, 드롭다운, 모두 확인 후 배지 소거 |
| `ChatPage` 통합 (기존 파일 확장 or 신규) | 백그라운드 액션 → 접수 배너, 진행중 세션 입력 잠금, 409 지정 문구 배너 |

### E2E 수동 (기동 환경 필요 — 이월 체크리스트)

- 서버 기동 → job 등록 → 브라우저 종료 → 재접속 → 벨 배지 → 작업함 → 세션에서 답변 확인
- 외부 cron 없이 1분 스케줄 자동 실행 확인, 서버 재시작 시 running job failed 처리 확인

---

## 7. 구현 순서 (Do)

1. **V060 마이그레이션 + models.py** (DDL comment 테스트 통과 확인)
2. domain: entity·policies·interfaces (+ 단위 테스트 Red→Green)
3. infrastructure: job_repository (+ 테스트)
4. application: Enqueue/List/Get/Seen/ScheduleRuns use case (+ 테스트)
5. application: BackgroundJobWorker (+ 테스트 — mock 빌더로 틱 단위 검증)
6. main.py: config 4종 + `create_background_job_factories` + lifespan start/stop + 라우터 include (D14 순서)
7. schedule_run_repository에 `list_by_user` 추가 (+ 테스트)
8. M2: 계약 동기화 → JobsPage → NotificationBell → ChatPage 연동 (각각 테스트 선행)
9. 회귀: 기존 pytest 격리 실행 (사전 실패 목록 제외), vitest 전체

---

## 8. 관측·보안

- 모든 로그에 request_id + job_id 태깅, 실패는 스택 트레이스 필수 (LOG-001)
- 워커 루프 예외는 루프를 죽이지 않고 error 로깅 후 다음 틱 (D1) — `status()` 스냅샷으로 생존 관측
- query 원문은 로그에 프리뷰(256자)만 — 전문 미로깅
- 인가: 모든 job API 본인 소유 검증, 타인 접근 404 통일 (존재 여부 비노출)
- LangSmith: RunAgentUseCase 기존 추적 그대로 (agent-run 프로젝트) — job 전용 분리는 후속
