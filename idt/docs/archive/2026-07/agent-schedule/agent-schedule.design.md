# Agent Schedule Design Document

> **Summary**: 에이전트 스케줄 기능 — 독립 도메인(`agent_schedule`) CRUD + 외부 트리거 실행 엔진. once/daily/weekly/cron 반복, 에이전트당 복수 스케줄, 포크 시 미복사 구조 보장.
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-02
> **Status**: Draft
> **Planning Doc**: [agent-schedule.plan.md](../../01-plan/features/agent-schedule.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. **독립 도메인**: 스케줄은 `agent_definition`의 컬럼이 아닌 별도 테이블/도메인 — 포크(수동 `ForkAgentUseCase` / 자동 `AutoForkService`)가 필드 화이트리스트 복사 방식이므로 구조적으로 미복사 보장.
2. **외부 트리거**: 앱은 스케줄 판정·실행만 담당. 주기 호출(매 분)은 외부 스케줄러(OS cron / Windows 작업 스케줄러 / k8s CronJob)가 담당. 인프로세스 백그라운드 루프 없음.
3. **결과 처리 유연성**: `ScheduleRunSinkInterface` 포트로 결과 기록을 추상화 — 현재는 이력 테이블 + 새 대화 세션, 추후 알림/웹훅 sink additive 추가 가능.
4. **기존 실행 경로 재사용**: 스케줄 실행은 `RunAgentUseCase.execute()`를 그대로 호출 — ai_run 관측성(AGENT-OBS-001), 세션 자동 생성, 스킬 주입 등 전부 무료로 획득.
5. **지침 = 실제 사용자 질문 (R9)**: 스케줄에 저장한 지침(instruction)이 실행 시점에 시점 변수(`{today}`/`{now}`/`{weekday}`) 치환을 거쳐 `RunAgentRequest.query`로 전송된다. `RunAgentUseCase`가 query를 새 세션의 user 메시지로 저장하므로, 세션을 열면 **사용자가 직접 질문한 것과 동일하게** 보인다.

### 1.2 Design Principles

- Thin DDD 레이어 준수 (domain은 외부 API·DB·LangChain 금지 — croniter는 순수 계산 라이브러리로 domain 허용, §3.2 근거)
- DB-001: Repository는 commit/rollback 금지, CRUD는 요청당 단일 세션
- StructuredLogger 로깅 (LOG-001), print() 금지
- TDD: 모든 모듈 테스트 선행

### 1.3 확정된 설계 결정 (Plan 미결사항)

| 항목 | 결정 | 근거 |
|------|------|------|
| croniter 사용 레이어 | **domain policy에서 직접 사용** | 순수 시간 계산(외부 I/O 없음). CLAUDE.md domain 금지 대상(외부 API·DB·LangChain) 아님. 의존성 `croniter>=2.0`을 `pyproject.toml`에 추가 |
| cron 최소 간격 | **10분** (`MIN_CRON_INTERVAL_MINUTES = 10`) | 과밀 cron으로 인한 LLM 비용 폭증 방지. 연속 두 발화 시각 차로 검증 |
| 타임존 계산 | stdlib `zoneinfo` (Python 3.11) | 추가 의존성 불필요 |
| 트리거 동시성 | `SELECT ... FOR UPDATE SKIP LOCKED` + 짧은 claim 트랜잭션 | MySQL 8 지원. 겹친 트리거 호출이 서로 블로킹 없이 잔여 due만 클레임 |
| 트리거 세션 전략 | `TriggerDueSchedulesUseCase`에 **session_factory 주입** | 단일 요청-단일 세션 규칙의 예외 선례: `RunAgentUseCase(session_factory=get_session_factory())` (`src/api/main.py:2148`, FK 락 회피 목적). N개 독립 실행을 한 트랜잭션에 묶으면 락 장기 점유 → 회차별 짧은 트랜잭션 |
| 트리거 관측 | `GET /internal/schedules/trigger/status` — 마지막 트리거 시각/결과 (in-memory) | 외부 cron 정지 감지용 |
| 지침 변수 치환 (R9) | `{today}`(YYYY-MM-DD)/`{now}`(HH:MM)/`{weekday}`(월~일) 3종, 스케줄 tz 기준. 미지원 플레이스홀더는 원문 유지 | 정규식/템플릿 엔진 없이 str.replace 수준의 순수 계산 — domain policy 배치. "매일 오늘 날짜 기준 요약" 류 지침이 실제 질문으로 성립 |

---

## 2. Architecture

### 2.1 Component Diagram

```
[외부 스케줄러 (OS cron 등)]                [사용자 (후속: 프론트 UI)]
        │ POST /internal/schedules/trigger        │ CRUD REST
        │   (X-Scheduler-Token)                   │ (JWT get_current_user)
        ▼                                         ▼
┌─ api/routes/agent_schedule_router.py ──────────────────────────┐
│  trigger 엔드포인트            CRUD 엔드포인트 8종               │
└───────┬────────────────────────────┬───────────────────────────┘
        ▼                            ▼
┌─ application/agent_schedule/ ───────────────────────────────────┐
│  TriggerDueSchedulesUseCase    Create/List/Get/Update/Delete/   │
│   ├ claim (short tx)           Toggle/ListRuns UseCase          │
│   ├ RunAgentUseCase.execute()  (요청당 단일 세션, DB-001)        │
│   └ ScheduleRunSink 기록                                        │
└───────┬─────────────────────────────┬──────────────────────────┘
        ▼                             ▼
┌─ domain/agent_schedule/ ────────────────────────────────────────┐
│  AgentSchedule(Entity)  ScheduleSpec(VO)  SchedulePolicy        │
│  ScheduleRepositoryInterface  ScheduleRunSinkInterface           │
└───────┬─────────────────────────────────────────────────────────┘
        ▼
┌─ infrastructure/agent_schedule/ ────────────────────────────────┐
│  models.py (ORM 2종)   schedule_repository.py                   │
│  schedule_run_repository.py   run_sink.py (DbScheduleRunSink)   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 실행 시퀀스 (trigger)

```
외부 cron ─▶ POST /internal/schedules/trigger
  1. 토큰 검증 (settings.scheduler_trigger_token) — 불일치 401, 미설정 503
  2. TriggerDueSchedulesUseCase.execute(request_id)
     a. [tx1: claim] async with session_factory() as s, s.begin():
          SELECT * FROM agent_schedule
           WHERE enabled=1 AND next_run_at <= UTC_NOW
           FOR UPDATE SKIP LOCKED
          각 행: scheduled_for = next_run_at 보관
                 next_run_at = SchedulePolicy.compute_next_run(spec, tz, after=now)
                 (once → next_run_at=None, enabled=False)
          UPDATE 반영 → commit  ← 이 시점부터 다른 트리거는 이 회차를 못 봄
     b. 클레임된 스케줄 순차 처리 (for each):
          [tx2] sink.on_started(...) → agent_schedule_run INSERT (status='running')
          rendered = SchedulePolicy.render_instruction(sch.instruction, sch.timezone, now)
              # R9: {today}/{now}/{weekday} 치환 → 실제 사용자 질문 텍스트
          RunAgentUseCase.execute(RunAgentRequest(
              query=rendered, user_id=sch.user_id, session_id=None))
              # 새 세션 자동 생성 + rendered가 user 메시지로 저장 + ai_run 기록
          [tx3] sink.on_finished(run_record_id, 'success'|'failed',
                                 session_id, run_id, error)
          last_run_at 갱신 — 성공/실패 무관 '마지막 실행 시도' 시각 기록 (analysis A안)
     c. 응답 {claimed, success, failed, request_id}
  3. 개별 실행 실패는 이력 'failed'로 기록하고 다음 스케줄 계속 (전체 중단 금지)
```

**misfire**: 서버 다운으로 `next_run_at`이 과거로 밀려도 claim은 1회만 발생하고, 재계산은 `after=현재시각` 기준이므로 밀린 회차는 자동 소멸(백필 없음).

---

## 3. Domain Layer — `src/domain/agent_schedule/`

### 3.1 `value_objects.py`

```python
ScheduleType = Literal["once", "daily", "weekly", "cron"]

@dataclass(frozen=True)
class ScheduleSpec:
    schedule_type: ScheduleType
    run_date: date | None = None          # once 전용
    time_of_day: time | None = None       # once/daily/weekly 전용
    days_of_week: tuple[int, ...] | None = None  # weekly 전용, 0=월..6=일
    cron_expr: str | None = None          # cron 전용

    def __post_init__(self):  # 유형별 필수/금지 필드 검증 → ValueError
        # once: run_date+time_of_day 필수, 나머지 None
        # daily: time_of_day 필수
        # weekly: time_of_day+days_of_week(1..7개, 0..6 중복불가) 필수
        # cron: cron_expr 필수 (형식 검증은 SchedulePolicy)
```

### 3.2 `policies.py` — `SchedulePolicy`

```python
class SchedulePolicy:
    MAX_SCHEDULES_PER_AGENT = 10
    MIN_CRON_INTERVAL_MINUTES = 10
    MAX_INSTRUCTION_LENGTH = 1900    # 렌더링 팽창 여유 포함 RunAgentRequest.query(2000) 이하 보장
    RENDERED_QUERY_MAX_LENGTH = 2000 # 렌더링 결과 절단 상한 (RunAgentRequest.query 제약)
    DEFAULT_TIMEZONE = "Asia/Seoul"
    PLACEHOLDERS = ("{today}", "{now}", "{weekday}")   # R9

    @staticmethod
    def validate_spec(spec, tz, now_utc) -> None
        # cron: croniter.is_valid() + 연속 발화 간격 >= MIN_CRON_INTERVAL 검증
        # once: run_date+time_of_day(tz 기준)가 now 이후인지 검증
        # timezone: ZoneInfo(tz) 유효성

    @staticmethod
    def compute_next_run(spec, tz, after_utc) -> datetime | None
        # tz-aware 계산 후 UTC naive로 반환 (DB DATETIME 저장 규격)
        # once  : run_date+time_of_day → after 이후면 그 시각, 지났으면 None
        # daily : after(tz) 기준 오늘 time_of_day, 지났으면 내일
        # weekly: days_of_week 중 after 이후 가장 가까운 요일+time_of_day
        # cron  : croniter(cron_expr, after_tz).get_next() → UTC 변환

    @staticmethod
    def render_instruction(instruction, tz, now_utc) -> str    # R9
        # 스케줄 tz 기준 현재 시각으로 {today}→"2026-07-02", {now}→"09:00",
        # {weekday}→"수" 치환. 미지원 플레이스홀더({foo} 등)는 원문 유지.
        # 렌더링 결과가 2000자 초과 시 절단 (RunAgentRequest 제약)

    @staticmethod
    def validate_instruction(instruction) -> None              # 빈값/1900자 초과 → ValueError

    @staticmethod
    def can_modify(schedule_user_id, viewer_user_id) -> bool   # 소유자만
    @staticmethod
    def validate_count(existing_count) -> None                 # 상한 초과 → ValueError
```

- croniter는 순수 계산(외부 I/O 없음)이므로 domain 사용 허용. `pyproject.toml` dependencies에 `"croniter>=2.0"` 추가.
- **시각 규격**: 모든 저장 datetime은 **UTC naive** (기존 `AgentDefinitionModel.created_at` 등과 동일 규격). tz는 계산 시에만 사용.

### 3.3 `entity.py`

```python
@dataclass
class AgentSchedule:
    id: str                    # uuid4
    agent_id: str
    user_id: str               # 생성자 = 실행 주체
    name: str                  # 1..200자
    spec: ScheduleSpec
    instruction: str           # 지침, 1..1900자 (R9: 실행 시 렌더링 → user 질문)
    enabled: bool
    timezone: str              # IANA
    next_run_at: datetime | None   # UTC naive
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
```

### 3.4 `interfaces.py`

```python
class ScheduleRepositoryInterface(ABC):
    async def save(self, schedule, request_id) -> None
    async def find_by_id(self, schedule_id, request_id) -> AgentSchedule | None
    async def list_by_agent(self, agent_id, request_id) -> list[AgentSchedule]
    async def count_by_agent(self, agent_id, request_id) -> int
    async def update(self, schedule, request_id) -> None
    async def delete(self, schedule_id, request_id) -> None
    async def claim_due(self, now_utc, request_id) -> list[ClaimedSchedule]
        # FOR UPDATE SKIP LOCKED + next_run_at 재계산 UPDATE까지 수행
        # ClaimedSchedule = (schedule, scheduled_for)
    async def touch_last_run(self, schedule_id, ran_at, request_id) -> None

class ScheduleRunSinkInterface(ABC):
    async def on_started(self, schedule, scheduled_for, request_id) -> str   # run_record_id
    async def on_finished(self, run_record_id, status, request_id, *,
                          session_id=None, run_id=None, error_message=None) -> None

class ScheduleRunRepositoryInterface(ABC):
    async def save(self, run, request_id) -> None
    async def update(self, run, request_id) -> None
    async def list_by_schedule(self, schedule_id, limit, offset, request_id) -> list[ScheduleRun]
```

`ScheduleRun` entity: `{id, schedule_id, agent_id, status, scheduled_for, started_at, finished_at, session_id, run_id, error_message, request_id}` — status: `running|success|failed`.

---

## 4. Infrastructure Layer — `src/infrastructure/agent_schedule/`

### 4.1 `models.py` (ORM)

`AgentScheduleModel`(`agent_schedule`), `AgentScheduleRunModel`(`agent_schedule_run`) — §7 DDL과 1:1. `days_of_week`는 JSON 컬럼(list[int]).

### 4.2 `schedule_repository.py`

- 생성자 `(session: AsyncSession, logger: LoggerInterface)` — 기존 repo 컨벤션.
- commit/rollback 금지 (DB-001). `claim_due`도 execute만 수행 — 트랜잭션 경계는 호출측(UseCase의 `async with factory() as s, s.begin()`)이 소유.
- `claim_due` 구현:
  ```python
  rows = (await session.execute(
      select(AgentScheduleModel)
      .where(AgentScheduleModel.enabled.is_(True),
             AgentScheduleModel.next_run_at <= now_utc)
      .with_for_update(skip_locked=True)
  )).scalars().all()
  for m in rows:
      scheduled_for = m.next_run_at
      nxt = SchedulePolicy.compute_next_run(spec_of(m), m.timezone, after_utc=now_utc)
      m.next_run_at = nxt
      if nxt is None:            # once 소진
          m.enabled = False
  await session.flush()
  ```

### 4.3 `run_sink.py` — `DbScheduleRunSink`

- 생성자 `(session_factory, logger)`. `on_started`/`on_finished` 각각 **자체 짧은 트랜잭션**(`async with factory() as s, s.begin()`)으로 즉시 커밋 — 에이전트 실행(수십 초)과 이력 기록의 트랜잭션 분리. 선례: `RunAgentUseCase.session_factory`(main.py:2148).
- `on_started` → `agent_schedule_run` INSERT(status='running'), `on_finished` → UPDATE(status/finished_at/session_id/run_id/error_message).

---

## 5. Application Layer — `src/application/agent_schedule/`

### 5.1 CRUD UseCase 6종 (요청당 단일 세션, DB-001 표준 패턴)

| UseCase | 핵심 로직 |
|---------|----------|
| `CreateScheduleUseCase` | agent 존재+소유자 확인(`AgentDefinitionRepository.find_by_id` → `user_id == viewer`) → `validate_count` → `validate_spec` → `compute_next_run`으로 초기 `next_run_at` → save |
| `ListSchedulesUseCase` | 소유자 확인 → `list_by_agent` |
| `GetScheduleUseCase` | 조회 → `can_modify` 검사(불일치 PermissionError) → agent_id 경로 일치 검사 |
| `UpdateScheduleUseCase` | 조회+권한 → spec/instruction/name/timezone 갱신 → **spec 또는 tz 변경 시 next_run_at 재계산** → update |
| `DeleteScheduleUseCase` | 조회+권한 → delete |
| `ToggleScheduleUseCase` | 조회+권한 → enabled 변경. **off→on 시 next_run_at = compute_next_run(after=now)** (과거 시각으로 즉시 폭발 방지), on→off 시 next_run_at 유지 |
| `ListScheduleRunsUseCase` | 스케줄 조회+권한 → `list_by_schedule` (limit≤100, offset) |

에러 규약(기존 라우터 컨벤션): `ValueError`→400/404, `PermissionError`→403.

### 5.2 `TriggerDueSchedulesUseCase`

```python
class TriggerDueSchedulesUseCase:
    def __init__(self, session_factory, schedule_repo_builder,
                 run_agent_uc_builder, sink, logger):
        # schedule_repo_builder: Callable[[AsyncSession], ScheduleRepositoryInterface]
        #   — application 이 infrastructure 를 직접 임포트하지 않도록 빌더 주입
        # run_agent_uc_builder: Callable[[AsyncSession], RunAgentUseCase]
        #   — main.py의 기존 run_uc_factory 내부 조립 로직 재사용 (§6.2)

    async def execute(self, request_id) -> TriggerResult:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # [tx1] claim
        async with self._session_factory() as s:
            async with s.begin():
                claimed = await ScheduleRepository(s, logger).claim_due(now, request_id)
        results = []
        for c in claimed:      # 순차 실행 (Plan §3-4)
            run_record_id = await self._sink.on_started(c.schedule, c.scheduled_for, request_id)
            try:
                # [run tx] 에이전트 실행 — 회차별 독립 세션
                async with self._session_factory() as s:
                    async with s.begin():
                        run_uc = self._run_agent_uc_builder(s)
                        rendered = SchedulePolicy.render_instruction(
                            c.schedule.instruction, c.schedule.timezone, now)  # R9
                        resp = await run_uc.execute(c.schedule.agent_id, RunAgentRequest(
                            query=rendered, user_id=c.schedule.user_id))
                await self._sink.on_finished(run_record_id, "success", request_id,
                                             session_id=resp.session_id, run_id=resp.run_id)
            except Exception as e:
                self._logger.error("schedule run failed", exception=e,
                                   request_id=request_id, schedule_id=c.schedule.id)
                await self._sink.on_finished(run_record_id, "failed", request_id,
                                             error_message=str(e)[:2000])
            # last_run_at 갱신 (짧은 tx)
        return TriggerResult(claimed=..., success=..., failed=...)
```

- 개별 실행 예외는 삼켜서 이력 `failed` 처리 후 다음 스케줄 계속 — 스택 트레이스는 logger로.
- lifespan 싱글턴으로 두되 **AsyncSession 비보유**(session_factory만 보유) → DB-001 lifespan 금지 조항 저촉 없음.
- 마지막 트리거 시각/결과를 인스턴스 필드(in-memory)에 보관 → status 엔드포인트가 노출.

### 5.3 `schemas.py` (application)

```python
class ScheduleSpecPayload(BaseModel):      # 요청/응답 공용
    schedule_type: Literal["once","daily","weekly","cron"]
    run_date: date | None = None
    time_of_day: str | None = None         # "HH:MM"
    days_of_week: list[int] | None = None
    cron_expr: str | None = None

class CreateScheduleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    spec: ScheduleSpecPayload
    instruction: str = Field(..., min_length=1, max_length=1900)
    # R9: {today}/{now}/{weekday} 플레이스홀더 사용 가능
    timezone: str = "Asia/Seoul"
    enabled: bool = True

class UpdateScheduleRequest(CreateScheduleRequest): ...
class ToggleScheduleRequest(BaseModel): enabled: bool

class ScheduleResponse(BaseModel):
    id, agent_id, name, spec, instruction, enabled, timezone: ...
    next_run_at: str | None      # ISO8601 UTC
    last_run_at: str | None
    created_at, updated_at: str

class ScheduleRunResponse(BaseModel):
    id, schedule_id, status, scheduled_for, started_at: ...
    finished_at, session_id, run_id, error_message: ... | None

class TriggerResponse(BaseModel):
    claimed: int; success: int; failed: int; request_id: str
```

---

## 6. Interfaces Layer

### 6.1 라우터 — `src/api/routes/agent_schedule_router.py`

경로는 기존 컨벤션에 따라 실제로는 `/api/v1` prefix 하에 노출된다
(`/api/v1/agents/...`, `/api/v1/internal/schedules/...`).

| Method | Path | UseCase | 인증 | 응답 |
|--------|------|---------|------|------|
| POST | `/agents/{agent_id}/schedules` | Create | JWT | 201 ScheduleResponse |
| GET | `/agents/{agent_id}/schedules` | List | JWT | 200 list |
| GET | `/agents/{agent_id}/schedules/{schedule_id}` | Get | JWT | 200 |
| PUT | `/agents/{agent_id}/schedules/{schedule_id}` | Update | JWT | 200 |
| DELETE | `/agents/{agent_id}/schedules/{schedule_id}` | Delete | JWT | 204 |
| PATCH | `/agents/{agent_id}/schedules/{schedule_id}/enabled` | Toggle | JWT | 200 |
| GET | `/agents/{agent_id}/schedules/{schedule_id}/runs?limit&offset` | ListRuns | JWT | 200 list |
| POST | `/internal/schedules/trigger` | TriggerDue | **X-Scheduler-Token** | 200 TriggerResponse |
| GET | `/internal/schedules/trigger/status` | (싱글턴 조회) | X-Scheduler-Token | 200 마지막 트리거 시각/결과 |

- JWT 경로: `current_user: User = Depends(get_current_user)` — 기존 agent_builder_router 컨벤션.
- 트리거 인증: `X-Scheduler-Token` 헤더 == `settings.scheduler_trigger_token`. 토큰 미설정(빈 문자열) 시 503(기능 비활성), 불일치 시 401. 라우터에 비즈니스 로직 금지 — 토큰 비교는 FastAPI dependency로.

### 6.2 DI 배선 (`src/api/main.py`)

```python
# CRUD: 표준 요청-스코프 팩토리 (DB-001)
def create_schedule_uc_factory(session: AsyncSession = Depends(get_session)):
    return CreateScheduleUseCase(
        schedule_repo=ScheduleRepository(session, app_logger),
        agent_repo=_make_repo(session),      # 기존 헬퍼 재사용
        logger=app_logger,
    )
# ... List/Get/Update/Delete/Toggle/ListRuns 동일 패턴

# Trigger: lifespan 싱글턴 (세션 비보유)
def _build_run_agent_uc(session: AsyncSession) -> RunAgentUseCase:
    # 기존 run_uc_factory(main.py:2137)의 조립 본문을 함수로 추출해 공유
trigger_uc = TriggerDueSchedulesUseCase(
    session_factory=get_session_factory(),
    run_agent_uc_builder=_build_run_agent_uc,
    sink=DbScheduleRunSink(get_session_factory(), app_logger),
    logger=app_logger,
)
```

- **리팩토링 포인트**: 기존 `run_uc_factory`의 RunAgentUseCase 조립 본문을 `_build_run_agent_uc(session)`으로 추출하고, 기존 팩토리와 trigger가 공유 (동작 불변).

### 6.3 설정 (`src/config.py`, `.env.example`)

```python
scheduler_trigger_token: str = ""    # 빈 값 = 트리거 비활성 (503)
```

### 6.4 외부 스케줄러 등록 (운영 문서)

```
# 예: 리눅스 crontab (매 분)
* * * * * curl -s -X POST http://localhost:8000/internal/schedules/trigger \
    -H "X-Scheduler-Token: ${SCHEDULER_TRIGGER_TOKEN}"
# Windows 작업 스케줄러: 동일 curl을 1분 주기 등록
```

---

## 7. DB Migration — `db/migration/V038__create_agent_schedule.sql`

Plan §3-2 DDL 그대로 (테이블 2종 + 인덱스). 요점:

- `agent_schedule.agent_id` → `agent_definition(id)` **ON DELETE CASCADE** — 에이전트 삭제 시 스케줄 동반 삭제.
- `agent_schedule_run.schedule_id` → `agent_schedule(id)` **ON DELETE CASCADE**, `agent_id`는 비정규화 컬럼(FK 없음) — 이력 추적용.
- `INDEX idx_agent_schedule_due (enabled, next_run_at)` — claim 쿼리 커버링.
- datetime 컬럼은 UTC naive 규격 (기존 테이블과 동일).
- `/db-migration` 스킬로 생성 검증.

---

## 8. Test Plan (TDD — 구현 전 작성)

### 8.1 domain (`tests/domain/agent_schedule/`)

- `test_schedule_spec.py`: 유형별 필수/금지 필드 조합 (once에 cron_expr → ValueError 등), days_of_week 범위/중복.
- `test_schedule_policy.py`:
  - `compute_next_run` — daily(오늘 시각 전/후), weekly(요일 wrap-around, 다중 요일), once(미래/과거), cron(다음 발화), **KST→UTC 환산 경계(자정 근처)**.
  - `validate_spec` — 잘못된 cron, 10분 미만 간격 cron(`* * * * *`) 거부, 과거 once 거부, 잘못된 tz.
  - `validate_count` — 10개 초과 거부. `can_modify` — 소유자/타인.
  - `render_instruction` (R9) — `{today}`/`{now}`/`{weekday}` 각 치환(스케줄 tz 기준, UTC와 날짜가 갈리는 자정 경계 포함), 미지원 `{foo}` 원문 유지, 플레이스홀더 없는 지침 원문 그대로, 2000자 초과 절단.

### 8.2 infrastructure (`tests/infrastructure/agent_schedule/`)

- repository CRUD round-trip (aiosqlite in-memory — 기존 패턴).
- `claim_due`: due 2건+미래 1건 → 2건 클레임, next_run_at 재계산 반영, once는 enabled=False. (SKIP LOCKED는 sqlite 미지원 → `with_for_update` 분기 or MySQL 통합 테스트 마킹 — 기존 테스트 인프라 관례 따름)
- `DbScheduleRunSink`: on_started→running INSERT, on_finished→success/failed UPDATE.

### 8.3 application (`tests/application/agent_schedule/`)

- CRUD 7종: 정상/403(타인)/404(미존재)/상한 초과/spec 변경 시 next_run_at 재계산/off→on 재계산.
- `TriggerDueSchedulesUseCase` (repo·sink·run_uc mock):
  - due 2건 → run_uc 2회 호출, sink started/finished 쌍 기록.
  - 지침에 `{today}` 포함 → run_uc에 전달된 `RunAgentRequest.query`가 치환 완료된 텍스트인지 검증 (R9).
  - 1건 실행 예외 → 해당 건 failed 이력 + 나머지 계속 + 응답 failed=1.
  - due 0건 → run_uc 미호출, claimed=0.

### 8.4 api (`tests/api/`)

- 트리거: 토큰 없음/불일치 401, 미설정 503, 정상 200.
- CRUD 라우팅/스키마 검증 (기존 auth DI override 패턴).

### 8.5 포크 회귀 (`tests/application/agent_builder/`)

- `test_fork_excludes_schedules.py`: 원본 에이전트에 스케줄 2건 → `ForkAgentUseCase` 실행 → 사본 agent_id 스케줄 0건. `AutoForkService.fork_for_subscribers` 동일.

---

## 9. Implementation Order (Do 단계 체크리스트)

1. `pyproject.toml`에 `croniter>=2.0` 추가 + 설치
2. **[TDD]** domain: value_objects → policies (§8.1 테스트 선행)
3. V038 마이그레이션 + ORM models
4. **[TDD]** infrastructure: repository → claim_due → run_sink (§8.2)
5. **[TDD]** application: CRUD 7종 → schemas (§8.3)
6. **[TDD]** application: TriggerDueSchedulesUseCase (§8.3)
7. interfaces: router + config(`scheduler_trigger_token`) + `.env.example` + main.py DI (run_uc 조립 본문 추출 리팩토링 포함)
8. **[TDD]** api 테스트 (§8.4) + 포크 회귀 (§8.5)
9. `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과
10. `/pdca analyze agent-schedule`

---

## 10. 영향 범위 / 주의사항

- **기존 코드 수정 최소**: `main.py`(DI 추가 + run_uc 조립 추출), `config.py`(+1 필드), `.env.example`. 포크/실행 유스케이스 본체는 무수정.
- **프론트 후속**: 이 문서의 §5.3 스키마가 API 계약 — 프론트 작업 시 `/api-cotract` 스킬로 타입 동기화 (후속 feature `agent-schedule-ui`).
- **운영 전제**: 외부 cron 등록 없이는 스케줄이 실행되지 않음 — 배포 체크리스트에 §6.4 등록 절차 포함 필수.
- **비용 가드**: 스케줄 실행도 ai_run으로 기록되므로 기존 usage 집계에 자동 포함.
