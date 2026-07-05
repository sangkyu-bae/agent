# Gap Analysis: agent-schedule

> Analyzed: 2026-07-03 (gap-detector)
> Design: [agent-schedule.design.md](../02-design/features/agent-schedule.design.md)
> Plan: [agent-schedule.plan.md](../01-plan/features/agent-schedule.plan.md)

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 97% | ✅ |
| Architecture (Thin DDD / DB-001) Compliance | 100% | ✅ |
| Test Plan Coverage (§8) | 95% | ✅ |
| **Overall Match Rate** | **96%** | ✅ (≥90%) |

신규 테스트 110개 전부 통과. verify-architecture / verify-logging / verify-tdd 모두 PASS.

## 항목별 판정 요약

| Design 섹션 | 판정 |
|-------------|------|
| §1.3 확정 결정 7건 (croniter domain, 10분 가드, zoneinfo, SKIP LOCKED, session_factory, trigger status, R9 치환 3종) | 7/7 Match |
| §3 Domain (Spec 매트릭스, Policy 상수/메서드, Entity, 인터페이스 3종) | Match |
| §4 Infrastructure (ORM↔V038 1:1, claim_due, Sink 짧은 트랜잭션) | Match |
| §5 Application (CRUD 7종 권한/상한/재계산/cap, Trigger 실패 격리) | Match (중 1건, 아래) |
| §6 Interfaces (엔드포인트 9종, 토큰 503/401, DI 배선, config) | Match |
| §7 DDL (테이블 2종, CASCADE, 인덱스 4종) | Match |
| §8 테스트 플랜 (자정 경계, once 소진, 실패 격리, 포크 회귀, R9 렌더링) | Match |

## Gap 목록

### 🔵 Changed (Design ≠ Implementation)

| # | 항목 | 설계 | 구현 | 위치 | 심각도 |
|---|------|------|------|------|:------:|
| 1 | last_run_at 갱신 시점 | §2.2: 회차 실행 후 갱신 (성공/실패 무관 해석 여지) | **성공 경로에서만** 갱신, 실패 시 미갱신 | `trigger_due_schedules_use_case.py:109` | **중** |
| 2 | TriggerUC 시그니처 | `(session_factory, run_agent_uc_builder, sink, logger)` | `schedule_repo_builder` 파라미터 추가 (application의 infra 무참조화 — 개선) | 동 파일 `:38` | 하 |

### 🟡 Added (설계에 없던 긍정적 additive)

- `SchedulePolicy.validate_instruction` (빈값/1900자 도메인 검증)
- `RENDERED_QUERY_MAX_LENGTH=2000` 상수, `TriggerStatusResponse` 스키마
- `ScheduleRunRepositoryInterface.find_by_id`
- Trigger→RunAgentUseCase 호출에 `request_id, viewer_user_id` 전달 (실제 시그니처 정합)

### ⚪ 경미 관찰 (Gap 아님)

- 라우터 prefix `/api/v1` — 기존 컨벤션과 일치 (설계는 축약 표기)
- `PLACEHOLDERS` 클래스 상수 미노출 (render 내부 인라인, 기능 동일)
- SKIP LOCKED 실제 동시성의 MySQL 통합 테스트 마킹 부재 (mock 단위 테스트만)
- render 기준 시각이 claim now 가 아닌 실행 시점 재호출 (ms 단위 오차, 무시 가능)

## Recommended Actions

1. **[중] last_run_at 정책 결정 필요 (사용자 판단)**
   - A안: "실행 시도 = 기록" → 실패 분기에도 `_touch_last_run` 호출
   - B안: "성공만 기록" (현 동작) → Design §2.2 문구를 현 동작으로 명시
2. **[하] 문서 동기화**: Design §3.2 `validate_instruction` 추가, §5.2 시그니처에 `schedule_repo_builder` 반영, §6.1 `/api/v1` prefix 명시
3. **[하] `PLACEHOLDERS` 상수화** 또는 설계에서 제거

## 결론

Match Rate **96% ≥ 90%** — pdca-iterator 자동 개선 불필요. [중] 1건은 정책 결정 사항이므로 수동 판단 후 `/pdca report agent-schedule` 진행 권장.

---

## Act 반영 결과 (2026-07-03, 사용자 결정: A안)

| # | 조치 | 상태 |
|---|------|:----:|
| 1 | **[중] last_run_at = A안 확정**: `_run_one`에서 성공/실패 공통 경로로 `_touch_last_run` 이동 + 실패 시 갱신 테스트 추가 (`test_failed_run_also_touches_last_run`) | ✅ 해소 |
| 2 | **[하] Design 동기화**: §2.2 A안 문구, §3.2 `validate_instruction`·`RENDERED_QUERY_MAX_LENGTH`, §5.2 `schedule_repo_builder` 시그니처, §6.1 `/api/v1` prefix | ✅ 해소 |
| 3 | **[하] `PLACEHOLDERS` 상수화**: `SchedulePolicy.PLACEHOLDERS` 노출 + `render_instruction`이 상수 순회로 치환 (Design §3.2와 단일 출처) | ✅ 해소 |
| 4 | **[하] SKIP LOCKED MySQL 통합 테스트 마킹** | ⏳ 후속 (배포 환경 검증 시) |

반영 후 테스트 **111개 전부 통과**. 잔여 갭은 통합 테스트 마킹 1건(하)뿐 — **최종 Match Rate 98%**.
