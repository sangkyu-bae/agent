# Plan: fix-tracker-naive-aware-datetime

> `RunTracker.update_step`에서 `started_at`(naive)과 `ended_at`(aware) 빼기 연산으로 발생하는 `TypeError` 수정

---

## Executive Summary

| 구분 | 내용 |
|------|------|
| **Problem** | LangGraph 노드 종료 시점에 `RunTracker.update_step`이 `latency_ms`를 계산하지 못하고 `TypeError: can't subtract offset-naive and offset-aware datetimes`를 발생시켜 step 갱신이 best-effort 경고로 처리됨 |
| **Solution** | Repository mapper(`_step_to_domain` 등)에서 MySQL `DATETIME`으로부터 fetch된 naive datetime을 UTC aware로 정규화하고, `update_step`에서 비교 직전 안전 가드 추가 |
| **Function UX Effect** | 운영자가 `ai_run_step.latency_ms`를 신뢰 가능하게 조회 가능. step 단위 지연 시간 누락 0건. WARNING 로그 노이즈 제거 |
| **Core Value** | AGENT-OBS-001 관측성 신뢰도 회복 — Run/Step latency가 빠짐없이 기록되어 성능 분석과 SLA 모니터링 기반 확보 |

---

## 1. 문제 정의

### 1-1. 현상

```
[2026-05-23T06:17:09Z] WARNING  Tracker update_step failed (best-effort)
  run_id   : 477276b8-7e45-4ccd-9d48-f01e6d0257c5
  step_id  : 98567d88-d566-41b2-afb5-059ecc5718d4
  location : tracker.py:update_step:250
Traceback (most recent call last):
  File "...\src\application\agent_run\tracker.py", line 246, in update_step
    delta = target.ended_at - target.started_at
            ~~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~
TypeError: can't subtract offset-naive and offset-aware datetimes
```

매 LangGraph 노드 종료마다 발생 → `latency_ms`가 `NULL`로 남고, 관측성 데이터에 구멍이 생긴다.

### 1-2. 근본 원인

값의 timezone 정보가 **저장 → fetch** 경로에서 비대칭하게 처리된다.

| 단계 | 처리 | tzinfo 상태 |
|------|------|-------------|
| ① `tracker.record_step()` line 202 | `_utcnow()` → `datetime.now(timezone.utc)` | **aware (UTC)** |
| ② SQLAlchemy → MySQL `DATETIME` 컬럼 INSERT | `AgentRunStepModel.started_at: Mapped[datetime]` (`DateTime`, **timezone=False**) | naive로 저장 (wall clock만) |
| ③ `update_step()` line 235 → `repo.find_steps()` → `_step_to_domain` | SQLAlchemy가 MySQL DATETIME을 그대로 매핑 | **naive** |
| ④ `update_step()` line 244 | `target.ended_at = _utcnow()` | **aware (UTC)** |
| ⑤ `update_step()` line 246 | `target.ended_at - target.started_at` | **TypeError** |

핵심: **도메인 엔티티는 항상 aware UTC를 가정**하지만, **인프라(MySQL `DATETIME`)는 tzinfo를 보존하지 못함**. mapper에서 정규화가 빠져 있다.

### 1-3. 동일 위험 지점

| 위치 | 위험도 | 비고 |
|------|--------|------|
| `tracker.py:update_step` line 246 | 🔴 발생 중 | 본 이슈 |
| `repository._run_to_domain` (started_at/ended_at) | 🟡 잠재 | API 응답 시 naive datetime이 그대로 JSON 직렬화 → ISO8601 'Z' 미부착, 타임존 모호 |
| `repository._tool_to_domain` (created_at) | 🟡 잠재 | 동일 |
| `repository._retrieval_to_domain` (created_at) | 🟡 잠재 | 동일 |
| `apply_completion_totals` (SQL `TIMESTAMPDIFF`) | 🟢 안전 | DB에서 직접 계산 |
| `update_tool_call` | 🟢 안전 | `latency_ms`를 외부에서 받음, datetime 빼기 없음 |
| `mark_failed` | 🟢 안전 | latency 계산 없음 |

---

## 2. 영향 범위

- **직접 영향**: 모든 LangGraph 노드 종료 시 `ai_run_step.latency_ms` 미기록 → 성능 분석/Trace 표시 누락
- **잠재 영향**: M5 admin 대시보드의 step latency 통계, p95/p99 metric 산출 신뢰도 저하
- **로그 노이즈**: 매 노드마다 WARNING 발생 → 진짜 경고가 묻힘
- **DB 데이터 무결성**: 기존에 저장된 row는 그대로(naive UTC wall clock 의미 유지), 영향 없음

---

## 3. 수정 전략

### 3-1. 방안 비교

| 방안 | 장점 | 단점 | 채택 |
|------|------|------|------|
| A. `update_step` 한 곳만 가드(naive→aware 변환) | 최소 변경, 즉시 해결 | mapper 일관성 결여 → API 응답에서 동일 모호성 잔존 | ⛔ |
| B. **Mapper에서 naive→aware(UTC) 정규화 + `update_step` 가드** | "도메인은 aware UTC" 정책 강제, API/Tracker 모두 안전 | mapper 4곳(_run/_step/_tool/_retrieval) 일괄 수정 필요 | ✅ |
| C. ORM 컬럼을 `DateTime(timezone=True)`로 변경 + 마이그레이션 | DB 레벨 일관성 | MySQL `DATETIME`은 tzinfo 비지원, `TIMESTAMP`로 바꾸면 2038 + DST 이슈, 마이그레이션 비용 큼 | ⛔ |

### 3-2. 채택 방안 (B) 핵심 변경

1. **Repository mapper에 정규화 헬퍼 추가**: `_to_utc(dt: datetime | None) -> datetime | None`
   - `dt is None` → `None`
   - `dt.tzinfo is None` → `dt.replace(tzinfo=timezone.utc)` (저장 정책상 UTC 가정)
   - 이미 aware → 그대로
2. `_step_to_domain`, `_run_to_domain`, `_tool_to_domain`, `_retrieval_to_domain`의 모든 datetime 필드(`started_at`, `ended_at`, `created_at`)에 적용
3. `tracker.update_step` line 246: 비교 직전에도 동일 가드 적용(이중 안전; mapper 우회 경로 대비)
4. `_utcnow()`는 이미 aware UTC이므로 변경 없음

### 3-3. 변경 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src/infrastructure/persistence/repositories/agent_run_repository.py` | `_to_utc` 헬퍼 + 4개 mapper 정규화 |
| `src/application/agent_run/tracker.py` | line 244-247 비교 가드 추가(`started_at`이 naive면 UTC로 보정 후 빼기) |
| `tests/infrastructure/persistence/test_agent_run_repository_mapper.py` (신규) | naive row → aware domain 변환 테스트 |
| `tests/application/agent_run/test_tracker_update_step.py` (신규 or 확장) | started_at이 naive로 들어와도 latency_ms 계산 성공 테스트 |

---

## 4. 구현 계획 (TDD)

### Step 1: 테스트 작성 (Red)

**테스트 1 — Repository mapper 정규화**
- 픽스처: `AgentRunStepModel`에 `started_at=datetime(2026, 5, 23, 6, 17, 0)` (naive) 주입
- `_step_to_domain(row).started_at.tzinfo == timezone.utc` 단언
- `AgentRunModel`, `ToolCallModel`, `RetrievalSourceModel` 동일 패턴 검증

**테스트 2 — Tracker latency 계산**
- 시나리오: `record_step` → DB 저장 → `update_step` 호출 (실제 SQLite/in-memory or AsyncMock repo)
- AsyncMock 사용 시 `find_steps`가 반환하는 step의 `started_at`을 naive로 강제
- 검증: 예외 없이 종료, `target.latency_ms`가 양수 int

### Step 2: 구현 (Green)

**`agent_run_repository.py`**

```python
from datetime import datetime, timezone

def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """MySQL DATETIME에서 fetch된 naive datetime을 UTC aware로 정규화."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
```

각 `_*_to_domain` 내부의 모든 datetime 필드 매핑을 `_to_utc(row.xxx)`로 감싼다.

**`tracker.py` `update_step` (line 244-247 부근)**

```python
target.ended_at = _utcnow()
started = target.started_at
if started is not None and started.tzinfo is None:
    started = started.replace(tzinfo=timezone.utc)
if started is not None and target.ended_at is not None:
    delta = target.ended_at - started
    target.latency_ms = int(delta.total_seconds() * 1000)
```

### Step 3: 검증

- 신규 테스트 통과 (Green)
- 기존 테스트 회귀 없음: `pytest tests/infrastructure/persistence/ tests/application/agent_run/ -q`
- 실서버 재기동 후 LangGraph 1회 실행 → WARNING 로그 미발생, `SELECT latency_ms FROM ai_run_step ORDER BY started_at DESC LIMIT 5;` 값 채워짐 확인

### Step 4: skill 검증

- `/verify-architecture` (DDD 레이어 위반 없는지)
- `/verify-logging` (LOG-001 준수)
- `/verify-tdd` (신규 모듈 테스트 커버리지)

---

## 5. 완료 기준

- [ ] `RunTracker.update_step` 호출 시 `TypeError` 미발생
- [ ] `ai_run_step.latency_ms`가 모든 종료된 step에 정상 기록(NULL 0건)
- [ ] `_step_to_domain` 등 4개 mapper가 항상 aware UTC datetime 반환 (단위 테스트)
- [ ] 기존 테스트 스위트 회귀 없음
- [ ] `Tracker update_step failed (best-effort)` WARNING 로그 미발생
- [ ] DDD/Logging/TDD verify skill 통과

---

## 6. 관련 문서

- AGENT-OBS-001 §4-1 (ai_run_step 스키마)
- `docs/rules/db-session.md` (세션 정책 — 이번 수정과 무관, 기존 패턴 유지)
- 원본 코드: `src/application/agent_run/tracker.py:244-247`, `src/infrastructure/persistence/repositories/agent_run_repository.py:330-345`
