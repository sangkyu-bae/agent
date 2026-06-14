# fix-tracker-naive-aware-datetime Design Document

> **Summary**: MySQL `DATETIME` 컬럼에서 fetch된 naive datetime과 `_utcnow()` aware datetime의 빼기 연산으로 발생하는 `TypeError` 수정. Repository mapper에서 naive→UTC aware로 정규화하여 도메인 일관성 확보.
>
> **Project**: sangplusbot (idt)
> **Author**: AI Assistant
> **Date**: 2026-05-24
> **Status**: Draft
> **Planning Doc**: [fix-tracker-naive-aware-datetime.plan.md](../../01-plan/features/fix-tracker-naive-aware-datetime.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- `RunTracker.update_step`에서 `TypeError: can't subtract offset-naive and offset-aware datetimes` 제거
- 도메인 엔티티의 모든 `datetime` 필드가 **항상 timezone-aware (UTC)** 임을 인프라 레이어에서 보장
- API 응답에서도 ISO8601 'Z' 접미사가 정상 부착되도록 mapper 일관성 확보
- 기존 DB 데이터/스키마 변경 없이 코드 레벨만 수정 (마이그레이션 비용 0)

### 1.2 Design Principles

- **인프라 레이어 책임**: "MySQL `DATETIME` 컬럼은 UTC wall clock으로 저장한다"는 정책을 mapper에서 강제
- **DDD 레이어 규칙 준수**: domain entities는 그대로 두고, infrastructure mapper만 변경
- **다중 방어선(defense in depth)**: mapper 정규화 + tracker 비교 직전 가드 (mapper 우회 경로 대비)
- 최소 변경 원칙: ORM 컬럼 타입/마이그레이션은 건드리지 않음 (MySQL `DATETIME`은 tzinfo 미지원)

---

## 2. Architecture

### 2.1 현재 문제점 (Before)

```
record_step (aware UTC)             update_step
   │                                    │
   ▼                                    ▼
[ Domain Entity (aware) ]          [ ended_at = _utcnow() (aware) ]
   │                                    │
   ▼                                    ▼
[ ORM Model (DateTime, no tz) ]    [ find_steps() → fetch row ]
   │                                    │
   ▼                                    ▼
[ MySQL DATETIME (no tz) ]─────────►[ _step_to_domain (naive ⚠) ]
                                        │
                                        ▼
                                  target.ended_at - target.started_at
                                       (aware)       (naive)
                                        │
                                        ▼
                              TypeError ⛔ → WARNING log
                              latency_ms = NULL
```

### 2.2 수정 후 (After)

```
record_step (aware UTC)             update_step
   │                                    │
   ▼                                    ▼
[ Domain Entity (aware) ]          [ ended_at = _utcnow() (aware) ]
   │                                    │
   ▼                                    ▼
[ ORM Model (DateTime, no tz) ]    [ find_steps() → fetch row ]
   │                                    │
   ▼                                    ▼
[ MySQL DATETIME (no tz) ]─────────►[ _step_to_domain ]
                                        │  └─ _to_utc(row.started_at) ⭐
                                        ▼
                                   target.started_at (aware UTC ✅)
                                        │
                                        ▼
                                  target.ended_at - target.started_at
                                       (aware)       (aware)
                                        │
                                        ▼
                                  delta.total_seconds() * 1000
                                        │
                                        ▼
                                  latency_ms ✅ 저장
```

### 2.3 Data Flow

```
INSERT 경로 (변경 없음):
  Domain (aware UTC) → ORM → MySQL DATETIME (tz 정보 손실, wall clock = UTC)

SELECT 경로 (수정):
  MySQL DATETIME (naive wall clock = UTC)
    → ORM (naive)
    → _to_utc() ⭐ replace(tzinfo=timezone.utc)
    → Domain (aware UTC ✅)

Tracker 계산 가드 (이중 안전):
  target.started_at (정상 시 aware, mapper 우회 시 naive 가능)
    → if naive: replace(tzinfo=timezone.utc)
    → ended_at - started_at → latency_ms
```

---

## 3. Layer-by-Layer Changes

### 3.1 Domain Layer

**변경 없음.**
- `src/domain/agent_run/entities.py`: `AgentRun`, `AgentRunStep`, `ToolCall`, `RetrievalSource`, `LlmCall` dataclass 그대로 유지
- `started_at`, `ended_at`, `created_at` 필드 시그니처(`datetime`/`Optional[datetime]`) 변경 없음
- 다만 **"이 필드들은 항상 timezone-aware UTC"** 라는 묵시적 계약이 mapper에 의해 강제됨

### 3.2 Infrastructure Layer (`src/infrastructure/persistence/repositories/agent_run_repository.py`)

#### 신규 헬퍼: 모듈 레벨 `_to_utc()`

```python
from datetime import datetime, timezone
from typing import Optional

def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """MySQL DATETIME에서 fetch된 naive datetime을 UTC aware로 정규화.

    저장 정책: 본 시스템은 모든 시각을 UTC로 저장한다 (tracker._utcnow()).
    MySQL DATETIME은 tzinfo를 보존하지 않으므로, fetch 시점에 UTC tzinfo를 부여한다.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
```

#### 수정: `_run_to_domain()`

```python
def _run_to_domain(self, row: AgentRunModel) -> AgentRun:
    return AgentRun(
        # ... (other fields)
        started_at=_to_utc(row.started_at),   # ⭐
        ended_at=_to_utc(row.ended_at),       # ⭐
        # ...
    )
```

#### 수정: `_step_to_domain()`

```python
def _step_to_domain(self, row: AgentRunStepModel) -> AgentRunStep:
    return AgentRunStep(
        # ... (other fields)
        started_at=_to_utc(row.started_at),   # ⭐
        ended_at=_to_utc(row.ended_at),       # ⭐
        # ...
    )
```

#### 수정: `_tool_to_domain()`

```python
def _tool_to_domain(self, row: ToolCallModel) -> ToolCall:
    # ... (other fields)
    return ToolCall(
        # ...
        created_at=_to_utc(row.created_at),   # ⭐
    )
```

#### 수정: `_retrieval_to_domain()`

```python
def _retrieval_to_domain(self, row: RetrievalSourceModel) -> RetrievalSource:
    return RetrievalSource(
        # ... (other fields)
        created_at=_to_utc(row.created_at),   # ⭐
    )
```

#### 변경 없음

- `_run_to_orm`, `_tool_to_orm`, `save_step`, `save_retrieval`: INSERT 시 도메인 엔티티는 이미 aware이므로 그대로 ORM에 전달
- `apply_completion_totals`: SQL `TIMESTAMPDIFF`로 DB 내부 계산 → datetime 빼기 없음
- `mark_failed`: latency 계산 없음

### 3.3 Application Layer (`src/application/agent_run/tracker.py`)

#### 수정: `update_step()` (line 244-247 부근)

**Before:**
```python
target.ended_at = _utcnow()
if target.started_at and target.ended_at:
    delta = target.ended_at - target.started_at
    target.latency_ms = int(delta.total_seconds() * 1000)
```

**After:**
```python
target.ended_at = _utcnow()
target.latency_ms = _compute_latency_ms(target.started_at, target.ended_at)
```

모듈 레벨에 헬퍼 추가:

```python
def _compute_latency_ms(
    started_at: Optional[datetime],
    ended_at: Optional[datetime],
) -> Optional[int]:
    """started/ended datetime 간 latency(ms) 계산. naive datetime은 UTC로 보정."""
    if started_at is None or ended_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if ended_at.tzinfo is None:
        ended_at = ended_at.replace(tzinfo=timezone.utc)
    delta = ended_at - started_at
    return int(delta.total_seconds() * 1000)
```

**근거**:
- Mapper에서 이미 정규화하므로 정상 경로에서는 가드가 no-op
- Mapper를 우회하는 mock/test 경로 또는 향후 추가될 다른 mapper에서 누락된 경우에도 안전
- `record_tool_call`, `record_retrieval` 등 다른 곳에서도 향후 latency 계산이 필요해질 경우 재사용 가능

### 3.4 Interface Layer

**변경 없음.**
- Router 응답 schema(`AgentRunResponse` 등)는 그대로 유지
- 다만 mapper 수정의 부수 효과로 `datetime.isoformat()` 결과에 `+00:00`이 부착됨
  - 예: `"started_at": "2026-05-24T06:17:09"` → `"started_at": "2026-05-24T06:17:09+00:00"`
  - **이것은 의도된 개선**: 프론트엔드가 timezone을 정확히 인식 가능

---

## 4. API Specification

### 4.1 기존 API 계약

**변경 없음** — endpoint, request schema, response field 구조 모두 그대로.

### 4.2 응답 datetime 포맷 변화 (부수 효과)

#### `GET /api/v1/admin/agent-runs/{run_id}/steps`

**Before:**
```json
{
  "steps": [
    {
      "id": "98567d88-...",
      "node_name": "answer",
      "status": "SUCCESS",
      "started_at": "2026-05-24T06:17:09",       // tz 없음
      "ended_at": "2026-05-24T06:17:11",         // tz 없음
      "latency_ms": null                          // ⚠ 항상 null (버그)
    }
  ]
}
```

**After:**
```json
{
  "steps": [
    {
      "id": "98567d88-...",
      "node_name": "answer",
      "status": "SUCCESS",
      "started_at": "2026-05-24T06:17:09+00:00", // UTC 명시
      "ended_at": "2026-05-24T06:17:11+00:00",   // UTC 명시
      "latency_ms": 2000                          // ✅ 정상 기록
    }
  ]
}
```

---

## 5. Error Handling

### 5.1 에러 시나리오

| 시나리오 | 현재 동작 | 수정 후 동작 |
|----------|----------|-------------|
| 정상 step 종료 (started/ended 모두 존재) | `TypeError` → WARNING, `latency_ms=NULL` | `latency_ms` 정상 기록 |
| started_at만 존재 (ended_at=None) | `if` 조건 false → `latency_ms` 미설정 | 동일 (헬퍼가 None 반환) |
| 둘 다 None | `if` 조건 false | 동일 |
| 미래 시각 ended < started (clock skew) | 음수 계산 | 동일 (음수 latency_ms 그대로 기록) — 별도 처리 안 함 |
| mapper에서 None row 반환 (find_steps에 step_id 없음) | `target is None` → early return | 동일 |

### 5.2 best-effort 정책 유지

- `update_step`의 try/except 블록은 그대로 유지
- DB 에러는 여전히 WARNING으로 흡수 (관측성은 best-effort)
- 단, `TypeError`는 더 이상 발생하지 않음

### 5.3 에러 응답 형식

**변경 없음** — Tracker는 best-effort이므로 외부 API 에러 응답에 영향 없음

---

## 6. Test Plan

### 6.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `_to_utc()` 헬퍼 | pytest |
| Unit Test | 4개 `_*_to_domain()` mapper의 datetime 필드 | pytest |
| Unit Test | `_compute_latency_ms()` 헬퍼 | pytest |
| Unit Test | `RunTracker.update_step` 통합 | pytest + AsyncMock |
| Regression | 기존 `test_agent_run_repository.py`, `test_tracker.py` | pytest |

### 6.2 Test Cases

#### `tests/infrastructure/persistence/test_agent_run_repository_mapper.py` (신규)

##### `TestToUtcHelper`
- [ ] `None` 입력 → `None` 반환
- [ ] naive datetime → tzinfo가 `timezone.utc`로 설정된 동일 wall clock 반환
- [ ] aware datetime (UTC) → 그대로 반환 (idempotent)
- [ ] aware datetime (KST) → 그대로 반환 (변환하지 않음, 보존)

##### `TestRunToDomain`
- [ ] `AgentRunModel.started_at`이 naive → 도메인 `started_at.tzinfo == timezone.utc`
- [ ] `AgentRunModel.ended_at`이 None → 도메인 `ended_at` is None

##### `TestStepToDomain`
- [ ] `AgentRunStepModel.started_at`이 naive → aware UTC로 변환
- [ ] `AgentRunStepModel.ended_at`이 naive → aware UTC로 변환

##### `TestToolToDomain` / `TestRetrievalToDomain`
- [ ] `created_at`이 naive → aware UTC로 변환

#### `tests/application/agent_run/test_tracker_update_step.py` (신규)

##### `TestComputeLatencyMs`
- [ ] 두 aware datetime → ms 정상 계산
- [ ] started naive, ended aware → 예외 없이 계산
- [ ] started aware, ended naive → 예외 없이 계산
- [ ] 둘 다 naive → UTC 가정 후 계산
- [ ] started=None → None 반환
- [ ] ended=None → None 반환

##### `TestUpdateStepLatency`
- [ ] **회귀 테스트(원인 재현)**: AsyncMock으로 `find_steps`가 naive `started_at`을 가진 step 반환 → `update_step` 호출 → 예외 없이 종료, `repo.update_step`에 전달된 step의 `latency_ms`가 양수 int
- [ ] step_id가 존재하지 않으면 early return (repo.update_step 미호출)
- [ ] status, output_summary, error_text 정상 갱신
- [ ] DB 예외 발생 시 best-effort WARNING 로그 (기존 동작 유지)

### 6.3 통합 검증

```bash
# 1. 전체 unit test 회귀 확인
cd idt
pytest tests/infrastructure/persistence/ tests/application/agent_run/ -v

# 2. 실서버 재기동 후 1회 질의
uvicorn src.main:app --reload --port 8000
# (질의 → LangGraph 실행)

# 3. DB 직접 확인
mysql> SELECT id, node_name, started_at, ended_at, latency_ms
       FROM ai_run_step
       ORDER BY started_at DESC LIMIT 5;
# 기대: latency_ms 컬럼이 NULL이 아닌 양수 값

# 4. 로그 확인
# 기대: "Tracker update_step failed (best-effort)" WARNING 0건
```

### 6.4 verify skills

- `/verify-architecture` — DDD 레이어 위반 0건
- `/verify-logging` — LOG-001 준수 (기존 logger 사용 패턴 유지)
- `/verify-tdd` — 신규 모듈(`_to_utc`, `_compute_latency_ms`)에 대응 테스트 존재

---

## 7. Implementation Order

### 7.1 TDD 순서 (Red → Green → Refactor)

```
Step 1: _to_utc 헬퍼 (TDD)
  ├─ RED:   TestToUtcHelper 4개 케이스 작성 → 실패 확인
  ├─ GREEN: agent_run_repository.py 모듈 레벨에 _to_utc 추가
  └─ REFACTOR: typing/docstring 정리

Step 2: Repository mapper 정규화 (TDD)
  ├─ RED:   TestRunToDomain, TestStepToDomain, TestToolToDomain,
  │         TestRetrievalToDomain 작성 → 실패 확인
  ├─ GREEN: 4개 _*_to_domain 메서드에 _to_utc 적용
  └─ REFACTOR: 중복 패턴 점검

Step 3: _compute_latency_ms 헬퍼 (TDD)
  ├─ RED:   TestComputeLatencyMs 6개 케이스 작성 → 실패 확인
  ├─ GREEN: tracker.py 모듈 레벨에 _compute_latency_ms 추가
  └─ REFACTOR

Step 4: update_step 통합 (TDD)
  ├─ RED:   TestUpdateStepLatency 회귀 케이스 작성 → 실패 (TypeError 재현)
  ├─ GREEN: update_step의 line 244-247을 _compute_latency_ms 호출로 교체
  └─ REFACTOR

Step 5: 회귀 검증
  ├─ pytest 전체 통과
  ├─ 실서버 1회 질의 → DB latency_ms 채워짐 확인
  └─ WARNING 로그 미발생 확인

Step 6: verify skills
  ├─ /verify-architecture
  ├─ /verify-logging
  └─ /verify-tdd
```

### 7.2 파일 변경 요약

| # | File | Change | Lines |
|---|------|--------|-------|
| 1 | `src/infrastructure/persistence/repositories/agent_run_repository.py` | `_to_utc()` 추가, 4개 mapper 수정 | ~15 |
| 2 | `src/application/agent_run/tracker.py` | `_compute_latency_ms()` 추가, `update_step` 4줄 교체 | ~12 |
| 3 | `tests/infrastructure/persistence/test_agent_run_repository_mapper.py` (신규) | 헬퍼 + mapper 테스트 ~12개 | ~120 |
| 4 | `tests/application/agent_run/test_tracker_update_step.py` (신규) | 헬퍼 + update_step 테스트 ~10개 | ~150 |

---

## 8. Dependency & Risk

### 8.1 의존성

| 항목 | 영향 |
|------|------|
| Python `datetime.timezone` | 표준 라이브러리, 추가 의존성 없음 |
| SQLAlchemy / aiomysql | 변경 없음 |
| MySQL DATETIME 컬럼 | 스키마 변경 없음, 기존 row 그대로 사용 |

### 8.2 Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| 기존 DB row의 wall clock이 UTC가 아닌 경우 (서버 timezone 변경 이력) | 본 시스템은 처음부터 `datetime.now(timezone.utc)`로 저장. 정책상 UTC 일관 보장. 만약 과거 데이터에 KST가 섞여 있다면 별도 데이터 마이그레이션 필요(현 scope 외) |
| API 응답 포맷이 `+00:00` 부착으로 변경됨 (프론트엔드 영향) | ISO8601 표준이므로 일반적인 JS `new Date()` 파서가 정상 처리. 변경 후 프론트 1회 smoke test 권장 |
| `_compute_latency_ms`에 음수 결과 발생 (clock skew) | 도메인 정책상 음수 latency 허용 (이상 데이터 식별 가능). 별도 처리 안 함 |
| 향후 `find_run` / `list_runs` 응답의 datetime 비교 코드가 추가될 때 | mapper 정규화 덕분에 항상 aware → 추가 가드 불필요 |
| Mapper 우회 경로 (직접 ORM 사용) | tracker의 `_compute_latency_ms` 가드가 2차 방어선 역할 |

### 8.3 관찰성 영향

- **개선**: `ai_run_step.latency_ms` 채움률 100% 달성 → admin 대시보드 step 지연 분석 가능
- **개선**: WARNING 로그 노이즈 제거 → 실제 경고가 묻히지 않음
- **무영향**: `ai_run.latency_ms`는 `apply_completion_totals`의 SQL `TIMESTAMPDIFF`로 이미 정상 동작 중

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-24 | Initial draft | AI Assistant |
