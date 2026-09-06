# jobs-page-revamp Design Document

> **Summary**: 작업함을 통합 이력 테이블로 개편하고, 수동 job의 soft delete·정리·필터·페이지네이션을 UNION 기반 단일 조회로 제공한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-09-03
> **Status**: Draft
> **Planning Doc**: [jobs-page-revamp.plan.md](../../01-plan/features/jobs-page-revamp.plan.md)

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

### 1.1 Design Goals

- 서로 다른 두 테이블(`agent_background_job`, `agent_schedule_run`)을 **DB에서** 하나의 시간순 목록으로 정렬·페이징·집계한다.
- soft delete를 도입하되, **필터 누락으로 삭제 행이 되살아나는 사고를 구조적으로 막는다.**
- 기존 워커 루프·스케줄 트리거 계약은 건드리지 않는다 (additive only).

### 1.2 Design Principles

- **단일 진실 쿼리**: 통합 목록의 정렬·페이징·카운트는 전부 DB가 계산한다. 클라이언트는 렌더링만 한다.
- **삭제는 기본 제외**: 조회 헬퍼에 `deleted_at IS NULL`을 내장해, 새 쿼리를 짜도 자동으로 적용되게 한다.
- **정규화 경계는 repository**: 두 테이블의 컬럼 차이는 repository에서 흡수하고, 위 레이어는 단일 DTO만 본다.
- **진행중 작업 불가침**: 워커가 소유한 상태(queued/running)는 사용자 조작으로 바뀌지 않는다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: 프론트 병합 | Option B: 통합 Read Model 신설 | Option C: 기존 모듈 내 UNION |
|----------|:-:|:-:|:-:|
| **Approach** | 기존 2개 API 호출 후 클라이언트 병합 | `domain/job_history/` 신설 | `BackgroundJobRepository`에 `union_all` 조회 추가 |
| **New Files** | 0 (BE) | 6~7 | 2 |
| **Modified Files** | 5 | 8 | 8 |
| **페이지네이션 정확도** | ❌ 부정확 | ✅ | ✅ |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | High (UX 결함 확정) | Low | Low |

**Selected**: **Option C** — **Rationale**: 페이지네이션·`total`을 DB에서 정확히 계산하면서, 이력 소스가 아직 2개뿐인 현 시점에 별도 도메인 모듈을 신설하는 과잉 추상화(CLAUDE.md §6 "두꺼운 DDD 금지")를 피한다. 소스가 3개 이상으로 늘면 Option B로 승격한다.

### 2.1 Component Diagram

```
┌──────────────────────┐      ┌───────────────────────────┐      ┌──────────────────────┐
│ JobsPage             │      │ background_job_router     │      │ MySQL                │
│  ├ 작업 기록 탭      │─────▶│  GET    /jobs             │─────▶│ agent_background_job │
│  │   필터·표·페이징  │      │  DELETE /jobs/{id}        │      │   (+ deleted_at)     │
│  └ 스케줄 작업 탭    │      │  POST   /jobs/cleanup     │      │ agent_schedule_run   │
│                      │      │  GET    /agents/{id}/     │      │ agent_schedule       │
│  NotificationBell    │─────▶│         schedules (기존)  │      │ agent_definition     │
└──────────────────────┘      └───────────────────────────┘      └──────────────────────┘
                                          │
                                          ▼
                              ListJobHistoryUseCase
                              DeleteJobUseCase / CleanupJobsUseCase
                                          │
                                          ▼
                              BackgroundJobRepository
                                (union_all 정규화 + deleted_at 필터)
```

### 2.2 Data Flow

```
[목록]  필터 선택 → GET /jobs?status&type&period&limit&offset
        → UseCase가 KST 경계를 UTC로 환산
        → Repository: job 서브쿼리 ∪ schedule_run 서브쿼리 → occurred_at DESC → LIMIT/OFFSET
        → 같은 조건으로 COUNT(*) → {items, total}

[삭제]  휴지통 클릭 → 확인 → DELETE /jobs/{id}
        → 소유·상태 검증(진행중이면 409) → deleted_at = now
        → 프론트: jobs + unseenCount 쿼리 무효화

[정리]  정리 클릭 → 확인 → POST /jobs/cleanup
        → 본인 소유 + status IN (success, failed) + deleted_at IS NULL → 일괄 UPDATE
        → {deleted: N} → 토스트 + 목록 무효화
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `ListJobHistoryUseCase` | `BackgroundJobRepositoryInterface` | 통합 목록·총건수 조회 |
| `DeleteJobUseCase` / `CleanupJobsUseCase` | 동 interface, `JobDeletionPolicy` | 소유·상태 검증 후 soft delete |
| `BackgroundJobRepository` | `AgentBackgroundJobModel`, `AgentScheduleRunModel`, `AgentScheduleModel`, `AgentDefinitionModel` | UNION 정규화 + 소유자 조인 |
| `JobsPage` | `useJobHistory`, `useDeleteJob`, `useCleanupJobs`, `useAgentSchedules` | 화면 구성 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# domain/background_job/entity.py — 기존 BackgroundJob 에 필드 1개 추가
@dataclass
class BackgroundJob:
    ...
    deleted_at: datetime | None   # NULL=활성, 값 있으면 목록/집계에서 제외 (soft delete)


# domain/background_job/entity.py — 통합 이력 항목 (신규, 읽기 전용 뷰 모델)
JobHistoryType = Literal["manual", "schedule"]

@dataclass(frozen=True)
class JobHistoryItem:
    id: str                       # job.id 또는 schedule_run.id
    type: JobHistoryType          # manual | schedule
    occurred_at: datetime         # job=queued_at, schedule=scheduled_for (정렬 기준, UTC naive)
    title: str                    # job=query, schedule=schedule_name
    status: JobStatus             # queued|running|success|failed 로 정규화
    agent_id: str
    agent_name: str | None
    session_id: str | None
    error_message: str | None
    seen_at: datetime | None      # schedule 행은 항상 None
    started_at: datetime | None
    finished_at: datetime | None
    deletable: bool               # manual=True, schedule=False (FR-11 휴지통 노출 기준)
```

`agent_schedule_run.status` 는 `running|success|failed` 로 job 상태의 부분집합이므로 **정규화 시 변환이 필요 없다** (queued 상태는 스케줄 실행에 존재하지 않음).

### 3.2 Entity Relationships

```
[User] 1 ── N [agent_background_job]  (user_id 직접 소유)
                     └── deleted_at (soft delete 대상)

[User] 1 ── N [agent_schedule] 1 ── N [agent_schedule_run]   (소유자는 schedule 경유)
                                          └── 삭제 없음 (스케줄 삭제 시 CASCADE)

두 이력 → UNION ALL → JobHistoryItem (읽기 전용)
```

### 3.3 Database Schema

```sql
-- db/migration/V070__add_deleted_at_to_agent_background_job.sql
ALTER TABLE agent_background_job
  ADD COLUMN deleted_at DATETIME NULL
    COMMENT '소프트 삭제 시각 (NULL=활성, 값 있으면 목록·집계에서 제외)';

-- 목록/집계가 항상 (user_id, deleted_at) 로 좁힌 뒤 queued_at 으로 정렬하므로 복합 인덱스
CREATE INDEX ix_agent_background_job_user_deleted_queued
  ON agent_background_job (user_id, deleted_at, queued_at);
```

> DDL COMMENT 규칙(V054+): 컬럼 COMMENT 필수, SQLAlchemy 모델에도 `comment=` 동일 반영.
> `tests/db/test_migration_ddl_comments.py` 가 검사한다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth | 변경 |
|--------|------|-------------|------|------|
| GET | `/api/v1/jobs` | 통합 작업 이력 목록 | JWT | **변경** (응답·파라미터) |
| DELETE | `/api/v1/jobs/{job_id}` | 수동 job soft delete | JWT | **신규** |
| POST | `/api/v1/jobs/cleanup` | 완료 job 일괄 soft delete | JWT | **신규** |
| GET | `/api/v1/jobs/{job_id}` | 단건 조회 | JWT | 유지 (삭제 행 404) |
| GET | `/api/v1/jobs/unseen-count` | 미확인 수 | JWT | 유지 (삭제 행 제외) |
| POST | `/api/v1/jobs/seen-all`, `/jobs/{id}/seen` | 확인 처리 | JWT | 유지 (삭제 행 제외) |
| GET | `/api/v1/schedules` | 내 스케줄 정의 전체 | JWT | **신규** (v0.2 — module-5) |
| GET | `/api/v1/schedule-runs` | 내 스케줄 실행 이력 | JWT | **유지** (통합 목록으로 대체되나 계약 보존, 클라이언트는 사용 안 함) |
| GET/PUT/PATCH/DELETE | `/api/v1/agents/{id}/schedules*` | 스케줄 정의 CRUD | JWT | 무변경 (탭에서 재사용) |

> **경로 선언 순서 (D14 계약)**: 리터럴 경로 `/jobs/unseen-count`, `/jobs/seen-all`, `/jobs/cleanup` 은 반드시 `/jobs/{job_id}` **보다 먼저** 선언한다. `cleanup` 이 `{job_id}` 로 먹히면 404가 난다.

### 4.2 Detailed Specification

#### `GET /api/v1/jobs`

**Query Parameters**

| Name | Type | Default | Values | 설명 |
|------|------|---------|--------|------|
| `status` | str | `all` | `all` \| `running` \| `done` | `running`=queued+running, `done`=success+failed |
| `type` | str | `all` | `all` \| `manual` \| `schedule` | 이력 소스 |
| `period` | str | `all` | `all` \| `1h` \| `today` \| `week` | KST 기준 |
| `limit` | int | 20 | 1~100 | |
| `offset` | int | 0 | ≥0 | |

**Response (200)**

```json
{
  "items": [
    {
      "id": "b3f0...",
      "type": "manual",
      "occurred_at": "2026-09-03T10:17:00",
      "title": "3분기 여신 정책 요약해줘",
      "status": "failed",
      "agent_id": "630b99b4-...",
      "agent_name": "여신정책 도우미",
      "session_id": null,
      "error_message": "도구 호출에 실패했습니다",
      "seen_at": null,
      "started_at": "2026-09-03T10:17:02",
      "finished_at": "2026-09-03T10:17:44",
      "deletable": true
    }
  ],
  "total": 1
}
```

- 정렬: `occurred_at DESC` (job=`queued_at`, schedule=`scheduled_for`)
- 동점 처리: `occurred_at DESC, id ASC` — 페이지 경계에서 순서가 흔들리지 않도록 보조 키를 반드시 넣는다.

#### `DELETE /api/v1/jobs/{job_id}`

- **204 No Content** — soft delete 성공
- **404** — 없음 / 타인 소유 (사유 비구분, 기존 정책 유지)
- **409 Conflict** — `queued` 또는 `running` 상태 (FR-04). detail: `"진행 중인 작업은 삭제할 수 없습니다"`
- 멱등: 이미 삭제된 행은 404 (목록에서 사라진 자원이므로)

#### `POST /api/v1/jobs/cleanup`

**Request**: body 없음

**Response (200)**

```json
{ "deleted": 12 }
```

- 대상: `user_id = me AND status IN ('success','failed') AND deleted_at IS NULL`
- 스케줄 실행 이력은 대상 아님. 대상 0건이면 `{"deleted": 0}` + 200

#### `GET /api/v1/schedules` (v0.2 추가)

내 스케줄 **정의** 전체 — 작업함 '스케줄 작업' 탭 (FR-15).

기존 스케줄 CRUD 는 `/api/v1/agents/{agent_id}/schedules` 로 **에이전트별**이라
에이전트를 가로지르는 목록을 만들 수 없다(N+1 없이는). 그래서 조회 전용
엔드포인트를 신설한다. 생성·수정·토글·삭제는 기존 경로를 그대로 쓴다.

**Response (200)**

```json
[
  {
    "id": "s1",
    "agent_id": "a1",
    "agent_name": "여신정책 도우미",
    "name": "아침 요약",
    "spec": { "schedule_type": "daily", "time_of_day": "09:00" },
    "instruction": "오늘 뉴스 요약해줘",
    "enabled": true,
    "timezone": "Asia/Seoul",
    "next_run_at": "2026-09-05T00:00:00",
    "last_run_at": null
  }
]
```

- 소유자 판정은 `agent_schedule.user_id` (실행 이력과 달리 스케줄 정의에 직접 있다)
- `agent_name` 은 표시용 outerjoin — 에이전트가 삭제돼도 행은 남는다
- 관리 경로(`/agents/{agent_id}/schedules/...`)를 클라이언트가 조립할 수 있도록 `agent_id` 를 함께 내린다
- **배치**: `background_job_router` (prefix `/api/v1`). `/schedule-runs` 가 이미 같은
  탭을 위해 거기 있으므로 짝을 맞춘다 — `agent_schedule_router` 는 prefix 가
  `/api/v1/agents` 라 이 경로를 담을 수 없다

### 4.3 통합 조회 쿼리 설계 (Option C 핵심)

```python
# infrastructure/background_job/job_repository.py

_JOB_COLS = select(
    AgentBackgroundJobModel.id.label("id"),
    literal("manual").label("type"),
    AgentBackgroundJobModel.queued_at.label("occurred_at"),
    AgentBackgroundJobModel.query.label("title"),
    AgentBackgroundJobModel.status.label("status"),
    ...
).outerjoin(AgentDefinitionModel, ...).where(
    AgentBackgroundJobModel.user_id == user_id,
    AgentBackgroundJobModel.deleted_at.is_(None),   # ← 필수
)

_RUN_COLS = select(
    AgentScheduleRunModel.id,
    literal("schedule"),
    AgentScheduleRunModel.scheduled_for,
    AgentScheduleModel.name,
    AgentScheduleRunModel.status,
    ...
).join(AgentScheduleModel, ...).outerjoin(AgentDefinitionModel, ...).where(
    AgentScheduleModel.user_id == user_id,
)

union_stmt = _JOB_COLS.union_all(_RUN_COLS).subquery()
# type 필터가 manual/schedule 단일값이면 union 없이 해당 서브쿼리만 사용 (쿼리 단순화)
```

- **컬럼 개수·타입·순서가 두 서브쿼리에서 정확히 일치**해야 한다 (`literal(None)` 로 자리 채움).
- 총건수는 `select(func.count()).select_from(union_stmt)` 로 같은 조건 재사용.
- `title` 은 `query`(TEXT)와 `name`(VARCHAR(200)) 이 섞이므로 UNION 타입 일치를 위해 양쪽 모두 문자열로 캐스팅한다.

### 4.4 KST 기간 경계 계산

```python
# application/background_job/period.py (신규)
KST = timezone(timedelta(hours=9))

def period_to_utc_start(period: str, now_utc: datetime) -> datetime | None:
    """period → UTC naive 하한. 'all' 이면 None (필터 없음)."""
    if period == "all":
        return None
    now_kst = now_utc.replace(tzinfo=timezone.utc).astimezone(KST)
    if period == "1h":
        start_kst = now_kst - timedelta(hours=1)
    elif period == "today":
        start_kst = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # week — 월요일 00:00 KST
        monday = now_kst - timedelta(days=now_kst.weekday())
        start_kst = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_kst.astimezone(timezone.utc).replace(tzinfo=None)
```

DB는 UTC naive 저장이므로 비교 직전에 tzinfo를 제거한다 (기존 `agent_schedule` 관례 동일).

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌───────────────────────────────────────────────────────────────────────────┐
│ 백그라운드 작업                                    [🗑 정리] [⟳ 새로고침]  │
│ 백그라운드 작업을 모니터링하고 관리하세요                                 │
├───────────────────────────────────────────────────────────────────────────┤
│ [작업 기록] [스케줄 작업]                                                 │
├───────────────────────────────────────────────────────────────────────────┤
│ [전체][진행중][완료됨]      [전체][수동][스케줄]     [전체][1시간][오늘][이번 주] │
├──────────────┬──────────────────────┬──────────┬──────────────┬───────────┤
│ 시간         │ 제목                 │ 상태     │ 에이전트     │           │
├──────────────┼──────────────────────┼──────────┼──────────────┼───────────┤
│ 2026-09-03…  │ 3분기 여신 정책 요약 │ ⊗ 실패   │ 630b99b4     │    🗑     │
│ 2026-09-03…  │ 일일 리포트          │ ✓ 완료   │ 여신 도우미  │    (없음) │
└──────────────┴──────────────────────┴──────────┴──────────────┴───────────┘
                          [‹]  1 / 3 페이지  [›]
```

### 5.2 User Flow

```
네비바 "작업" → /jobs
  ├ 작업 기록 탭 (기본)
  │   ├ 필터 클릭 → offset=0 리셋 → 재조회
  │   ├ 행 클릭 → (성공·세션 있음) 채팅 세션으로 이동 + 미확인이면 seen 처리
  │   ├ 🗑 클릭 → 확인 다이얼로그 → DELETE → 목록·배지 갱신
  │   └ 정리 클릭 → "완료된 작업 N건을 정리할까요?" → POST cleanup → 토스트
  └ 스케줄 작업 탭 → 스케줄 정의 목록 → 활성 토글 / 삭제(기존 API)
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `JobsPage` | `pages/JobsPage/index.tsx` | 탭·헤더 액션·상태 보유 |
| `JobHistoryTable` | `pages/JobsPage/JobHistoryTable.tsx` | 테이블 렌더 + 행 클릭/삭제 위임 |
| `JobFilterBar` | `pages/JobsPage/JobFilterBar.tsx` | 상태·유형·기간 3단 필터 |
| `JobPagination` | `pages/JobsPage/JobPagination.tsx` | `N / M 페이지` + 이전/다음 |
| `ScheduleDefinitionTable` | `pages/JobsPage/ScheduleDefinitionTable.tsx` | 스케줄 정의 목록·활성 토글 |
| `StatusBadge` | `pages/JobsPage/StatusBadge.tsx` | 기존 배지 추출 (재사용) |

> 상수(`STATUS_LABEL`, 필터 옵션)는 컴포넌트 파일에서 export 금지 — `src/types/backgroundJob.ts` 에 `as const` 로 둔다.

### 5.4 Page UI Checklist

#### 작업 기록 탭

- [ ] Filter: 상태 3버튼 (`전체` / `진행중` / `완료됨`) — 선택 시 검은 배경 강조
- [ ] Filter: 유형 3버튼 (`전체` / `수동` / `스케줄`)
- [ ] Filter: 기간 4버튼 (`전체` / `1시간` / `오늘` / `이번 주`)
- [ ] Table header: `시간` / `제목` / `상태` / `에이전트` 4열 + 액션 열(헤더 텍스트 없음)
- [ ] Cell: 시간 — `YYYY-MM-DD HH:mm` (KST 표기)
- [ ] Cell: 제목 — 1줄 말줄임, 수동=query / 스케줄=스케줄명
- [ ] Cell: 상태 — 배지 4종 (대기 중/실행 중=스피너, 완료=초록, 실패=빨강 ⊗)
- [ ] Cell: 에이전트 — `agent_name`, 없으면 `agent_id` 앞 8자
- [ ] Button: 행별 휴지통 — **`deletable === true` 인 행에만 렌더**
- [ ] Button: 헤더 `정리` (보라 강조) — 확인 다이얼로그 경유
- [ ] Button: 헤더 `새로고침` — 목록 + 미확인 수 재조회
- [ ] Pagination: `현재 / 전체 페이지` 표시 + 이전/다음 (경계에서 disabled)
- [ ] Empty: 필터 결과 0건 — "조건에 맞는 작업이 없습니다"
- [ ] Row: 실패 행의 `error_message` 노출 (툴팁 또는 하단 보조 텍스트)

#### 스케줄 작업 탭

- [ ] Table: 스케줄명 / 주기 / 다음 실행 / 에이전트 / 활성
- [ ] Toggle: 활성/비활성 (`PATCH /agents/{id}/schedules/{sid}/enabled`)
- [ ] Button: 스케줄 삭제 (`DELETE /agents/{id}/schedules/{sid}`) — 확인 경유
- [ ] Empty: "등록된 스케줄이 없습니다"

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | 상황 | 처리 |
|------|------|------|
| 400 | `status`/`type`/`period` 가 허용값 밖 | FastAPI `pattern` 검증 → 422/400, 프론트는 버튼 UI라 발생하지 않음 |
| 401 | 미인증 | 기존 인터셉터가 로그인으로 이동 |
| 404 | 없음 / 타인 소유 / 이미 삭제됨 | "작업을 찾을 수 없습니다" 토스트 + 목록 갱신 |
| 409 | 진행중 작업 삭제 시도 | "진행 중인 작업은 삭제할 수 없습니다" 토스트, 목록 유지 |
| 500 | 서버 오류 | 스택 트레이스 포함 로깅(LOG-001), 사용자에겐 일반 메시지 |

### 6.2 Error Response Format

기존 계약 유지 — FastAPI `HTTPException(detail=...)`. 프론트는 `extractJobError()` 로 `detail` 추출.

---

## 7. Security Considerations

- [x] 모든 job 경로에서 `user_id` 일치 검증 — 타인 자원은 **404**(존재 여부 노출 금지, 기존 D-정책 승계)
- [x] 스케줄 실행 이력의 소유자는 `agent_schedule.user_id` 경유 조인으로만 판정 (`agent_schedule_run` 에는 user_id 없음)
- [x] cleanup은 항상 `user_id = 본인` 조건 포함 — 전역 UPDATE 금지
- [x] soft delete는 데이터 파기가 아니므로 감사 추적(`run_id`) 유지
- [ ] Rate limiting: 이번 범위 밖 (기존 정책 승계)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0: Unit | KST 기간 경계, 상태 그룹 매핑, 삭제 가능 정책 | pytest | Do |
| L1: API | 6개 엔드포인트 — 상태코드·응답형태·인가 | pytest (httpx) | Do |
| L2: UI Action | 필터 전환·삭제 확인·페이지 이동 | Vitest + RTL + MSW | Do |
| L3: E2E | 등록 → 목록 확인 → 정리 | 수동 (Playwright 미도입) | Check |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Method | Test Description | Expected |
|---|----------|--------|-----------------|----------|
| 1 | `/api/v1/jobs` | GET | 기본 조회 | 200, `items` 배열 + `total` 정수 |
| 2 | `/api/v1/jobs?type=manual` | GET | 유형 필터 | 스케줄 행이 결과에 없음 |
| 3 | `/api/v1/jobs?type=schedule` | GET | 유형 필터 | 모든 항목 `deletable=false` |
| 4 | `/api/v1/jobs?status=running` | GET | 상태 그룹 | queued·running만, success 미포함 |
| 5 | `/api/v1/jobs?period=today` | GET | KST 오늘 경계 | 어제 23:59(KST) 항목 제외, 오늘 00:00 항목 포함 |
| 6 | `/api/v1/jobs?limit=2&offset=2` | GET | 페이징 | 3~4번째 항목, `total`은 전체 건수 유지 |
| 7 | `/api/v1/jobs` | GET | 정렬 | 두 소스가 `occurred_at DESC` 로 섞여 정렬됨 |
| 8 | `/api/v1/jobs/{id}` | DELETE | 완료 job 삭제 | 204, 이후 목록·`total`에서 제외 |
| 9 | `/api/v1/jobs/{id}` | DELETE | 진행중 job 삭제 | 409 |
| 10 | `/api/v1/jobs/{id}` | DELETE | 타인 job 삭제 | 404 |
| 11 | `/api/v1/jobs/{id}` | DELETE | 이미 삭제된 job | 404 |
| 12 | `/api/v1/jobs/cleanup` | POST | 완료 3건 + 진행중 1건 | `{deleted: 3}`, 진행중 잔존 |
| 13 | `/api/v1/jobs/cleanup` | POST | 대상 0건 | 200, `{deleted: 0}` |
| 14 | `/api/v1/jobs/unseen-count` | GET | 삭제 후 집계 | 삭제한 미확인 job이 카운트에서 빠짐 |
| 15 | `/api/v1/jobs/{id}` | GET | 삭제된 job 단건 | 404 |
| 16 | `/api/v1/jobs/seen-all` | POST | 삭제 행 제외 | 삭제된 미확인 job은 `updated` 에 미포함 |
| 17 | 전 엔드포인트 | - | 미인증 | 401 |

> **#14~16은 회귀 방지의 핵심** — `deleted_at` 필터 누락 사고를 잡는 테스트다.

### 8.3 L2: UI Action Test Scenarios

| # | Page | Action | Expected Result |
|---|------|--------|----------------|
| 1 | 작업 기록 | 페이지 로드 | §5.4 체크리스트 요소 전부 렌더, 4열 테이블 |
| 2 | 작업 기록 | `완료됨` 필터 클릭 | 재조회 발생, `status=done` 파라미터 전송, offset 0 리셋 |
| 3 | 작업 기록 | `스케줄` 필터 클릭 | 휴지통 아이콘이 하나도 렌더되지 않음 |
| 4 | 작업 기록 | 휴지통 클릭 → 확인 | DELETE 호출, 성공 시 행 사라짐 |
| 5 | 작업 기록 | 휴지통 클릭 → 취소 | DELETE 미호출 |
| 6 | 작업 기록 | 진행중 행 삭제 → 409 | 에러 토스트, 행 유지 |
| 7 | 작업 기록 | `정리` → 확인 | cleanup 호출, "N건 정리" 토스트 |
| 8 | 작업 기록 | 다음 페이지 | offset 증가, 마지막 페이지에서 `›` disabled |
| 9 | 작업 기록 | 결과 0건 | 빈 상태 문구 노출 |
| 10 | NotificationBell | 목록 응답이 `{items,total}` | 배지·드롭다운 정상 (계약 변경 회귀) |

### 8.4 Seed Data Requirements

| Entity | Minimum Count | Key Fields |
|--------|:---:|---|
| `agent_background_job` | 5 | success 2, failed 1, running 1, 타 사용자 1 |
| `agent_schedule` + `agent_schedule_run` | 2 | success 1, failed 1 (본인 소유) |
| `agent_definition` | 2 | 이름 있는 것 1, 삭제되어 없는 것 1 (`agent_name=None` 경로) |

---

## 9. Clean Architecture

### 9.1 Layer Structure (백엔드)

| Layer | 이 기능의 구성요소 | 위치 |
|-------|-----------------|------|
| **Domain** | `BackgroundJob(+deleted_at)`, `JobHistoryItem`, `JobDeletionPolicy`, repository 인터페이스 | `src/domain/background_job/` |
| **Application** | `ListJobHistoryUseCase`, `DeleteJobUseCase`, `CleanupJobsUseCase`, `period.py`, schemas | `src/application/background_job/` |
| **Infrastructure** | `AgentBackgroundJobModel(+deleted_at)`, `BackgroundJobRepository(union/soft delete)` | `src/infrastructure/background_job/` |
| **Interfaces** | `background_job_router.py` (DELETE·cleanup·확장 GET) | `src/api/routes/` |

### 9.2 Dependency Rules

- Domain은 SQLAlchemy를 모른다 — `JobHistoryItem` 은 순수 dataclass.
- UNION 쿼리는 Infrastructure에만 존재. UseCase는 `list_history(...)` / `count_history(...)` 만 호출.
- KST 경계 환산은 Application(`period.py`) — 정책성 계산이므로 라우터·리포지토리에 두지 않는다.
- Repository는 `commit()/rollback()` 을 호출하지 않는다 (DB-001). 삭제 트랜잭션 경계는 `get_session` 의존성이 소유.

### 9.3 This Feature's Layer Assignment (프론트)

| Component | Layer | Location |
|-----------|-------|----------|
| `JobsPage`, `JobHistoryTable`, `JobFilterBar`, `JobPagination` | Presentation | `src/pages/JobsPage/` |
| `useJobHistory`, `useDeleteJob`, `useCleanupJobs` | Application | `src/hooks/useBackgroundJobs.ts` |
| `JobHistoryItem`, `JobFilters`, 상수 | Domain | `src/types/backgroundJob.ts` |
| `backgroundJobService`, `API_ENDPOINTS` | Infrastructure | `src/services/`, `src/constants/api.ts` |

---

## 10. Coding Convention Reference

### 10.1 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| DDL | 테이블·전 컬럼 COMMENT, SQLAlchemy `comment=` 동반 (V054+) |
| 함수 길이 | 40줄 이내 — UNION 쿼리는 `_job_history_select()` / `_run_history_select()` 로 분리 |
| if 중첩 | 2단 이내 — 필터 조건은 리스트에 모아 `*conditions` 전개 |
| 로깅 | `logger.info/warning` + `request_id` 동반, `print()` 금지 |
| 프론트 상수 | 런타임 상수는 `src/types/backgroundJob.ts` 에 `as const` (컴포넌트 export 금지) |
| 쿼리 키 | `queryKeys.backgroundJobs.*` 확장, 필터 객체를 키에 포함해 조건별 캐시 분리 |

### 10.2 soft delete 규약 (프로젝트 신규)

> **규칙**: `agent_background_job` 을 읽는 모든 쿼리는 `deleted_at IS NULL` 을 포함한다.
> 예외는 삭제 자체를 다루는 쿼리뿐이다.

이를 구조로 강제하기 위해 repository 내부에 헬퍼를 둔다:

```python
def _active(*conditions):
    """활성 job 조건 — deleted_at 필터를 빠뜨릴 수 없게 감싼다."""
    return (AgentBackgroundJobModel.deleted_at.is_(None), *conditions)
```

적용 대상 메서드 (전수 점검 체크리스트):

| 메서드 | 필터 필요 | 비고 |
|--------|:---:|------|
| `find_by_id` | ✅ | 삭제 행은 404 |
| `find_active_by_session` | ✅ | 삭제된 job이 세션 중복 409를 유발하면 안 됨 |
| `list_history` (신규) | ✅ | |
| `count_history` (신규) | ✅ | |
| `count_unseen` | ✅ | 벨 배지 |
| `mark_seen` / `mark_all_seen` | ✅ | |
| `soft_delete` / `soft_delete_completed` (신규) | ✅ | 이미 삭제된 행 재삭제 방지 |
| `claim_queued` | ⛔ 불필요 | 진행중 job은 삭제 불가(409)라 삭제 행이 queued일 수 없음 |
| `finish` | ⛔ 불필요 | 워커가 소유한 전이 — 삭제 여부와 무관하게 종결 기록 |
| `reconcile_orphan_running` | ⛔ 불필요 | 동상 |
| `enqueue` | N/A | |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── db/migration/V070__add_deleted_at_to_agent_background_job.sql   [신규]
├── src/domain/background_job/
│   ├── entity.py                     [수정] deleted_at, JobHistoryItem
│   ├── interfaces.py                 [수정] list_history/count_history/soft_delete/soft_delete_completed
│   │                                        [제거] list_by_user — list_history 가 완전 대체 (v0.2)
│   └── policies.py                   [수정] JobDeletionPolicy (진행중 삭제 불가)
├── src/application/background_job/
│   ├── period.py                     [신규] KST 기간 경계
│   ├── query_use_cases.py            [수정] ListJobHistoryUseCase
│   │                                        [제거] ListJobsUseCase — 소비처 0 (v0.2)
│   ├── list_my_schedules_use_case.py [신규] 내 스케줄 정의 조회 (v0.2)
│   ├── delete_use_cases.py           [신규] Delete / Cleanup UseCase
│   ├── errors.py                     [수정] JobDeleteConflictError
│   └── schemas.py                    [수정] JobHistoryResponse, JobListResponse, CleanupResponse
├── src/infrastructure/background_job/
│   ├── models.py                     [수정] deleted_at
│   └── job_repository.py             [수정] UNION 조회 + soft delete + _active 헬퍼
├── src/api/routes/background_job_router.py  [수정] DELETE·cleanup·확장 GET·GET /schedules
├── src/infrastructure/agent_schedule/schedule_repository.py [수정] list_by_user (v0.2)
├── src/api/main.py                   [수정] DI 팩토리 2개 추가
└── tests/                            [신규/수정] api·application·db

idt_front/
├── src/types/backgroundJob.ts        [수정] JobHistoryItem, 필터 상수, JobListResponse
├── src/constants/api.ts              [수정] JOBS_CLEANUP
├── src/services/backgroundJobService.ts [수정] listHistory/remove/cleanup
├── src/hooks/useBackgroundJobs.ts    [수정] useJobHistory/useDeleteJob/useCleanupJobs, useJobList 언래핑
├── src/lib/queryKeys.ts              [수정] 필터 포함 키
├── src/pages/JobsPage/
│   ├── index.tsx                     [수정] 전면 개편
│   ├── JobFilterBar.tsx              [신규]
│   ├── JobHistoryTable.tsx           [신규]
│   ├── JobPagination.tsx             [신규]
│   ├── StatusBadge.tsx               [신규] 추출
│   └── ScheduleDefinitionTable.tsx   [신규]
└── src/components/layout/NotificationBell.tsx / .test.tsx [수정] 계약 변경 흡수
```

### 11.2 Implementation Order

1. [ ] V070 마이그레이션 + 모델 `deleted_at` + DDL COMMENT 테스트 통과
2. [ ] 도메인: `JobHistoryItem`, `JobDeletionPolicy`, repository 인터페이스 확장
3. [ ] `period.py` + 단위 테스트 (KST 경계값)
4. [ ] repository: `_active` 헬퍼 → 기존 메서드 전수 적용 → L1 #14~16 회귀 테스트 Green
5. [ ] repository: UNION `list_history` / `count_history`
6. [ ] UseCase 3종 + 라우터 (리터럴 경로 선언 순서 주의) + L1 테스트 전체
7. [ ] 프론트 타입·서비스·훅 (`useJobList` 언래핑 → NotificationBell 테스트 먼저 Green)
8. [ ] `JobFilterBar` / `JobHistoryTable` / `JobPagination` + 테스트
9. [ ] `JobsPage` 조립 + 스케줄 정의 탭
10. [ ] 스크린샷 대조 및 마감

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---:|
| 스키마 & soft delete 기반 | `module-1` | V070, 모델·엔티티·정책, `_active` 전수 적용, 회귀 테스트 (구현순서 1~4) | 25-30 |
| 통합 조회 & 삭제 API | `module-2` | UNION 조회, period, UseCase 3종, 라우터, DI, L1 테스트 (5~6) | 30-40 |
| 프론트 계약 동기화 | `module-3` | 타입·서비스·훅·queryKeys, NotificationBell 회귀 (7) | 20-25 |
| 작업 기록 탭 UI | `module-4` | 필터바·테이블·페이지네이션·삭제/정리 + 테스트 (8~9) | 35-45 |
| 스케줄 작업 탭 | `module-5` | 스케줄 정의 목록·토글·삭제 (9~10) | 15-20 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:---:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 55-70 |
| Session 3 | Do | `--scope module-3,module-4` | 55-70 |
| Session 4 | Do + Check | `--scope module-5` + 갭 분석 | 40-50 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-03 | 최초 작성 — Option C 선택, 상태 공통 4값 정규화 확정 | 배상규 |
| 0.2 | 2026-09-04 | Check 반영 — `GET /api/v1/schedules` 신규 명세(§4.1·§4.2), `list_by_user`/`ListJobsUseCase` 제거 기록(§11.1) | 배상규 |
