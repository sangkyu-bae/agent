---
title: DB 큐 + 인프로세스 워커 — 비동기 작업·스케줄 실행
status: draft
source_type: conversation
source_refs:
  - idt/src/application/background_job/worker.py (start/stop/reconcile/_claim_and_spawn/_maybe_tick_schedules)
  - idt/src/infrastructure/background_job/job_repository.py:98-126 (claim_queued — FOR UPDATE SKIP LOCKED)
  - idt/src/config.py:229-233 (background_worker_enabled / poll / concurrency / tick)
  - idt/docs/archive/2026-08/background-jobs/background-jobs.report.md (D1·D2·D7·D8·D10·D13, FR-01~FR-07)
  - 커밋 5d334a3 feat(background-jobs): DB 큐+워커+작업함+알림 벨 (V060)
confidence: 0.85
version: 1
created: 2026-08-14
updated: 2026-08-14
verified_at: 12c69b4
---

# DB 큐 + 인프로세스 워커 — 비동기 작업·스케줄 실행

## 문제

"오래 걸리는 에이전트 실행을 백그라운드로 넘기고, 사용자는 채팅방을 나가도 된다"와
"주기 실행(스케줄)"을 지원해야 하는데, Celery/Redis 브로커·외부 cron을 추가하면
배포 인프라가 늘어난다. 또 `asyncio.create_task`로만 돌리면 **서버 재시작 시 작업이
증발**하고 상태를 조회할 방법이 없다.

## 검증된 사실

### 1. 브로커 없이 MySQL 테이블이 큐다 (V060)

`agent_background_job` 테이블 + FastAPI `lifespan`에서 기동하는 워커 싱글턴.
외부 브로커·cron 프로세스 0개. 등록 API는 **202 + job_id 즉시 반환**하고,
`queued → running → success|failed` 상태 전이만 허용된다(도메인 policy로 강제).

### 2. 이중 선점 방지는 `FOR UPDATE SKIP LOCKED`

```python
# job_repository.py:98-126
select(...).where(status == "queued").order_by(queued_at).limit(limit)
           .with_for_update(skip_locked=True)
# → 같은 트랜잭션에서 status="running" 전환, commit은 호출측(UseCase)이 담당
```

잠긴 행을 건너뛰므로 워커가 여러 개여도 같은 job을 두 번 집지 않는다.
"claim + running 전환"이 한 트랜잭션인 것이 원자성의 핵심.
(Repository 안에서 commit 하지 않는 규칙은 CLAUDE.md §6 그대로.)

### 3. 재시작 복구는 "기동 시 reconcile"로

워커 루프는 시작하자마자 `reconcile()`을 1회 돌려, 이전 프로세스가 남긴
**고아 `running` 행을 `failed`로 정리**한다. 종료 시에도 마킹을 시도하지만
(`_try_mark_shutdown_failed`), 실패해도 다음 기동 reconcile이 이중 방어한다 —
**종료 경로를 신뢰하지 않는 설계**. `queued`는 손대지 않으므로 재시작 후 그대로 실행된다.

### 4. 스케줄러는 워커 루프 안의 "틱"이다 (single-flight)

`poll_interval` 5s마다 job을 집고, `tick_interval` 30s마다 스케줄 트리거를 돈다.
스케줄 틱은 **별도 task + single-flight** — 직전 틱이 안 끝났으면 그냥 skip한다
(`_maybe_tick_schedules`). 스케줄 직렬 실행이 수십 초~분 걸릴 수 있어 틱이
겹치면 중복 실행이 되기 때문.

### 5. 설정 4종 — 기본값이 곧 운영 전제

| 설정 | 기본값 | 의미 |
|------|-------:|------|
| `background_worker_enabled` | `True` | **다른 opt-in 플래그와 달리 기본 켜짐.** 테스트는 False로 끈다 |
| `background_job_poll_interval_sec` | `5.0` | 등록~실행 지연의 하한 |
| `background_job_max_concurrency` | `2` | 초과분은 queued 대기 |
| `background_schedule_tick_interval_sec` | `30.0` | 스케줄 정밀도 |

멀티 인스턴스로 배포하면 인스턴스마다 워커가 뜬다. SKIP LOCKED 덕에 이중 실행은
없지만 **총 동시성은 `max_concurrency × 인스턴스 수**다.

### 6. 결과 저장·알림은 기존 자산 재사용

- 실행은 `RunAgentUseCase` 재사용, 결과는 **세션 메시지로 저장**(job 레코드에
  `session_id`·`run_id` 기록). enqueue 시점에는 메시지를 쓰지 않는다(중복 방지, D10).
- 완료/실패 **양쪽 모두** 웹훅 outbound 발송(`source="job"`). 발송 실패는 job 결과에
  영향 없음.
- 프론트는 헤더 벨 15s 폴링(푸시 아님).

## 다음에 적용하는 법

1. **새 비동기 작업 유형을 추가할 때 브로커를 도입하지 말고 이 큐에 편승한다.**
   상태 전이 policy·claim·reconcile·알림 벨이 이미 있다.
2. **워커에서 도는 코드는 "언제든 프로세스가 죽는다"를 전제로 쓴다** — 중간 상태는
   DB에 남기고, 종료 훅에 복구를 의존하지 않는다.
3. **주기 작업이 필요하면 cron/외부 스케줄러 대신 틱에 붙인다.** 반드시
   single-flight 가드를 함께 붙일 것.
4. **부하 튜닝은 config 4종으로**, 코드 수정 없이. 지연이 문제면 `poll_interval`,
   처리량이 문제면 `max_concurrency`.
5. 마이그레이션 의존: **V060 미적용 상태에서 워커가 뜨면 테이블 부재로 실패**한다
   ([[migration-deploy-deps]] 갱신 필요 — 현재 문서는 V046~V054 범위).

## 관련 문서

- 조감도: `backend/architecture-overview.md`
- 배포 의존성: `ops/migration-deploy-deps.md`
