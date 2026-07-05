# agent-schedule API

> 에이전트 스케줄 기능 — 에이전트별 스케줄(once/daily/weekly/cron) CRUD 및 외부 스케줄러 트리거 기반 실행 엔진.

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1` |
| Auth | CRUD: JWT Bearer (`get_current_user`) / 트리거: `X-Scheduler-Token` 헤더 (`settings.scheduler_trigger_token`) |

- 스케줄은 에이전트 소유자만 생성/조회/수정/삭제 가능 (타인 접근 시 403).
- 에이전트당 스케줄 최대 **10개**, 지침(instruction) 최대 **1,900자**, cron 최소 간격 **10분**.
- 지침에는 시점 변수 플레이스홀더 사용 가능: `{today}`(YYYY-MM-DD), `{now}`(HH:MM), `{weekday}`(월~일) — 실행 시점에 스케줄 타임존 기준으로 치환되어 실제 사용자 질문(query)으로 전송된다.
- 저장/응답의 모든 datetime은 **UTC** 기준 ISO8601 문자열. `timezone` 필드(IANA, 기본 `Asia/Seoul`)는 스케줄 계산에만 사용.
- 트리거 엔드포인트는 외부 스케줄러(OS cron / Windows 작업 스케줄러 / k8s CronJob)가 매 분 호출하는 내부용 API.

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/agents/{agent_id}/schedules` | 스케줄 생성 |
| GET | `/agents/{agent_id}/schedules` | 스케줄 목록 조회 |
| GET | `/agents/{agent_id}/schedules/{schedule_id}` | 스케줄 단건 조회 |
| PUT | `/agents/{agent_id}/schedules/{schedule_id}` | 스케줄 수정 |
| DELETE | `/agents/{agent_id}/schedules/{schedule_id}` | 스케줄 삭제 |
| PATCH | `/agents/{agent_id}/schedules/{schedule_id}/enabled` | 스케줄 활성/비활성 토글 |
| GET | `/agents/{agent_id}/schedules/{schedule_id}/runs` | 스케줄 실행 이력 조회 |
| POST | `/internal/schedules/trigger` | due 스케줄 일괄 실행 (외부 스케줄러 전용) |
| GET | `/internal/schedules/trigger/status` | 마지막 트리거 시각/결과 조회 |

---

## 공통 스키마

### ScheduleSpecPayload

| 필드 | 타입 | 설명 |
|------|------|------|
| `schedule_type` | `"once" \| "daily" \| "weekly" \| "cron"` | 반복 유형 |
| `run_date` | `string(date) \| null` | `once` 전용 (필수), 미래 날짜 |
| `time_of_day` | `string("HH:MM") \| null` | `once`/`daily`/`weekly` 필수 |
| `days_of_week` | `int[] \| null` | `weekly` 전용 (필수), 0=월 .. 6=일, 1~7개, 중복 불가 |
| `cron_expr` | `string \| null` | `cron` 전용 (필수), 연속 발화 간격 10분 이상 |

유형별로 해당 필드 외의 값이 오면 400.

### ScheduleResponse

```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "name": "일일 뉴스 요약",
  "spec": {
    "schedule_type": "daily",
    "run_date": null,
    "time_of_day": "09:00",
    "days_of_week": null,
    "cron_expr": null
  },
  "instruction": "{today} 기준 주요 금융 뉴스를 요약해줘",
  "enabled": true,
  "timezone": "Asia/Seoul",
  "next_run_at": "2026-07-03T00:00:00Z",
  "last_run_at": null,
  "created_at": "2026-07-02T05:00:00Z",
  "updated_at": "2026-07-02T05:00:00Z"
}
```

---

## 상세 스펙

### POST /agents/{agent_id}/schedules

스케줄을 생성한다. 대상 에이전트의 소유자만 가능하며, 생성 시 `next_run_at`이 즉시 계산된다.

**Request**
```json
{
  "name": "일일 뉴스 요약",
  "spec": {
    "schedule_type": "daily",
    "time_of_day": "09:00"
  },
  "instruction": "{today} 기준 주요 금융 뉴스를 요약해줘",
  "timezone": "Asia/Seoul",
  "enabled": true
}
```

| 필드 | 제약 |
|------|------|
| `name` | 필수, 1~200자 |
| `spec` | 필수, ScheduleSpecPayload |
| `instruction` | 필수, 1~1,900자 |
| `timezone` | 기본 `"Asia/Seoul"`, IANA 형식 |
| `enabled` | 기본 `true` |

**Response** — `201 Created`
```json
{ "...": "ScheduleResponse" }
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 400 | spec 필드 조합 오류 / cron 형식 오류 / cron 간격 10분 미만 / 과거 once / 잘못된 timezone / 에이전트당 10개 초과 |
| 403 | 에이전트 소유자가 아님 |
| 404 | 에이전트 미존재 |

---

### GET /agents/{agent_id}/schedules

에이전트의 스케줄 목록을 조회한다.

**Request** — 본문 없음

**Response** — `200 OK`
```json
[
  { "...": "ScheduleResponse" }
]
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | 에이전트 소유자가 아님 |
| 404 | 에이전트 미존재 |

---

### GET /agents/{agent_id}/schedules/{schedule_id}

스케줄 단건을 조회한다. 경로의 `agent_id`와 스케줄의 `agent_id`가 일치해야 한다.

**Request** — 본문 없음

**Response** — `200 OK`
```json
{ "...": "ScheduleResponse" }
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | 스케줄 소유자가 아님 |
| 404 | 스케줄 미존재 / agent_id 경로 불일치 |

---

### PUT /agents/{agent_id}/schedules/{schedule_id}

스케줄을 수정한다. `spec` 또는 `timezone`이 변경되면 `next_run_at`이 재계산된다.

**Request** — POST 생성 요청과 동일 스키마
```json
{
  "name": "일일 뉴스 요약 (오후)",
  "spec": {
    "schedule_type": "daily",
    "time_of_day": "18:00"
  },
  "instruction": "{today} 기준 주요 금융 뉴스를 요약해줘",
  "timezone": "Asia/Seoul",
  "enabled": true
}
```

**Response** — `200 OK`
```json
{ "...": "ScheduleResponse" }
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 400 | spec/instruction/timezone 검증 실패 |
| 403 | 스케줄 소유자가 아님 |
| 404 | 스케줄 미존재 |

---

### DELETE /agents/{agent_id}/schedules/{schedule_id}

스케줄을 삭제한다. 실행 이력(`agent_schedule_run`)도 CASCADE 삭제된다.

**Request** — 본문 없음

**Response** — `204 No Content`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | 스케줄 소유자가 아님 |
| 404 | 스케줄 미존재 |

---

### PATCH /agents/{agent_id}/schedules/{schedule_id}/enabled

스케줄 활성 여부를 토글한다. off→on 시 `next_run_at = compute_next_run(after=now)`로 재계산되어 과거 시각 기준 즉시 폭발 실행을 방지한다. on→off 시 `next_run_at`은 유지된다.

**Request**
```json
{ "enabled": true }
```

**Response** — `200 OK`
```json
{ "...": "ScheduleResponse" }
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | 스케줄 소유자가 아님 |
| 404 | 스케줄 미존재 |

---

### GET /agents/{agent_id}/schedules/{schedule_id}/runs

스케줄 실행 이력을 최신순으로 조회한다.

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 제약 |
|----------|------|--------|------|
| `limit` | int | - | 최대 100 |
| `offset` | int | 0 | - |

**Response** — `200 OK`
```json
[
  {
    "id": "uuid",
    "schedule_id": "uuid",
    "status": "success",
    "scheduled_for": "2026-07-03T00:00:00Z",
    "started_at": "2026-07-03T00:00:01Z",
    "finished_at": "2026-07-03T00:00:14Z",
    "session_id": "uuid",
    "run_id": "uuid",
    "error_message": null
  }
]
```

`status`: `running` | `success` | `failed`. 성공 시 `session_id`/`run_id`로 생성된 대화 세션과 ai_run 추적 가능, 실패 시 `error_message`에 사유 기록.

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | 스케줄 소유자가 아님 |
| 404 | 스케줄 미존재 |

---

### POST /internal/schedules/trigger

due 상태(`enabled=true` AND `next_run_at <= now`)인 스케줄을 클레임하여 순차 실행한다. 외부 스케줄러가 매 분 호출하는 내부 엔드포인트로, `FOR UPDATE SKIP LOCKED` 클레임 방식이라 트리거 호출이 겹쳐도 동일 회차가 중복 실행되지 않는다.

각 스케줄은 지침의 시점 변수를 치환한 뒤 `RunAgentUseCase`로 실행되며, 새 대화 세션이 자동 생성되고 치환된 지침이 user 메시지로 저장된다. 개별 실행 실패는 이력에 `failed`로 기록되고 나머지 스케줄은 계속 처리된다.

**Request**

| 헤더 | 설명 |
|------|------|
| `X-Scheduler-Token` | `settings.scheduler_trigger_token`과 일치해야 함 |

본문 없음.

**Response** — `200 OK`
```json
{
  "claimed": 3,
  "success": 2,
  "failed": 1,
  "request_id": "uuid"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 토큰 누락 또는 불일치 |
| 503 | `scheduler_trigger_token` 미설정 (트리거 기능 비활성) |

**외부 스케줄러 등록 예시**
```bash
# 리눅스 crontab (매 분)
* * * * * curl -s -X POST http://localhost:8000/api/v1/internal/schedules/trigger \
    -H "X-Scheduler-Token: ${SCHEDULER_TRIGGER_TOKEN}"
```

---

### GET /internal/schedules/trigger/status

마지막 트리거 실행 시각/결과를 조회한다 (in-memory, 외부 cron 정지 감지용).

**Request**

| 헤더 | 설명 |
|------|------|
| `X-Scheduler-Token` | 트리거와 동일 토큰 |

**Response** — `200 OK`
```json
{
  "last_triggered_at": "2026-07-03T00:01:00Z",
  "claimed": 3,
  "success": 2,
  "failed": 1
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 토큰 누락 또는 불일치 |
| 503 | `scheduler_trigger_token` 미설정 |
