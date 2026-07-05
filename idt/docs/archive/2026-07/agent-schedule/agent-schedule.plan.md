# Plan: agent-schedule

> Created: 2026-07-02
> Phase: Plan
> Scope: `idt/` 백엔드 — 에이전트에 스케줄 기능 추가. 독립 도메인(`agent_schedule`)으로 분리해 CRUD 가능하게 하고, 외부 트리거 방식 실행 엔진까지 백엔드 완결. 프론트 UI는 후속 feature.

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 에이전트는 사용자가 직접 질문할 때만 실행된다. "매일 아침 9시에 시황 요약", "매주 월요일 리포트 생성" 같은 정기/예약 실행이 불가능하고, 이를 담을 도메인·테이블·실행 인프라가 전무하다. |
| **Solution** | `agent_schedule`을 **독립 도메인 + 별도 테이블(agent_definition FK)**로 신설해 CRUD API를 제공한다. 반복 유형은 once(특정 날짜 1회)/daily/weekly(요일)/cron(자유 표현식) 4종, 에이전트당 복수 스케줄 허용. 실행은 **외부 트리거 방식** — 보호된 내부 엔드포인트(`POST /internal/schedules/trigger`)를 OS cron/작업 스케줄러가 주기 호출하면, 앱이 due 판정 → `RunAgentUseCase` 실행 → 이력 기록 + 새 대화 세션 생성. 결과 처리부는 `ScheduleRunSink` 포트로 추상화해 추후 변경(알림 등)에 유연하게 대응한다. |
| **Function/UX Effect** | 사용자는 에이전트마다 여러 개의 스케줄을 등록/수정/삭제/on-off 할 수 있고, 스케줄마다 **지침(instruction)**을 넣으면 실행 시점에 `{today}` 등 시점 변수가 치환되어 **실제 사용자 질문처럼** 새 대화 세션에 전송된다. 결과는 채팅 목록에서 열람 + 실행 이력(성공/실패)으로 추적 가능하다. |
| **Core Value** | 에이전트를 "질문에 답하는 도구"에서 "정해진 시간에 스스로 일하는 워커"로 확장. 스케줄은 별도 테이블이므로 **포크(수동/자동) 시 절대 복사되지 않아** 원본 소유자의 스케줄이 사본으로 유출·중복 실행되는 일이 없다. |

---

## 1. 배경 / 문제 정의

### 1-1. 현재 상태

- 에이전트 실행 진입점은 `RunAgentUseCase.execute/stream` 단 하나이며, 입력은 `RunAgentRequest{query, user_id, session_id?, attachments?}` (`src/application/agent_builder/schemas.py:133`). `session_id`가 없으면 새 세션이 만들어진다.
- 스케줄러 인프라 부재: 코드베이스 전체에 APScheduler/Celery/cron 관련 코드가 없다 (grep 확인).
- 에이전트 포크 경로는 2개이며 **둘 다 필드 화이트리스트 방식**으로 새 `AgentDefinition`을 조립한다:
  - 수동 포크: `ForkAgentUseCase` (`src/application/agent_builder/fork_agent_use_case.py:59-76`)
  - 구독 자동 포크: `AutoForkService.fork_for_subscribers` (`src/application/agent_builder/auto_fork_service.py:55`)

### 1-2. 요구사항 (사용자 확정)

| # | 요구 | 확정 내용 |
|---|------|----------|
| R1 | 스케줄을 독립 도메인으로 분리, CRUD 가능 | `src/domain/agent_schedule/` 신설 + CRUD API |
| R2 | 반복 유형 | once(특정 날짜 1회) / daily(매일) / weekly(요일 지정) / **cron(자유 표현식)** |
| R3 | 시각 지정 | 스케줄별 실행 시각(HH:MM) 지정, 타임존 기본 Asia/Seoul |
| R4 | 복수 스케줄 | 에이전트 1개에 스케줄 N개 등록 가능 |
| R5 | **포크 시 미복사** | 포크(수동/자동)된 에이전트에는 스케줄이 절대 따라가지 않는 DB 구성 |
| R6 | 실행 결과 | 실행 이력 테이블 + 새 대화 세션. 단, **추후 설계 변경에 유연하도록 결과 처리부를 추상화** |
| R7 | 실행 메커니즘 | **외부 트리거 방식** — 앱은 판정/실행만, 주기 호출은 외부(OS cron 등)가 담당 |
| R8 | 범위 | 백엔드 전체 (도메인 + CRUD API + 실행 엔진). 프론트 UI는 후속 |
| R9 | **스케줄별 지침(instruction)** | 각 스케줄에 지침을 저장하고, 실행 시점에 **실제 사용자 질문처럼** 새 대화 세션의 user 메시지로 전송. `{today}`/`{now}`/`{weekday}` 시점 변수 치환 지원 (예: "오늘({today}) 기준 시황 요약해줘") |

### 1-3. 핵심 판단 — 포크 미복사는 "별도 테이블"로 구조적으로 보장

포크 두 경로 모두 원본 필드를 **명시적으로 나열해 복사**하므로, 스케줄을 `agent_definition` 컬럼(JSON 등)이 아닌 **별도 테이블 `agent_schedule`(FK)**로 두면 포크 코드를 한 줄도 건드리지 않아도 사본에는 스케줄이 0건이다. 반대로 JSON 컬럼으로 넣으면 포크 코드마다 제외 처리를 해야 해서 누락 위험이 생긴다. → **별도 테이블 채택. 포크 유스케이스에 스케줄 미복사 회귀 테스트를 추가**해 향후 포크 로직이 "전체 컬럼 복사" 방식으로 바뀌어도 깨지도록 방어한다.

---

## 2. 목표 / 비목표

### 2-1. 목표

- **G1.** `agent_schedule` 도메인 신설: Entity(`AgentSchedule`), VO(`ScheduleSpec`), Policy(검증·권한·상한) — Thin DDD 레이어 준수.
- **G2.** DB: `agent_schedule`(스케줄 정의) + `agent_schedule_run`(실행 이력) 2개 테이블, Flyway `V038` 마이그레이션.
- **G3.** CRUD API: 생성/목록/단건/수정/삭제 + enable·disable, 실행 이력 조회. 소유자만 접근.
- **G4.** 실행 엔진: 외부 트리거용 보호 엔드포인트 → due 스케줄 클레임(동시 호출 안전) → `RunAgentUseCase` 실행 → `next_run_at` 재계산 → 이력 기록.
- **G5.** 결과 처리 seam: `ScheduleRunSink` 포트(인터페이스) 정의. 기본 구현 = 이력 기록 + 새 대화 세션. 추후 알림/웹훅 sink를 additive로 추가 가능.
- **G6.** 포크(수동/자동) 시 스케줄 미복사 — 회귀 테스트로 고정.
- **G7.** TDD(테스트 선행), 아키텍처/로깅 규칙(verify-architecture, verify-logging) 통과.

### 2-2. 비목표 (이번 범위 제외)

- **N1.** 프론트엔드 UI (스케줄 관리 화면) — 후속 feature `agent-schedule-ui`.
- **N2.** 인프로세스 백그라운드 스케줄러(폴링 루프/APScheduler) — 외부 트리거로 확정. 단, 트리거 진입을 유스케이스로 분리해 추후 인프로세스 전환 시 재사용 가능하게 함.
- **N3.** 실행 결과 알림(이메일/웹훅/푸시) — `ScheduleRunSink` seam만 확보.
- **N4.** 놓친 스케줄 백필(서버 다운 동안 지나간 회차를 소급 실행) — 미실행분은 1회로 접고 다음 회차 재계산(§3-4 misfire 정책).
- **N5.** 스케줄 실행 시 attachments(엑셀 등) 지정 — query 텍스트만 지원, 필요 시 후속.

---

## 3. 해결 방안

### 3-1. 도메인 모델

```
AgentSchedule (Entity)
  id: str(uuid)
  agent_id: str            # FK → agent_definition.id (CASCADE)
  user_id: str             # 스케줄 생성자 = 실행 주체 (RunAgentRequest.user_id로 사용)
  name: str                # 표시명 (예: "아침 시황 요약")
  spec: ScheduleSpec       # 반복 규칙 VO
  instruction: str         # 지침 (R9). 실행 시점에 시점 변수({today} 등) 치환 후
                           # 실제 사용자 질문으로 전송 (렌더링 결과 1..2000자, RunAgentRequest 제약)
  enabled: bool
  timezone: str            # IANA tz, 기본 "Asia/Seoul"
  next_run_at: datetime|None  # UTC. 다음 실행 시각(판정 키). once 소진/disable 시 None
  last_run_at: datetime|None
  created_at / updated_at

ScheduleSpec (VO, discriminated union)
  schedule_type: "once" | "daily" | "weekly" | "cron"
  run_date:     date|None        # once 전용
  time_of_day:  time|None        # once/daily/weekly 전용 (HH:MM)
  days_of_week: list[int]|None   # weekly 전용, 0=월..6=일, 1개 이상
  cron_expr:    str|None         # cron 전용, 5-field crontab
```

**next_run_at 계산**: `SchedulePolicy.compute_next_run(spec, tz, after)`가 도메인에서 담당.
- once → `run_date+time_of_day` 1회. 실행 후 `next_run_at=None` + `enabled=False`(소진).
- daily/weekly → tz 기준 다음 해당 시각을 UTC로 환산.
- cron → `croniter` 라이브러리로 다음 발화 시각 계산. **의존성 추가: `croniter`** (경량, cron 파싱 표준). 단 croniter는 infrastructure 관심사가 아니라 순수 계산이므로 domain policy에서 직접 사용해도 CLAUDE.md 금지항목(외부 API·DB·LangChain)에 저촉되지 않음 — Design에서 최종 확정.

**SchedulePolicy 검증 규칙**:
- 에이전트당 스케줄 상한 `MAX_SCHEDULES_PER_AGENT = 10`.
- cron_expr 유효성(5필드, 파싱 가능), 최소 간격 가드(예: 분 단위 `* * * * *` 같은 과밀 cron 금지 — 최소 10분 간격, Design에서 확정).
- once의 run_date+time은 미래여야 함.
- CRUD 권한: **스케줄 소유자(user_id) 본인만**. 에이전트 소유자 ≠ 스케줄 생성자 케이스는 "본인 소유 에이전트에만 스케줄 생성 가능"으로 단순화(구독/공용 에이전트에 스케줄을 걸려면 포크 후 자기 사본에 걸도록 유도).

### 3-2. DB 설계 (V038)

```sql
-- V038__create_agent_schedule.sql
CREATE TABLE agent_schedule (
  id            VARCHAR(36) PRIMARY KEY,
  agent_id      VARCHAR(36) NOT NULL,
  user_id       VARCHAR(100) NOT NULL,
  name          VARCHAR(200) NOT NULL,
  schedule_type VARCHAR(10)  NOT NULL,          -- once|daily|weekly|cron
  run_date      DATE NULL,
  time_of_day   TIME NULL,
  days_of_week  JSON NULL,                      -- [0,2,4]
  cron_expr     VARCHAR(100) NULL,
  instruction   TEXT NOT NULL,                  -- R9: 지침 (실행 시 변수 치환 → user 질문)
  enabled       TINYINT(1) NOT NULL DEFAULT 1,
  timezone      VARCHAR(50) NOT NULL DEFAULT 'Asia/Seoul',
  next_run_at   DATETIME NULL,
  last_run_at   DATETIME NULL,
  created_at    DATETIME NOT NULL,
  updated_at    DATETIME NOT NULL,
  CONSTRAINT fk_agent_schedule_agent
    FOREIGN KEY (agent_id) REFERENCES agent_definition(id) ON DELETE CASCADE,
  INDEX idx_agent_schedule_due (enabled, next_run_at),   -- due 판정 쿼리 키
  INDEX idx_agent_schedule_agent (agent_id)
);

CREATE TABLE agent_schedule_run (
  id            VARCHAR(36) PRIMARY KEY,
  schedule_id   VARCHAR(36) NOT NULL,
  agent_id      VARCHAR(36) NOT NULL,           -- 스케줄 삭제 후에도 이력 조회 가능하도록 비정규화
  status        VARCHAR(10) NOT NULL,           -- running|success|failed
  scheduled_for DATETIME NOT NULL,              -- 원래 예정 시각
  started_at    DATETIME NOT NULL,
  finished_at   DATETIME NULL,
  session_id    VARCHAR(36) NULL,               -- 생성된 대화 세션
  run_id        VARCHAR(36) NULL,               -- ai_run 연결 (AGENT-OBS-001)
  error_message TEXT NULL,
  request_id    VARCHAR(64) NOT NULL,
  CONSTRAINT fk_schedule_run_schedule
    FOREIGN KEY (schedule_id) REFERENCES agent_schedule(id) ON DELETE CASCADE,
  INDEX idx_schedule_run_schedule (schedule_id, started_at),
  INDEX idx_schedule_run_agent (agent_id, started_at)
);
```

**포크 미복사 보장(R5)**: 스케줄은 `agent_definition`에 컬럼을 추가하지 않고 위 별도 테이블에만 존재. `ForkAgentUseCase`/`AutoForkService`는 원본 필드를 화이트리스트로 복사하므로 사본의 `agent_schedule` 행은 자연히 0건. 에이전트 삭제 시 CASCADE로 스케줄·이력 동반 삭제.

### 3-3. API 설계

| Method | Path | 설명 |
|--------|------|------|
| POST | `/agents/{agent_id}/schedules` | 스케줄 생성 (본인 소유 에이전트만) |
| GET | `/agents/{agent_id}/schedules` | 목록 |
| GET | `/agents/{agent_id}/schedules/{schedule_id}` | 단건 |
| PUT | `/agents/{agent_id}/schedules/{schedule_id}` | 수정 (spec 변경 시 next_run_at 재계산) |
| DELETE | `/agents/{agent_id}/schedules/{schedule_id}` | 삭제 |
| PATCH | `/agents/{agent_id}/schedules/{schedule_id}/enabled` | on/off 토글 (off→on 시 next_run_at 재계산) |
| GET | `/agents/{agent_id}/schedules/{schedule_id}/runs` | 실행 이력 (페이지네이션) |
| POST | `/internal/schedules/trigger` | **외부 트리거 진입점** (아래 §3-4) |

라우터는 기존 컨벤션대로 `src/api/routes/agent_schedule_router.py` 신설, `main.py` 등록.

### 3-4. 실행 엔진 (외부 트리거)

```
[외부 스케줄러: OS cron / Windows 작업 스케줄러 / k8s CronJob]
   └─ 매 분: POST /internal/schedules/trigger  (X-Scheduler-Token 헤더)
        └─ TriggerDueSchedulesUseCase
             1. claim: UPDATE agent_schedule SET next_run_at=<재계산>
                WHERE enabled=1 AND next_run_at <= NOW()  (원자적 선점 → 동시 호출 중복 실행 방지)
             2. 클레임된 각 스케줄에 대해:
                  rendered = SchedulePolicy.render_instruction(schedule.instruction, tz, now)
                    # {today}/{now}/{weekday} 치환 → 실제 사용자 질문 텍스트 (R9)
                  RunAgentUseCase.execute(RunAgentRequest(
                      query=rendered, user_id=schedule.user_id, session_id=None))
                  → 새 세션 자동 생성 + rendered가 user 메시지로 저장
                    (세션을 열면 실제 질문한 것처럼 보임), ai_run 관측성 그대로 활용
             3. ScheduleRunSink.on_started/on_finished 호출 → agent_schedule_run 기록
             4. 응답: {claimed: n, success: n, failed: n}
```

- **인증**: `SCHEDULER_TRIGGER_TOKEN` 환경변수(설정은 `src/config.py`, 하드코딩 금지) 검증. 불일치 시 401.
- **동시성/멱등성**: 1단계에서 `next_run_at`을 조건부 UPDATE로 선점(claim)하므로 트리거가 겹쳐 호출돼도 같은 회차가 두 번 실행되지 않음.
- **misfire 정책**: 서버 다운으로 `next_run_at`이 과거로 밀린 경우, 밀린 횟수와 무관하게 **1회만 실행**하고 다음 회차는 "현재 시각 이후"로 재계산 (백필 없음, N4).
- **실행 실패**: 이력에 `failed` + `error_message`(스택 트레이스는 logger로) 기록. 재시도 없음(다음 회차에 자연 재실행). 반복 실패 스케줄 자동 disable은 후속 검토.
- **순차/병렬**: 초기 구현은 클레임 건들을 순차 실행(LLM 비용·부하 예측 가능). 병렬화는 후속.

### 3-5. 결과 처리 seam — `ScheduleRunSink` (R6 유연성)

```
# domain/agent_schedule/interfaces.py
ScheduleRunSinkInterface:
  on_started(schedule, scheduled_for, request_id) -> run_record_id
  on_finished(run_record_id, status, session_id?, run_id?, error?) 

# infrastructure 기본 구현: DbScheduleRunSink
  → agent_schedule_run 테이블 기록 (세션은 RunAgentUseCase가 이미 생성)
```

추후 "알림 발송", "결과를 특정 채널로 전달" 등 설계 변경 시 sink 구현체 추가/교체만으로 대응 — `TriggerDueSchedulesUseCase`는 수정 불필요.

### 3-6. 레이어 배치 (Thin DDD)

| Layer | 신규 파일 |
|-------|----------|
| domain | `domain/agent_schedule/{entity.py, value_objects.py, policies.py, interfaces.py}` |
| application | `application/agent_schedule/{create_..., list_..., get_..., update_..., delete_..., toggle_..., list_runs_..., trigger_due_schedules_use_case.py, schemas.py}` |
| infrastructure | `infrastructure/agent_schedule/{models.py, schedule_repository.py, schedule_run_repository.py, run_sink.py}` |
| interfaces/api | `api/routes/agent_schedule_router.py`, `main.py` DI 배선, `config.py` 토큰 설정 |
| db | `db/migration/V038__create_agent_schedule.sql` |

세션/트랜잭션은 DB-001 규칙 준수: Repository는 commit/rollback 금지, UseCase 단위 단일 세션.

---

## 4. 구현 순서 (Design 후 Do 단계 가이드)

1. **[TDD] 도메인**: `ScheduleSpec` 검증 + `compute_next_run`(once/daily/weekly/cron × tz 경계) 테스트 → 구현. `croniter` 의존성 추가.
2. **[TDD] DB/Repository**: V038 마이그레이션, ORM 모델, `find_due_and_claim` 원자성 테스트 → 구현.
3. **[TDD] CRUD UseCase + Router**: 생성~삭제~토글~이력, 권한(타인 403)·상한(10개)·유효성 테스트 → 구현.
4. **[TDD] 실행 엔진**: `TriggerDueSchedulesUseCase` — claim 멱등성, RunAgent 연동(mock), sink 기록, misfire, 실패 이력 테스트 → 구현. 트리거 엔드포인트 + 토큰 인증.
5. **[TDD] 포크 회귀**: `ForkAgentUseCase`/`AutoForkService` 실행 후 사본 agent_id로 스케줄 조회 시 0건 테스트.
6. **검증**: `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과 → `/pdca analyze agent-schedule`.

---

## 5. 리스크 / 주의사항

| 리스크 | 대응 |
|--------|------|
| 외부 트리거가 멈추면 스케줄 전체 정지 | 운영 문서에 외부 cron 등록 절차 명시. `GET /internal/schedules/trigger` 헬스/최근 트리거 시각 노출 검토(Design) |
| 트리거 중복 호출로 이중 실행 | next_run_at 조건부 UPDATE 선점(claim)으로 구조적 차단 + 테스트 |
| cron 과밀(매분 실행)로 LLM 비용 폭증 | SchedulePolicy 최소 간격 가드 + 에이전트당 10개 상한 |
| 스케줄 실행은 인증 미들웨어 밖(유저 토큰 없음) | `schedule.user_id`를 RunAgentRequest.user_id로 사용. RunAgentUseCase의 접근 정책 통과 여부 Design에서 검증 (본인 소유 에이전트만 허용이므로 원칙상 통과) |
| DST/타임존 경계 오차 | tz-aware 계산 후 UTC 저장. Asia/Seoul은 DST 없어 저위험이나 tz 필드로 일반화 |
| 에이전트 삭제/모델 삭제 후 스케줄 실행 | agent CASCADE로 스케줄 소멸. 실행 시점 agent 미존재는 failed 이력 처리 |
| 포크 로직이 향후 "전체 복사"로 바뀔 가능성 | 미복사 회귀 테스트(4-5)로 고정 |

---

## 6. 완료 기준 (Check 지표)

- [ ] V038 적용 후 CRUD API 전 엔드포인트 정상 동작 (소유자 외 403)
- [ ] once/daily/weekly/cron 각 유형의 next_run_at 계산 정확 (tz 포함)
- [ ] 지침의 `{today}`/`{now}`/`{weekday}` 치환 정확, 렌더링 결과가 새 세션 user 메시지로 저장 (R9)
- [ ] 트리거 호출 → due 스케줄 실행 → 새 세션 + 이력(success) 생성 확인
- [ ] 트리거 동시 2회 호출 시 이중 실행 없음
- [ ] once 스케줄 실행 후 자동 disable
- [ ] 포크(수동/자동) 사본에 스케줄 0건
- [ ] verify-architecture / verify-logging / verify-tdd 통과
