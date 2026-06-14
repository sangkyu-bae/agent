# Fix Tracker Naive/Aware Datetime — Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Completion Date**: 2026-05-24
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | fix-tracker-naive-aware-datetime |
| Start Date | 2026-05-23 |
| Completion Date | 2026-05-24 |
| Duration | 1 day (Plan → Report) |
| Match Rate | 100% (Design 명시 변경/테스트 모두 충족) |
| Iteration Count | 0 (첫 Check에서 ≥90% 달성) |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────────────┐
│  Design Match Rate: 100%                             │
├──────────────────────────────────────────────────────┤
│  ✅ Infrastructure Changes: 5 / 5 items              │
│     - _to_utc 헬퍼 + 4 mapper datetime 정규화        │
│  ✅ Application Changes:    2 / 2 items              │
│     - _compute_latency_ms 헬퍼 + update_step 교체    │
│  ✅ Out-of-Scope 보존:      5 / 5 items              │
│     - Domain, ORM 컬럼, API schema, INSERT 경로,     │
│       mark_failed/apply_completion_totals            │
│  ✅ Test Cases:            22 / 22 items (10+12)     │
│     (Design 명시 + edge case 2 보강)                 │
│  🔴 Missing Gap:            0                         │
│  🟡 Added (improvement):    2 (edge case 테스트)     │
│  ✅ Unit Tests:           161 / 161 PASS             │
│     (persistence + agent_run 전체)                   │
│  ✅ Regression:             0 건                      │
└──────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | LangGraph 노드 종료마다 `RunTracker.update_step`이 `TypeError: can't subtract offset-naive and offset-aware datetimes`로 실패 → `ai_run_step.latency_ms`가 NULL로 남고 WARNING 로그가 매 요청마다 폭증. AGENT-OBS-001 관측성 데이터에 구멍 발생 |
| **Solution** | Repository mapper(`_run/_step/_tool/_retrieval_to_domain`)에 `_to_utc()` 헬퍼로 naive→UTC aware 정규화 → "도메인은 항상 aware UTC" 계약을 인프라 레이어에서 강제. `tracker.update_step`에 `_compute_latency_ms()` 2차 방어선 추가 |
| **Function/UX Effect** | 모든 step의 `latency_ms`가 정상 기록(채움률 NULL→100%). admin 대시보드에서 노드별 지연 시간 신뢰 가능. API 응답 datetime이 ISO8601 `+00:00` 부착되어 프론트엔드 timezone 인식 정확. WARNING 로그 노이즈 제거 |
| **Core Value** | AGENT-OBS-001 관측성 신뢰도 회복 — 성능 분석/SLA 모니터링 기반 확보. "도메인 datetime은 항상 aware UTC" 정책을 영속화 레이어에서 강제하여 향후 동일 패턴 버그 원천 차단 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [fix-tracker-naive-aware-datetime.plan.md](../01-plan/features/fix-tracker-naive-aware-datetime.plan.md) | ✅ Finalized |
| Design | [fix-tracker-naive-aware-datetime.design.md](../02-design/features/fix-tracker-naive-aware-datetime.design.md) | ✅ Finalized |
| Check | [fix-tracker-naive-aware-datetime.analysis.md](../03-analysis/fix-tracker-naive-aware-datetime.analysis.md) | ✅ Complete |
| Act | Current document | ✅ Complete |

---

## 3. PDCA Cycle Summary

### 3.1 Plan Phase (2026-05-23)

**Document**: `docs/01-plan/features/fix-tracker-naive-aware-datetime.plan.md`

**Root Cause Identified**:
- `tracker.record_step()` → `_utcnow()`로 aware UTC datetime 저장
- SQLAlchemy `AgentRunStepModel.started_at`은 `DateTime` (timezone=False) → MySQL `DATETIME` 컬럼으로 INSERT 시 tzinfo 손실
- `update_step()` → `find_steps()` → `_step_to_domain`이 DB row를 mapping 시 **naive** datetime으로 복원
- `target.ended_at = _utcnow()` (aware) 와 `target.started_at` (naive) 빼기 → `TypeError`

**Scope Decision**:
- ✅ Mapper 정규화(인프라 레이어 책임)로 도메인 일관성 확보
- ✅ Tracker에도 2차 방어선 추가 (mapper 우회 경로 대비)
- ⛔ ORM 컬럼 타입 변경 / DB 마이그레이션 (가성비 낮음, MySQL DATETIME은 tzinfo 비지원)
- ⛔ 기존 NULL latency_ms row 백필 (out of scope)

### 3.2 Design Phase (2026-05-24)

**Document**: `docs/02-design/features/fix-tracker-naive-aware-datetime.design.md`

**핵심 설계**:
1. **`_to_utc(dt)` 모듈 헬퍼** (repository.py:38-49): None / naive→aware UTC / aware idempotent
2. **4개 mapper 정규화**: `_run/_step/_tool/_retrieval_to_domain` 각 datetime 필드를 `_to_utc()` wrap
3. **`_compute_latency_ms(started, ended)` 모듈 헬퍼** (tracker.py:53-70): None 가드 + naive 보정 + ms 계산
4. **`update_step` 4줄 교체**: 기존 `if/delta` 블록을 헬퍼 호출로 단순화

**대안 비교**:

| 방안 | 채택 | 사유 |
|------|:----:|------|
| A. `update_step`만 가드 | ⛔ | mapper 일관성 결여, API 응답에서 모호성 잔존 |
| **B. Mapper 정규화 + tracker 2차 방어** | ✅ | "도메인은 aware UTC" 정책 강제, 다중 방어선 |
| C. ORM 컬럼 `DateTime(timezone=True)` + 마이그레이션 | ⛔ | MySQL DATETIME 비지원, TIMESTAMP는 2038/DST 이슈 |

### 3.3 Do Phase — Implementation (2026-05-24)

**TDD Cycle** (5 단계):

| Step | RED | GREEN |
|------|-----|-------|
| 1. `_to_utc` 헬퍼 | TestToUtcHelper 4 case 작성, ImportError로 fail | repository.py:38-49 추가 → PASSED |
| 2. 4 mapper 정규화 | TestRunToDomain/StepToDomain/ToolToDomain/RetrievalToDomain 6 case 작성 → naive 단언 fail | 4 mapper 각 `_to_utc()` wrap → PASSED |
| 3. `_compute_latency_ms` | TestComputeLatencyMs 7 case 작성, ImportError fail | tracker.py:53-70 추가 → PASSED |
| 4. `update_step` 통합 + 회귀 | TestUpdateStepLatency 5 case (회귀 1 포함) → TypeError 재현 | tracker.py:264-267 헬퍼 호출로 교체 → PASSED |
| 5. 전체 회귀 검증 | — | `pytest tests/infrastructure/persistence/ tests/application/agent_run/` → 161 passed |

**Files Changed**:

| File | Change Type | Lines |
|------|-------------|-------|
| `src/infrastructure/persistence/repositories/agent_run_repository.py` | Modified — `_to_utc()` 추가, 4 mapper datetime 필드 wrap | +15 |
| `src/application/agent_run/tracker.py` | Modified — `_compute_latency_ms()` 추가, `update_step` 4줄 교체 | +18 / -3 |
| `tests/infrastructure/persistence/test_agent_run_repository_mapper.py` | Added — 10 cases | +200 |
| `tests/application/agent_run/test_tracker_update_step.py` | Added — 12 cases | +230 |

### 3.4 Check Phase — Gap Analysis (2026-05-24)

**Document**: `docs/03-analysis/fix-tracker-naive-aware-datetime.analysis.md`

**Match Rate: 100%**

| Category | Score |
|----------|:-----:|
| Design §3 Layer Changes | 100% |
| Design §3 Out-of-Scope Preservation | 100% |
| Design §6.2 Test Coverage | 100% |
| Design §7 TDD Order | 100% |
| Design §8 Risk Mitigation | 100% |

**Gap 발견 사항**:
- 🔴 Missing: 없음
- 🟡 Added (개선): `TestComputeLatencyMs::test_both_none_returns_none` (edge case 보강), `TestUpdateStepLatency::test_aware_started_at_normal_path` (정상 경로 회귀 보강)
- 🔵 Changed: 없음 (Design 그대로 구현)

### 3.5 Act Phase

**Status**: 불필요 — Match Rate 100%로 90% 임계 초과. 추가 iteration 없이 Report 단계 진입.

---

## 4. Technical Details

### 4.1 Bug Reproduction (Before Fix)

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

**발생 흐름**:

| 단계 | 처리 | tzinfo |
|------|------|--------|
| ① `record_step()` | `_utcnow()` → `datetime.now(timezone.utc)` | **aware UTC** |
| ② SQLAlchemy INSERT | `Mapped[datetime]` (`DateTime`, timezone=False) → MySQL `DATETIME` | naive (wall clock) |
| ③ `update_step` → `find_steps()` → `_step_to_domain` | row → domain mapping | **naive ⚠** |
| ④ `target.ended_at = _utcnow()` | — | **aware UTC** |
| ⑤ `target.ended_at - target.started_at` | aware - naive | **TypeError ⛔** |

### 4.2 Fix Implementation (After Fix)

**`repository.py:38-49` (신규 헬퍼)**:
```python
def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """MySQL DATETIME에서 fetch된 naive datetime을 UTC aware로 정규화."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
```

**4 mapper 정규화** (예시: `_step_to_domain`):
```python
def _step_to_domain(self, row: AgentRunStepModel) -> AgentRunStep:
    return AgentRunStep(
        # ...
        started_at=_to_utc(row.started_at),   # ⭐ aware UTC 보장
        ended_at=_to_utc(row.ended_at),       # ⭐ aware UTC 보장
        # ...
    )
```

**`tracker.py:53-70` (신규 헬퍼)**:
```python
def _compute_latency_ms(
    started_at: Optional[datetime],
    ended_at: Optional[datetime],
) -> Optional[int]:
    """두 datetime 간 latency(ms) 계산. naive datetime은 UTC로 보정."""
    if started_at is None or ended_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if ended_at.tzinfo is None:
        ended_at = ended_at.replace(tzinfo=timezone.utc)
    delta = ended_at - started_at
    return int(delta.total_seconds() * 1000)
```

**`tracker.py:264-267` (update_step 교체)**:
```python
target.ended_at = _utcnow()
target.latency_ms = _compute_latency_ms(target.started_at, target.ended_at)
await repo.update_step(target)
```

### 4.3 Why "Mapper 정규화 + Tracker 가드" Approach

| 대안 | 장점 | 단점 | 선정 |
|------|------|------|:---:|
| (A) `update_step` 한 곳만 가드 | 최소 변경, 즉시 해결 | API 응답에서 동일 모호성 잔존, 향후 다른 호출 경로 재발 위험 | ❌ |
| **(B) Mapper 정규화 + Tracker 2차 방어** | "도메인은 aware UTC" 정책 인프라에서 강제, 모든 경로 안전 | mapper 4곳 수정 필요 | ✅ |
| (C) ORM 컬럼 `DateTime(timezone=True)` + 마이그레이션 | DB 레벨 일관 | MySQL DATETIME 비지원, TIMESTAMP는 2038/DST 이슈, 마이그 비용 큼 | ❌ |

방안 B 채택 — 14 lines 추가로 모든 datetime 경로 정규화 + 미래 잠재 버그 차단.

### 4.4 Side Effect — API 응답 datetime 포맷 개선

**Before:**
```json
{ "started_at": "2026-05-24T06:17:09", "latency_ms": null }
```

**After:**
```json
{ "started_at": "2026-05-24T06:17:09+00:00", "latency_ms": 2000 }
```

- 의도된 부수효과: ISO8601 표준 timezone suffix 부착으로 프론트엔드 `new Date()` 파서 정확도 향상
- 일반 JS Date 파서 호환 (브레이킹 체인지 아님)

---

## 5. Out-of-Scope / Future Work

### 5.1 별도 작업 권장

| # | 항목 | 분류 | 권장 |
|---|------|:----:|------|
| A | 기존 `ai_run_step.latency_ms` NULL row 백필 | 데이터 마이그레이션 | 이력 데이터 latency 분석 필요 시 별도 task |
| B | 음수 latency 발생 시 경고 로깅 (clock skew 감지) | 개선 | 모니터링 요구 시 별도 feature |
| C | `update_step`의 `find_steps` 후 set-based UPDATE 최적화 | 기술 부채 | `tracker.py:254` 주석에 기 명시 |

### 5.2 수동 검증 (사용자 확인 권장)

1. **실서버 1회 질의** → `uvicorn src.main:app --reload --port 8000` 재기동 후 LangGraph 노드 1회 실행
2. **DB 직접 확인**:
   ```sql
   SELECT id, node_name, started_at, ended_at, latency_ms
   FROM ai_run_step ORDER BY started_at DESC LIMIT 5;
   -- 기대: latency_ms 양수 값
   ```
3. **로그 확인** → `Tracker update_step failed (best-effort)` WARNING 미발생
4. **프론트엔드 smoke test** → admin 대시보드의 step latency 표시 정상

---

## 6. Lessons Learned

| 항목 | 내용 |
|------|------|
| **DB와 도메인의 timezone 책임 경계** | MySQL `DATETIME`은 tzinfo 비저장. 도메인 dataclass가 `datetime` 타입을 명시해도 naive/aware는 표현되지 않음 → mapper에서 정규화하지 않으면 비대칭 발생. Repository는 "DB→도메인 매핑 시 일관 보장" 책임을 명시적으로 가져야 함 |
| **TDD 회귀 케이스의 위력** | `test_naive_started_at_does_not_raise_typeerror`로 `find_steps` mock에 naive datetime을 강제 주입 → 정확히 원인 재현(`TypeError`). Fix 후 동일 케이스로 회귀 보호 영구 확보 |
| **2차 방어선의 가치** | mapper에서 정규화하면 정상 경로는 문제 없지만, 향후 직접 ORM 사용/테스트 mock 우회 시 동일 버그 재발 가능. `_compute_latency_ms`의 naive 가드가 "no-op이지만 안전망" 역할 — 14 lines 헬퍼로 미래 비용 절감 |
| **데이터 저장 정책의 묵시적 계약** | "본 시스템은 datetime을 UTC wall clock으로 DB에 저장"이 코드 어디에도 명시되지 않았었음. 본 fix에서 `_to_utc()` docstring으로 정책 명시화 — 새로 합류하는 개발자도 mapper 우회 시 위험을 인식 가능 |

---

## 7. Acceptance Criteria

| Criteria | Result |
|----------|:------:|
| `RunTracker.update_step` 호출 시 `TypeError` 미발생 | ✅ `test_naive_started_at_does_not_raise_typeerror` PASS |
| `_to_utc(None)` → None | ✅ `test_returns_none_for_none` PASS |
| `_to_utc(naive)` → aware UTC (wall clock 보존) | ✅ `test_naive_datetime_becomes_aware_utc` PASS |
| `_to_utc(aware)` → idempotent | ✅ `test_aware_utc_returned_as_is_idempotent` PASS |
| 4 mapper 모두 naive → aware 변환 | ✅ TestRunToDomain/StepToDomain/ToolToDomain/RetrievalToDomain PASS |
| `_compute_latency_ms` naive/aware 혼합 안전 | ✅ TestComputeLatencyMs 7 case PASS |
| `update_step` status/error_text 갱신 기존 동작 보존 | ✅ `test_status_and_error_text_updated` PASS |
| best-effort WARNING 정책 유지 | ✅ `test_db_failure_swallowed_as_warning` PASS |
| Domain entities / ORM 컬럼 / API schema 변경 0 | ✅ git diff 미발생 확인 |
| persistence + agent_run 전체 161 테스트 회귀 0 | ✅ 161/161 PASS |

**Final Status**: ✅ **Completed (100% Match Rate, 0 Regression)**
