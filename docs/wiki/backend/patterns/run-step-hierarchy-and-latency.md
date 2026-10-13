---
title: ai_run_step 계층(parent_step_id·depth)과 latency — 기록 시점 컨텍스트 재사용, monotonic 측정
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/application/agent_run/step_tracking.py (_resolve_hierarchy H1~H4, _elapsed_ms, track_step)
  - idt/src/application/agent_run/tracker.py (_compute_latency_ms — 전달값 없을 때만 쓰는 하위호환 경로)
  - idt/db/migration/V079__add_hierarchy_to_ai_run_step.sql (FK 없음, 기존 행 NULL/0)
  - idt_front/src/utils/buildStepTree.ts (평면→트리, 부모 미발견·순환 승격)
  - idt/docs/archive/2026-10/subagent-step-observability/subagent-step-observability.design.md (§3.4 H1~H4, §3.5 L1~L2, §8.5 L3, §12 D-01~D-11)
  - idt/docs/archive/2026-10/subagent-step-observability/subagent-step-observability.report.md
  - 커밋 405e91c, 50fc7eb
confidence: 0.85
version: 1
created: 2026-10-13
updated: 2026-10-13
verified_at: 3b6353b
---

# ai_run_step 계층(parent_step_id·depth)과 latency — 기록 시점 컨텍스트 재사용, monotonic 측정

> 읽는 시점: **실행 관측(ai_run_*)에 새 step·노드 기록을 추가할 때**, `ai_run_step`을 집계·조회하는
> 코드를 쓸 때, 서브에이전트 런 이력이 "평평하게 섞여" 보일 때, 그리고 **DB 타임스탬프 차로 경과
> 시간을 계산하려 할 때**(하지 말 것).

## 문제

서브에이전트 런에서 자식 그래프의 `supervisor`·`quality_gate`·워커 step이 부모와 같은 이름으로
평면에 섞여(실런 14 step 중 8~9개가 자식) 누가 무엇을 했는지 알 수 없었다. 조사 중 **모든 step의
latency가 틀려 있던 기존 버그**도 드러났다 — 1초 미만 step이 −122ms·−476ms로 기록.

## 검증된 사실

### 1. 부모는 "기록 직전의 `callback._current_step_id`" — 컴파일러·래퍼 무변경

`track_step`은 이미 enter/restore로 "현재 활성 step"을 정확히 들고 있다. 서브에이전트 wrapper 노드
안에서 자식 그래프 노드가 시작되면 그 시점의 `_current_step_id`가 wrapper step이고, 최상위 노드는
직전 노드의 `_restore_context`로 None이다(H1). 그래서 `parent_step_id`는 이 값, `depth`는
`RunContext.step_depth + 1`로 기록만 하면 됐다 — `WorkflowCompiler`·서브에이전트 래퍼는 한 줄도 안 바꿨다.

| 규칙 | 정의 |
|------|------|
| H2 | parent 없음 → depth 0 |
| H3 | parent 있음 & `ctx.step_id == parent` → `ctx.step_depth + 1` (손자 그래프 depth 2까지 검증) |
| H4 | parent 있음 & ctx 없음/불일치 → 1 (관측 저하 허용) |

승인 재개 런(`resume_from_snapshot`)도 같은 `compile(tracker=…) → track_step` 경로라 별도 처리 없음(D-10).
자식 tool·llm call은 기존 `enter_step` 귀속이 그대로 동작해 코드 변경 0.

### 2. `parent_step_id`에 FK를 두지 않는다 (D-03)

관측은 best-effort다 — wrapper 기록이 실패하면 자식은 최상위로 남아야지 INSERT가 함께 실패하면 안 된다.
기존 행은 NULL/0으로 평면 해석(하위호환). 인덱스 추가 없음: 런 단위로 전부 읽고 트리는 앱에서 조립.

### 3. latency는 `time.monotonic()` 측정값을 저장한다 — DB 재조회 금지

기존 `update_step`은 DB에서 재조회한 `started_at`(MySQL `DATETIME` **초 반올림**)과 정밀한 `ended_at`의
차로 계산해 ±500ms 오차가 났고 1초 미만은 음수가 됐다. 지금은 `track_step` 진입 시 `monotonic()`을
잡고 정상·예외 종료 모두 `max(0, 경과ms)`를 `update_step(latency_ms=)`로 전달한다(L1).
`_compute_latency_ms`는 전달값이 없을 때만 쓰는 하위호환 경로(L2). `DATETIME(3)` 전환은 하지 않았다.

**일반화**: 두 DB 타임스탬프의 차로 경과 시간을 만들지 말 것. 측정은 메모리에서, DB는 결과만 저장.

### 4. API는 평면 유지, 트리는 프론트 `buildStepTree` (D-06/07)

`StepDto`에 `parent_step_id`·`depth` 필드만 추가(additive). `buildStepTree`는 `step_index` 순을 형제
순서로 쓰고, **부모가 목록에 없거나(기록 실패) 순환(자기참조 포함)이면 최상위로 승격**해 step을 잃지
않는다. 순환 방어를 자기참조로만 좁혔다가 Check에서 잡혀 방문 집합으로 확장했다(G-2) —
Design §6 각 행을 테스트 ID와 1:1로 묶지 않은 탓.

### 5. 아직 안 된 것 (실측으로 기록)

- **실시간 진행(WS) 이벤트에는 계층이 없다**: 자식 `supervisor`·`quality_gate`가 부모와 같은 이름의
  `agent_node_started/completed`로 흘러나오고, 자식 도구 워커는 node 이벤트 없이 tool 이벤트만 나온다(D-08, 후속 후보).
- `GET /api/v1/admin/usage/by-node`는 node_name 집계라 자식 `supervisor`가 부모 버킷에 합산된다(D-09, 현행 유지).
- SSE `/run/stream`은 인증 placeholder 미배선으로 항상 401(상시 실패 9건의 원인) — 프론트는 WS를 쓴다.
  실런은 처음부터 WS 경로로.

## 다음에 적용하는 법

1. 새 노드 유형을 추가하면 `track_step`으로 감싸기만 하면 계층·latency가 자동으로 맞는다 —
   `callback._current_step_id`를 직접 만지는 우회 경로를 만들지 말 것.
2. `ai_run_step`을 집계할 때 "부모만" 또는 "자식만"이 필요하면 `depth`로 거른다(`depth=0`이 최상위).
3. 운영 DB에 **V079 적용**이 선행이다([[migration-deploy-deps]]) — 모델에 컬럼이 매핑돼 있어 미적용 시
   step 조회 자체가 깨진다.
4. 경과 시간·지연을 기록하는 새 코드는 `_elapsed_ms` 방식(monotonic)을 따른다.

## 관련 문서

- 서브에이전트 런타임 계약: `backend/patterns/supervisor-graph-contracts.md`
- 조감도 (b) 경로의 RunTracker: `backend/architecture-overview.md`
- 관리자 런 상세 화면: `frontend/screens/admin-screens.md`
