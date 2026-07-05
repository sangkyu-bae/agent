# agent-schedule Completion Report

> **Summary**: 에이전트 스케줄링 기능 — 독립 도메인 CRUD + 외부 트리거 실행 엔진. once/daily/weekly/cron 4유형, 에이전트당 최대 10개, 포크 시 미복사 구조 보장, 지침 시점 변수 치환.
>
> **Project**: sangplusbot (idt)
> **Feature**: agent-schedule
> **Completion Date**: 2026-07-03
> **Status**: ✅ Completed

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| **Feature** | 에이전트 스케줄 — once/daily/weekly/cron 4유형, CRUD API + 외부 트리거 실행 엔진. 포크 시 미복사 구조. 지침 변수(`{today}`/`{now}`/`{weekday}`) 치환 후 실제 사용자 질문으로 전송. |
| **Duration** | 2026-07-02 ~ 2026-07-03 (2일) |
| **Metrics** | 신규 파일 28개(src 19 + test 9), 테스트 111개 전부 통과, V038 마이그레이션, croniter>=2.0 의존성 |
| **Match Rate** | 초기 96% → Act-1 반영 후 **98%** ✅ |
| **Iteration** | 1회 (Gap-1: last_run_at 정책 → A안 채택, Gap-2,3: 문서·상수화 동기화) |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | 에이전트는 사용자 직접 질문 시에만 실행. 정기/예약 실행("매일 아침 9시 시황 요약") 불가능. 도메인·테이블·실행 인프라 전무. |
| **Solution** | `agent_schedule` 독립 도메인 신설(CRUD API, 별도 테이블 FK). once/daily/weekly/cron 4유형. 외부 트리거 방식(OS cron 등이 매 분 호출) — 앱은 due 판정·실행만. 지침을 시점 변수 치환 후 실제 질문으로 변환(R9). 결과 처리를 `ScheduleRunSink` 인터페이스로 추상화(추후 알림 등 유연 대응). |
| **Function/UX Effect** | 사용자가 에이전트당 여러 스케줄 등록/수정/삭제/on-off 가능. 스케줄마다 지침 설정 시 `{today}` 등 시점 변수 자동 치환되어 새 대화 세션 user 메시지로 저장. 세션 열면 사용자 직접 질문한 것처럼 보임. 실행 이력(성공/실패) 추적 가능. |
| **Core Value** | 에이전트를 "질문에 답하는 도구"에서 "정해진 시간에 스스로 일하는 워커"로 확장. 스케줄은 별도 테이블이므로 포크(수동/자동) 시 절대 복사 안 됨 — 원본 소유자 스케줄이 사본으로 유출·중복 실행 차단. |

---

## PDCA Cycle Summary

### Plan (2026-07-02)

**문서**: [docs/01-plan/features/agent-schedule.plan.md](../../01-plan/features/agent-schedule.plan.md)

- **목표**: 독립 도메인 CRUD + 외부 트리거 실행 엔진 구축. once/daily/weekly/cron 4유형. 포크 시 미복사 보장.
- **범위**: 백엔드 전체 (도메인 + CRUD API + 실행 엔진). 프론트 UI는 후속(`agent-schedule-ui` feature).
- **핵심 판단**: 스케줄을 `agent_definition` 컬럼(JSON)이 아닌 **별도 테이블**로 두면, 포크 유스케이스(필드 화이트리스트 복사)를 한 줄도 건드리지 않아도 사본에 스케줄이 0건.

### Design (2026-07-02)

**문서**: [docs/02-design/features/agent-schedule.design.md](../../02-design/features/agent-schedule.design.md)

**핵심 설계 결정**:

| 항목 | 결정 | 근거 |
|------|------|------|
| croniter 사용 레이어 | domain policy에서 직접 사용 | 순수 시간 계산(외부 I/O 없음), CLAUDE.md 금지 대상 아님 |
| cron 최소 간격 | 10분 | LLM 비용 폭증 방지 |
| 타임존 | stdlib `zoneinfo` (Python 3.11) | 추가 의존성 불필요 |
| 트리거 동시성 | `FOR UPDATE SKIP LOCKED` | MySQL 8+, 겹친 호출이 잔여만 클레임 |
| 트리거 세션 | session_factory 주입 | 회차별 짧은 트랜잭션 — 락 장기 점유 회피 |
| 지침 변수 (R9) | `{today}`/`{now}`/`{weekday}` 3종 | str.replace 순수 계산, 도메인 배치 |

**기존 실행 경로 재사용**: `RunAgentUseCase.execute()`를 그대로 호출 → ai_run 관측성·세션 자동 생성·스킬 주입 전부 무료.

### Do (2026-07-02~03)

**구현 요약**:

#### 신규 파일 (28개)

| Layer | 파일 개수 | 설명 |
|-------|:-------:|------|
| domain | 4 | entity.py, value_objects.py, policies.py, interfaces.py |
| application | 8 | create/list/get/update/delete/toggle/list_runs/trigger use cases + schemas.py |
| infrastructure | 5 | models.py, schedule_repository.py, schedule_run_repository.py, run_sink.py, __init__.py |
| interfaces | 1 | agent_schedule_router.py |
| db | 1 | V038__create_agent_schedule.sql |
| tests | 9 | test_value_objects.py, test_policies.py, test_repository.py, test_run_sink.py, 5개 application 테스트 + 1개 api 테스트 + 1개 포크 회귀 테스트 |

#### 기존 파일 수정

| 파일 | 변경 | 영향 |
|------|------|------|
| `src/api/main.py` | DI 배선 추가 + run_uc 조립 본문 추출 | 기존 동작 불변 |
| `src/config.py` | `scheduler_trigger_token` 필드 추가 | 필수 설정값 (빈 문자열 = 비활성) |
| `.env.example` | 트리거 토큰 예시 추가 | 배포 설정 가이드 |
| `pyproject.toml` | `croniter>=2.0` 의존성 | 신규 import |

#### 테스트 현황

- **111개 전부 통과** ✅
  - domain: 35개 (Spec 조합, Policy 계산·검증, Entity)
  - infrastructure: 28개 (CRUD, claim_due, Sink)
  - application: 40개 (CRUD 7종, Trigger 실패 격리, R9 렌더링)
  - api: 6개 (토큰 인증, 스키마)
  - 포크 회귀: 2개 (수동/자동 포크 스케줄 미복사)

### Check (2026-07-03)

**문서**: [docs/03-analysis/agent-schedule.analysis.md](../../03-analysis/agent-schedule.analysis.md)

**Gap-Detector 결과**:

| 구분 | 판정 |
|------|:----:|
| Design Match | 97% |
| Architecture (Thin DDD / DB-001) Compliance | 100% |
| Test Plan Coverage | 95% |
| **Overall Match Rate** | **96%** |

**식별된 Gap**:

| # | 항목 | Gap 내용 | 심각도 |
|---|------|---------|:------:|
| 1 | last_run_at 갱신 | 설계: 회차 후(성공/실패 무관 해석 여지), 구현: 성공 시만 갱신 | 중 |
| 2 | TriggerUC 시그니처 | 구현에 `schedule_repo_builder` 파라미터 추가 (개선) | 하 |
| 3 | 문서 미동기화 | Design에 `validate_instruction`, `PLACEHOLDERS` 상수 미명시 | 하 |

### Act (2026-07-03)

**사용자 결정 (A안)**: last_run_at = 성공/실패 **공통 경로**로 갱신. "마지막 실행 시도" 시각 기록.

**조치**:

| # | 항목 | 조치 | 상태 |
|---|------|------|:----:|
| 1 | **[중] last_run_at 정책** | `_run_one`에서 성공/실패 공통 경로로 `_touch_last_run` 이동 + 실패 시 갱신 테스트 추가 | ✅ 해소 |
| 2 | **[하] Design 동기화** | §2.2 A안 문구, §3.2 `validate_instruction` 메서드 추가, §5.2 `schedule_repo_builder` 시그니처, §6.1 `/api/v1` prefix 명시 | ✅ 해소 |
| 3 | **[하] 상수화** | `SchedulePolicy.PLACEHOLDERS` 노출 + `render_instruction`이 상수 순회로 치환 | ✅ 해소 |
| 4 | **[하] MySQL 통합 테스트** | SKIP LOCKED 실제 동시성 MySQL 통합 테스트 마킹(배포 환경 검증 시 구성) | ⏳ 후속 |

**최종 상태**: 반영 후 테스트 **111개 전부 통과**. Match Rate **96% → 98%**.

---

## 검증 결과

### 규칙 준수

| 검증 | 결과 | 세부 |
|------|:----:|------|
| `/verify-architecture` | ✅ PASS | Thin DDD 레이어 준수, domain ← application/infrastructure 의존성 통과 |
| `/verify-logging` | ✅ PASS | StructuredLogger 사용, print() 없음 |
| `/verify-tdd` | ✅ PASS | 전 모듈 RED→GREEN 사이클 |

### 구현 특성

- **TDD 준수**: 모든 모듈 테스트 선행 후 구현
- **DB-001 준수**: Repository는 commit/rollback 금지, 요청당 단일 세션 (Trigger 회차별 짧은 트랜잭션 선례: `RunAgentUseCase.session_factory`)
- **CLAUDE.md 준수**: croniter는 순수 계산이므로 domain 사용 허용, 그 외 외부 API·DB·LangChain 도메인 진입 없음

---

## 핵심 구현 포인트

### 1. 포크 미복사 보장 (R5)

스케줄을 `agent_definition`의 컬럼이 아닌 **별도 테이블**(`agent_schedule`, FK `agent_id`)로 배치:

```python
# ForkAgentUseCase, AutoForkService 모두 필드 화이트리스트 복사
# 스케줄은 별도 테이블이므로 사본에 자동 0건
# agent_id CASCADE 삭제로 에이전트 삭제 시 스케줄·이력 동반 삭제
```

회귀 테스트: `test_fork_excludes_schedules.py` — 원본 스케줄 2건 → 사본 조회 시 0건 ✅

### 2. 외부 트리거 방식 (R7)

```
[외부 스케줄러 (OS cron / Windows 작업 스케줄러 / k8s CronJob)]
  ↓ 매 분: POST /internal/schedules/trigger (X-Scheduler-Token)
  ↓
[TriggerDueSchedulesUseCase]
  1. [짧은 tx] SELECT...FOR UPDATE SKIP LOCKED (next_run_at <= now)
     → next_run_at 재계산(once는 disable) + 커밋
  2. 각 회차별 짧은 tx: RunAgentUseCase.execute(rendered query)
     → 새 세션 자동 생성, query가 user 메시지로 저장
  3. ScheduleRunSink.on_finished(success|failed) → 이력 기록
```

**동시성 안전**: FOR UPDATE SKIP LOCKED로 겹친 호출 중 1회만 실행. misfire 정책: 밀린 회차는 1회만 실행, 백필 없음.

### 3. 지침 변수 치환 (R9)

```python
# SchedulePolicy.render_instruction(instruction, tz, now_utc)
# "{today} 기준 시황 요약" → "2026-07-03 기준 시황 요약"
# {today}: YYYY-MM-DD (스케줄 tz 기준)
# {now}: HH:MM (스케줄 tz 기준)
# {weekday}: 월~일 한글 (스케줄 tz 기준)
# 미지원 플레이스홀더({foo}) 원문 유지
```

**렌더링 결과가 실제 사용자 질문**: `RunAgentUseCase.execute(RunAgentRequest(query=rendered))`로 호출 → 새 세션 user 메시지로 저장 → 세션 열면 사용자 직접 질문한 것처럼 보임.

### 4. 결과 처리 추상화 (R6)

```python
# domain/agent_schedule/interfaces.py
class ScheduleRunSinkInterface:
  async def on_started(schedule, scheduled_for, request_id) -> run_record_id
  async def on_finished(run_record_id, status, request_id, ...)
```

**현재 구현**: `DbScheduleRunSink` — agent_schedule_run 테이블 기록.
**추후 확장**: Sink 구현체 추가(알림, 웹훅 등) 가능 — TriggerDueSchedulesUseCase 수정 불필요.

### 5. 권한·검증 정책 (SchedulePolicy)

| 규칙 | 내용 |
|------|------|
| `MAX_SCHEDULES_PER_AGENT` | 10개 (에이전트당 상한) |
| `MIN_CRON_INTERVAL_MINUTES` | 10분 (과밀 cron 방지) |
| `can_modify(schedule_user_id, viewer_user_id)` | 스케줄 소유자만 수정 가능 |
| `validate_spec(spec, tz, now)` | cron 유효성, once는 미래 시각 필수 |
| `validate_instruction(instruction)` | 1~1900자, 렌더링 후 2000자 이하 보장 |

---

## 배운 점 / 후속 과제

### What Went Well (✅)

1. **Thin DDD 레이어 일관성**: domain에 croniter 순수 계산을 배치, infrastructure로 의존성 오염 없음.
2. **기존 경로 재사용**: RunAgentUseCase 그대로 호출하면 ai_run 관측성·세션·스킬 자동 획득 — 기존 API 확장이 아닌 새 도메인 CRUD로 느슨하게 결합.
3. **포크 미복사 구조**: 별도 테이블 선택으로 기존 포크 로직 무수정 — 회귀 테스트로 향후 보호.
4. **TDD 준수**: 모든 모듈 테스트 선행으로 구현 전 설계 오류 조기 발견 가능 (Gap-1, 2, 3 모두 분석 단계에서 적중).

### Areas for Improvement (📝)

1. **Trigger 모니터링 (운영 전제)**: 외부 cron이 정지해도 앱은 알 수 없음. 향후 상태 엔드포인트(`GET /internal/schedules/trigger/status`, in-memory) 활용한 외부 모니터링 dashboard 구성 필수.
2. **실패 재시도 정책**: 현재는 다음 회차에 자연 재실행. 반복 실패 스케줄 자동 disable은 후속 검토.
3. **MySQL SKIP LOCKED 검증**: 단위 테스트는 sqlite(미지원)이므로 통합 테스트 마킹만 함. 배포 환경에서 실제 동시성 검증 필요.
4. **프론트 UI**: CRUD API는 완성이지만 사용자 관점 스케줄 관리 UI(`agent-schedule-ui` feature) 필수.

### To Apply Next Time (🔄)

1. **외부 트리거 기반 기능**: 트리거 인증(`X-Scheduler-Token`), claim 동시성 패턴, 짧은 트랜잭션 회차화 → 유사 기능(배치 작업, 주기 보고 등)에 재사용 가능한 모듈로 일반화 검토.
2. **다값 VO 치환**: `render_instruction`의 다중 플레이스홀더 패턴(constant loop) → 문자열 템플릿 기능 있는 코드에 템플릿 엔진 도입 시 참고.
3. **포크 회귀 테스트**: 이번 `test_fork_excludes_schedules` 패턴 → 향후 에이전트 포크 기능 추가 시 항상 "데이터 분리" 회귀 테스트 고정.

---

## 다음 단계 / 운영 체크리스트

### 즉시 (배포 전)

- [ ] `.env.example` 문서 정독: `SCHEDULER_TRIGGER_TOKEN` 설정 예시 확인
- [ ] 외부 cron/작업 스케줄러 등록 절차 작성 및 배포 체크리스트에 추가

```bash
# 예: Linux crontab (매 분)
* * * * * curl -s -X POST http://localhost:8000/api/v1/internal/schedules/trigger \
    -H "X-Scheduler-Token: ${SCHEDULER_TRIGGER_TOKEN}"

# Windows 작업 스케줄러: PowerShell 스크립트로 동일 curl 1분 주기 등록
```

### 단기 (1~2주)

- [ ] 프론트엔드 UI feature: `agent-schedule-ui` 시작
  - CRUD 엔드포인트: `/api/v1/agents/{agent_id}/schedules` 등
  - 요청/응답 스키마: Design §5.3 참조 → `/api-contract-sync` 스킬로 타입 동기화
  - 스케줄 생성/수정 폼: spec(once/daily/weekly/cron), instruction(플레이스홀더 가이드), timezone, enabled
  - 실행 이력 조회: `/api/v1/agents/{agent_id}/schedules/{schedule_id}/runs`

### 중기 (1~3개월)

- [ ] MySQL SKIP LOCKED 통합 테스트 마킹 회피 → 실제 MySQL 환경에서 동시 트리거 검증
- [ ] Trigger 상태 모니터링 dashboard 구성: 마지막 트리거 시각, 성공/실패 카운트 추적
- [ ] 반복 실패 스케줄 자동 disable 정책 검토 및 구현

### 장기 (추후)

- [ ] 인프로세스 스케줄러 전환 검토: APScheduler/Celery 도입 시 TriggerDueSchedulesUseCase 인터페이스 유지 가능
- [ ] ScheduleRunSink 구현체 확장: 알림(이메일/Slack/푸시), 외부 시스템 연동(Zapier 등)
- [ ] DST/타임존 경계 특수 처리 검토 (현재 Asia/Seoul은 DST 없음, 후속 글로벌 대응 시)

---

## 결론

**agent-schedule 기능이 정상 완성되었습니다** ✅

- **Match Rate 98%** (설계-구현 정합도)
- **테스트 111개 전부 통과**
- **PDCA 검증 3종 (architecture/logging/tdd) 모두 PASS**
- **기존 코드 최소 수정** (main.py DI + config.py 설정값)
- **포크 미복사 구조 + 외부 트리거 방식 = 운영 안정성 확보**

이제 프론트엔드 UI 구현(`agent-schedule-ui`)과 배포 준비(외부 cron 등록)를 진행하면 사용자가 스케줄 기능을 온전히 활용할 수 있습니다.
