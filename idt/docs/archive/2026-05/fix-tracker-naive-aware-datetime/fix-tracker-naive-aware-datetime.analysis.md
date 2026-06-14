# Gap Analysis: fix-tracker-naive-aware-datetime

> 분석일: 2026-05-24
> 분석 대상: Design ↔ Implementation/Tests
> Match Rate: **100%**

---

## 1. 분석 개요

| 항목 | 내용 |
|------|------|
| Plan | `docs/01-plan/features/fix-tracker-naive-aware-datetime.plan.md` |
| Design | `docs/02-design/features/fix-tracker-naive-aware-datetime.design.md` |
| Implementation | `src/infrastructure/persistence/repositories/agent_run_repository.py`, `src/application/agent_run/tracker.py` |
| Tests (new) | `tests/infrastructure/persistence/test_agent_run_repository_mapper.py`, `tests/application/agent_run/test_tracker_update_step.py` |
| Test Result | **161/161 PASS** (persistence + agent_run 전체) — 신규 22 case 포함, 기존 139 회귀 0 |

---

## 2. 카테고리별 점수

| Category | Score | Status |
|----------|:-----:|:------:|
| Design §3 Layer-by-Layer Changes | 100% | ✅ PASS |
| Design §3 Out-of-Scope Preservation | 100% | ✅ PASS |
| Design §6.2 Test Cases Coverage | 100% | ✅ PASS |
| Design §7 Implementation Order (TDD) | 100% | ✅ PASS |
| Design §8 Risk Mitigation | 100% | ✅ PASS |
| **Overall Match Rate** | **100%** | **✅ PASS** |

---

## 3. Design §3 Layer-by-Layer 변경 커버리지

### 3-1. Infrastructure Layer (`agent_run_repository.py`)

| # | Design 항목 | Expected | Actual | Status |
|---|-------------|----------|--------|:------:|
| 1 | `_to_utc(dt)` 모듈 헬퍼 추가 | None / naive→aware UTC / aware idempotent | `repository.py:38-49`에 정의 (시그니처·docstring 일치) | ✅ |
| 2 | `_run_to_domain`에 `_to_utc` 적용 | `started_at`, `ended_at` 양쪽 wrap | `repository.py:337-338` 적용 확인 | ✅ |
| 3 | `_step_to_domain`에 `_to_utc` 적용 | `started_at`, `ended_at` 양쪽 wrap | `repository.py:355-356` 적용 확인 | ✅ |
| 4 | `_tool_to_domain`에 `_to_utc` 적용 | `created_at` wrap | `repository.py:409` 적용 확인 | ✅ |
| 5 | `_retrieval_to_domain`에 `_to_utc` 적용 | `created_at` wrap | `repository.py:424` 적용 확인 | ✅ |

### 3-2. Application Layer (`tracker.py`)

| # | Design 항목 | Expected | Actual | Status |
|---|-------------|----------|--------|:------:|
| 6 | `_compute_latency_ms(started, ended)` 모듈 헬퍼 | None 가드 + naive→aware 보정 + ms 계산 | `tracker.py:53-70`에 정의 (시그니처·로직 일치) | ✅ |
| 7 | `update_step` 비교 4줄 교체 | 기존 `delta = ended - started`를 헬퍼 호출로 교체 | `tracker.py:264-267` 교체 완료 — 원래 `if target.started_at and target.ended_at: delta = ...` 라인 완전 제거 | ✅ |

### 3-3. Domain / Interface Layer (변경 금지 검증)

| # | Design 항목 | Expected | Actual | Status |
|---|-------------|----------|--------|:------:|
| 8 | `domain/agent_run/entities.py` 변경 없음 | dataclass 그대로 유지 | git diff 미발생 (확인 완료) | ✅ |
| 9 | ORM 컬럼 타입 변경 없음 | `DateTime` (timezone=False) 유지 | `models/agent_run.py` git diff 없음 | ✅ |
| 10 | API router/schema 변경 없음 | 응답 schema 그대로 | router 파일 미수정 | ✅ |
| 11 | `_run_to_orm`, `_tool_to_orm`, `save_step`, `save_retrieval` 등 INSERT 경로 | 변경 없음 (도메인은 이미 aware) | `repository.py:170-171, 250, 311-312` 그대로 | ✅ |
| 12 | `mark_failed`, `apply_completion_totals` | 변경 없음 (각각 aware UTC 직접 주입 / SQL TIMESTAMPDIFF) | `repository.py:150, 110` 그대로 | ✅ |

---

## 4. Design §6.2 테스트 케이스 커버리지

### 4-1. `test_agent_run_repository_mapper.py` (신규)

| Design 명시 케이스 | 실제 테스트 | 상태 |
|-------------------|------------|:----:|
| `TestToUtcHelper` — None 입력 | `test_returns_none_for_none` | ✅ |
| `TestToUtcHelper` — naive → aware UTC | `test_naive_datetime_becomes_aware_utc` (wall clock 값 보존도 단언) | ✅ |
| `TestToUtcHelper` — aware UTC idempotent | `test_aware_utc_returned_as_is_idempotent` | ✅ |
| `TestToUtcHelper` — aware KST 보존 | `test_aware_non_utc_preserved_not_converted` | ✅ |
| `TestRunToDomain` — naive started_at | `test_naive_started_at_becomes_aware_utc` (ended_at도 함께 검증) | ✅ |
| `TestRunToDomain` — ended_at=None | `test_ended_at_none_stays_none` | ✅ |
| `TestStepToDomain` — naive started/ended | `test_naive_started_and_ended_become_aware_utc` | ✅ |
| `TestStepToDomain` — ended=None | `test_ended_at_none_stays_none` | ✅ |
| `TestToolToDomain` — naive created_at | `test_naive_created_at_becomes_aware_utc` | ✅ |
| `TestRetrievalToDomain` — naive created_at | `test_naive_created_at_becomes_aware_utc` | ✅ |

**Total**: 10 cases — Design 명시 사항 전부 커버.

### 4-2. `test_tracker_update_step.py` (신규)

| Design 명시 케이스 | 실제 테스트 | 상태 |
|-------------------|------------|:----:|
| `TestComputeLatencyMs` — 둘 다 aware | `test_both_aware_returns_correct_ms` | ✅ |
| `TestComputeLatencyMs` — naive started, aware ended | `test_started_naive_ended_aware_no_typeerror` | ✅ |
| `TestComputeLatencyMs` — aware started, naive ended | `test_started_aware_ended_naive_no_typeerror` | ✅ |
| `TestComputeLatencyMs` — 둘 다 naive | `test_both_naive_assumes_utc_and_computes` | ✅ |
| `TestComputeLatencyMs` — started=None | `test_started_none_returns_none` | ✅ |
| `TestComputeLatencyMs` — ended=None | `test_ended_none_returns_none` | ✅ |
| `TestUpdateStepLatency` — **회귀 케이스 (원인 재현)** | `test_naive_started_at_does_not_raise_typeerror` — find_steps mock에 naive started_at 주입, TypeError 미발생 + latency_ms 양수 단언 | ✅ |
| `TestUpdateStepLatency` — step_id 없음 early return | `test_step_id_not_found_early_return` | ✅ |
| `TestUpdateStepLatency` — status/error_text 갱신 | `test_status_and_error_text_updated` | ✅ |
| `TestUpdateStepLatency` — best-effort WARNING | `test_db_failure_swallowed_as_warning` | ✅ |

**Total**: 12 cases (Design 명시 10 + 추가 2 — `test_both_none_returns_none`, `test_aware_started_at_normal_path`).

**추가 케이스는 Gap 아님 — Design 의도 강화 (edge case 보강).**

---

## 5. Design §7 TDD 순서 준수

| Step | Design 순서 | 실제 진행 | 상태 |
|------|------------|----------|:----:|
| 1 | `_to_utc` 헬퍼 Red→Green | TestToUtcHelper 4 case 선작성 → 헬퍼 추가 후 PASSED | ✅ |
| 2 | 4개 mapper 정규화 Red→Green | TestRunToDomain~TestRetrievalToDomain 6 case 선작성 → mapper 4곳 수정 후 PASSED | ✅ |
| 3 | `_compute_latency_ms` 헬퍼 Red→Green | TestComputeLatencyMs 7 case 선작성 → 헬퍼 추가 후 PASSED | ✅ |
| 4 | update_step 통합 + 회귀 케이스 | TestUpdateStepLatency 5 case (회귀 포함) 선작성 → update_step 4줄 교체 후 PASSED | ✅ |
| 5 | 전체 회귀 검증 | `pytest tests/infrastructure/persistence/ tests/application/agent_run/` → **161 passed** | ✅ |
| 6 | verify skills | **미실행** — 사용자 명령 대기 (선택적 단계) | ⏸ |

Step 6은 Design에서도 "추가 검증" 성격으로 표기. Match Rate에 영향 없음.

---

## 6. Design §7.2 파일 변경 요약 검증

| # | File | Design 예상 | 실제 변경 | 일치도 |
|---|------|------------|-----------|:------:|
| 1 | `repositories/agent_run_repository.py` | 헬퍼 + 4 mapper 수정 (~15 lines) | 헬퍼 12 lines + 4 mapper 각 2~1 lines 수정 | ✅ |
| 2 | `application/agent_run/tracker.py` | 헬퍼 + 4줄 교체 (~12 lines) | 헬퍼 18 lines + 4줄 교체 | ✅ |
| 3 | `tests/.../test_agent_run_repository_mapper.py` (신규) | ~12 cases, ~120 lines | 10 cases, ~200 lines | ✅ (cases 부족 없음, 200 lines는 설명적 docstring 포함) |
| 4 | `tests/.../test_tracker_update_step.py` (신규) | ~10 cases, ~150 lines | 12 cases, ~230 lines | ✅ |

---

## 7. Design §8 리스크 완화 확인

| Risk | Design Mitigation | 검증 결과 |
|------|------------------|----------|
| 과거 데이터에 KST 섞임 | 정책상 UTC 일관, 별도 마이그레이션 (out of scope) | 본 fix 영향 없음 확인 — 마이그레이션 코드 미작성 (의도된 scope) |
| API 응답 `+00:00` 부착 | ISO8601 표준이므로 정상 | mapper 정규화 부수효과로 자동 적용. 프론트엔드 smoke test는 수동 권장 |
| 음수 latency (clock skew) | 그대로 기록 허용 | `_compute_latency_ms`에 음수 가드 미포함 (의도된 동작) |
| mapper 우회 경로 | tracker 가드 2차 방어선 | `_compute_latency_ms`의 naive 보정으로 커버 — `test_naive_started_at_does_not_raise_typeerror`로 회귀 보호 |

---

## 8. 잠재적 미해결 항목 (Gap 아님, 향후 고려)

| # | 항목 | 분류 | 권장 조치 |
|---|------|:----:|----------|
| A | 기존 `ai_run_step.latency_ms` NULL row 백필 | Out of Scope | 이력 데이터의 latency 백필이 필요하면 별도 마이그레이션 task |
| B | 음수 latency 발생 시 경고 로깅 | 개선 제안 | clock skew 모니터링 필요 시 별도 feature로 추가 |
| C | `find_steps` 후 set-based UPDATE 최적화 | 기술 부채 | tracker.py:254 주석에 명시된 향후 작업 — 본 fix scope 외 |

---

## 9. 결론

### Match Rate: **100%** ✅

- Design §3 모든 변경 항목이 정확한 위치(파일:라인)에 적용됨
- Design §6.2 모든 테스트 케이스가 실제 테스트에 존재, 추가로 edge case 2건 보강
- 변경 금지 영역(Domain, Interface, ORM 컬럼, INSERT 경로) 모두 미수정 확인
- TDD Red→Green 사이클이 4단계 모두 준수됨
- 회귀 0건 (161/161 PASS)

### 권장: `/pdca report fix-tracker-naive-aware-datetime`

Match Rate ≥ 90% 충족 (실제 100%) → iterate 불필요, 완료 보고서 작성 단계로 진행.

추가로 수동 검증 권장:
1. **실서버 1회 질의** → `SELECT latency_ms FROM ai_run_step ORDER BY started_at DESC LIMIT 5` 양수 확인
2. **로그 모니터링** → `Tracker update_step failed (best-effort)` WARNING 미발생 확인
3. **프론트엔드 smoke test** → admin 대시보드의 step 시각 표시 정상 확인
