# subagent-step-observability Design Document

> **Summary**: `track_step`이 기록 시점의 `callback._current_step_id`를 부모로, `RunContext.step_depth`+1을 깊이로 `ai_run_step`에 남기고(V079), latency는 진입 시각 monotonic 차로 계산한다. API는 평면 목록에 두 필드만 더하고, 프론트가 `buildStepTree`로 트리를 만들어 접기형 StepTree로 렌더한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-10-06
> **Status**: Draft (v0.1)
> **Planning Doc**: [subagent-step-observability.plan.md](../../01-plan/features/subagent-step-observability.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 서브에이전트 런의 실행 이력에서 부모·자식 step이 구분되지 않아 멀티 에이전트 디버깅이 불가능하고, 모든 step latency가 반올림 버그로 부정확(음수 포함)하다. |
| **WHO** | P2 — 멀티 에이전트를 조합·운영하며 실행 상세(/admin/agent-runs/:runId)로 검수하는 KB 운영자·에이전트 소유자. |
| **RISK** | `_current_step_id`가 노드 경계에서 복원되지 않으면 무관한 step이 자식으로 잘못 묶임 → 실런 트레이스로 전 step 부모 관계 검증. 마이그레이션은 컬럼 추가만(기존 행 NULL/0)이라 무중단. |
| **SUCCESS** | 실런(`[멀티] 문의 처리 매니저`)에서 자식 step 100%가 올바른 wrapper 아래 / 최상위 step parent 없음 / 자식 tool·llm call이 자식 step에 귀속 / 모든 latency ≥ 0 / StepTree 트리 렌더 / 회귀 0. |
| **SCOPE** | M1 마이그레이션+모델+엔티티 → M2 track_step 계층·latency → M3 API StepDto → M4 프론트 타입·StepTree 트리 → M5 L3 실런 검증. 스트리밍(실시간 진행)은 실측만. |

---

## 1. Overview

### 1.1 Design Goals
1. 부모 판별을 **이미 존재하는 enter/restore 계약**(`callback._current_step_id`)에 얹어, 컴파일러·서브에이전트 래퍼를 바꾸지 않는다.
2. 기록 실패가 실행을 막지 않는 기존 best-effort 계약을 그대로 지킨다.
3. API 계약은 **필드 추가만**(평면 목록 유지) — 과거 런·다른 소비자 무영향.

### 1.2 Design Principles
- 계층은 런타임 컨텍스트가 안다 — 저장소 재조회 없음.
- latency는 측정한 곳(track_step)이 계산한다 — DB 반올림값에 의존하지 않음.
- 트리 조립은 표현 계층(프론트 순수 함수)에서 — 백엔드 조립 로직·API 형태 불변.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | depth만 기록·들여쓰기 | 도메인 정책 + 백엔드 중첩 트리 API | 컨텍스트 depth + 평면 API + 프론트 트리 |
| **New Files** | 1 (V079) | 4 | 3 (V079, buildStepTree + 테스트) |
| **Modified Files** | 6 | 10 | 8 (백 6 + 프 2) |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (반복 호출 구분 약함) | High | High |
| **Risk** | 반복 호출 시 구간 모호 | API 계약 변경 | Low |

**Selected**: **Option C — Pragmatic** (Checkpoint 3). **Rationale**: 계약 변경 없이 트리를 정확히 복원하고, 기존 컨텍스트 전파 메커니즘을 재사용한다.

### 2.1 Component Diagram

```
WorkflowCompiler._wrap_step ──▶ track_step (application/agent_run/step_tracking.py)
                                   │ enter: parent = callback._current_step_id
                                   │        depth  = StepHierarchy(parent, ctx)
                                   │        t0     = time.monotonic()
                                   │ record_step(..., parent_step_id, depth)
                                   │ ctx' = with_step_id(ctx, step_id, step_depth=depth)
                                   │ exit : update_step(..., latency_ms=elapsed)
                                   ▼
                        RunTracker (record_step / update_step)  ──▶ ai_run_step (+parent_step_id, depth)
                                                                      │
GetRunDetailUseCase → StepDto(+parent_step_id, depth) 평면 ──▶ idt_front
                                                     buildStepTree(steps) → StepTree(재귀·접기)
```

### 2.2 Data Flow — 서브에이전트 1단 예시

```
parent supervisor        enter: parent=None        depth=0   → restore(None)
sub_agent wrapper        enter: parent=None        depth=0   ctx.step_depth=0, current=W
  ├ child supervisor     enter: parent=W           depth=1   → restore(W)
  ├ child list_inquiries enter: parent=W           depth=1   (tool_call.step_id = 이 step)
  └ child quality_gate   enter: parent=W           depth=1   → restore(W)
sub_agent wrapper exit   → restore(None)
parent supervisor        enter: parent=None        depth=0
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `track_step` | `callback._current_step_id`, `RunContext.step_depth` | 부모·깊이 판별 |
| `RunTracker.record_step/update_step` | 신규 선택 인자 | 계층·latency 저장 |
| `buildStepTree` | `StepDto.parent_step_id` | 트리 조립 |

---

## 3. Data Model

### 3.1 Migration — `db/migration/V079__add_hierarchy_to_ai_run_step.sql`

```sql
-- subagent-step-observability FR-01: 서브에이전트(자식 그래프) step 계층 기록
ALTER TABLE ai_run_step
    ADD COLUMN parent_step_id VARCHAR(36) NULL
        COMMENT '감싸는 부모 step id (서브에이전트 wrapper step). 최상위 step은 NULL. FK 없음 — 관측 best-effort',
    ADD COLUMN depth INT NOT NULL DEFAULT 0
        COMMENT '중첩 깊이 (0=최상위 그래프, 1=서브에이전트 내부, 2=손자)';
```

- 인덱스 추가 없음: 조회는 기존 `idx_step_run(run_id, step_index)`로 런 단위 전체를 읽고 트리는 앱에서 조립.
- FK 없음 (D-03).
- 기존 행: `parent_step_id` NULL, `depth` 0 → 평면 표시 (하위호환).

### 3.2 ORM / Entity / Mapper

| 위치 | 변경 |
|------|------|
| `infrastructure/persistence/models/agent_run.py` `AgentRunStepModel` | `parent_step_id: Mapped[str \| None] = mapped_column(String(36), nullable=True, comment=…)`, `depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment=…)` |
| `domain/agent_run/entities.py` `AgentRunStep` | 끝에 `parent_step_id: Optional[str] = None`, `depth: int = 0` (기본값 → 기존 생성부 무수정) |
| `agent_run_repository.py` `save_step`·`_step_to_domain`·`update_step` | 두 필드 매핑 (`update_step`은 계층 필드 갱신 안 함 — 생성 시 확정) |

### 3.3 RunContext — `application/agent_run/context.py`

```python
@dataclass(frozen=True)
class RunContext:
    ...
    step_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    step_depth: int = 0          # 신규 — 현재 활성 step의 깊이

def with_step_id(ctx, step_id, step_depth: int | None = None) -> RunContext:
    """step_depth 미지정 시 기존 값 유지 (기존 호출부 호환)."""
```

### 3.4 계층 판별 규칙 (H1~H4) — `step_tracking.py` 내부 순수 함수 `_resolve_hierarchy(parent_step_id, ctx) -> int`

| 규칙 | 정의 |
|------|------|
| **H1** | `parent_step_id = callback._current_step_id` (기록 직전 값). 최상위 노드는 직전 노드의 `_restore_context`로 None |
| **H2** | parent 없음 → depth 0 |
| **H3** | parent 있음 & `ctx.step_id == parent` → `ctx.step_depth + 1` |
| **H4** | parent 있음 & ctx 없음/불일치 → 1 (fallback, 관측 저하 허용) |

### 3.5 latency 규칙 (L1~L2)

| 규칙 | 정의 |
|------|------|
| **L1** | `track_step` 진입 시 `t0 = time.monotonic()`, 정상·예외 종료 모두 `latency_ms = max(0, int((monotonic()-t0)*1000))`를 `update_step`에 전달 |
| **L2** | `RunTracker.update_step(latency_ms=None)` — 전달값이 있으면 그대로 저장, 없으면 기존 `_compute_latency_ms`(하위호환) |

---

## 4. API Specification

### 4.1 Changed — `GET /api/v1/agents/runs/{run_id}` 응답 `steps[]` (`agent_run_router.py:149`)

`StepDto` (`interfaces/schemas/agent_run_response.py`) — 필드 추가만:

```python
parent_step_id: Optional[str] = None   # 감싸는 step id (최상위 None)
depth: int = 0                          # 0=최상위
```

목록은 기존과 같이 `step_index` 오름차순 평면. 트리 조립은 클라이언트 책임.

**다른 소비자 (변경 없음, 영향 기록)**: `GET /api/v1/admin/usage/by-node`(`agent_run_router.py:233`)는 node_name 기준 집계라 자식 그래프의 `supervisor`·`quality_gate`가 부모와 같은 버킷에 합산된다. 이번 사이클은 현행 유지(집계 의미 변경은 별도 결정) — 필요 시 다음 사이클에서 `depth`로 분리 집계.

### 4.2 Frontend Type — `idt_front/src/types/agentRunAdmin.ts`

```ts
export interface StepDto {
  ...
  parent_step_id: string | null;
  depth: number;
}

export interface StepTreeNode {   // buildStepTree 산출
  step: StepDto;
  children: StepTreeNode[];
}
```

---

## 5. UI/UX Design

### 5.1 Screen — 실행 상세 > Steps

```
#1  supervisor            [SUPERVISOR] SUCCESS          4.6s
#2  sub_agent_[멀티]_문의_분석가_0 [WORKER] SUCCESS  ▾ 하위 8   30.5s
    │ #3  supervisor      [SUPERVISOR] SUCCESS          3.4s
    │ #4  mcp_…list_inquiries_worker [WORKER] SUCCESS  11.9s
    │      🔧 list_inquiries …
    │ #5  quality_gate    [GATE] SUCCESS                0.1s
    │ …
#11 supervisor            [SUPERVISOR] SUCCESS          7.8s
#12 sub_agent_[멀티]_답변_작성자_1 [WORKER] SUCCESS  ▸ 하위 2 (접힘)
```

### 5.2 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `buildStepTree` | `idt_front/src/utils/buildStepTree.ts` (신규) | 평면 steps → 트리. `step_index` 순서 보존, 부모가 목록에 없으면(기록 실패) 최상위로 승격 |
| `StepTree` | `pages/AgentRunDetailPage/components/StepTree.tsx` | 트리 재귀 렌더, 자식 있는 step에 접기 토글·"하위 N" 배지, depth별 좌측 들여쓰기 + 세로선 |

### 5.3 Page UI Checklist — AgentRunDetailPage Steps

- [ ] Step 행: `#{step_index}`, node_name, `[node_type]`, StatusBadge, latency (기존 유지)
- [ ] 자식 있는 step: 토글 버튼(▾/▸, `aria-expanded`), "하위 N" 배지 (N = 직속+모든 하위 수)
- [ ] 자식 블록: 부모 아래 들여쓰기 + 좌측 세로선
- [ ] 기본 상태: 모두 펼침
- [ ] tool_calls·llm_calls는 각 step 아래 기존 방식 유지
- [ ] 과거 런(parent 없음): 평면 목록 그대로 (토글 없음)
- [ ] orphan LLM calls 블록 유지

---

## 6. Error Handling

| 상황 | 처리 |
|------|------|
| wrapper `record_step` 실패 → step_id None | 자식은 `_current_step_id`가 바깥 값(None)이라 최상위로 기록 — 관측 저하, 실행 무영향 (Plan RISK) |
| 프론트: 부모 id가 목록에 없음 | `buildStepTree`가 최상위로 승격 (데이터 유실 대신 평면 표시) |
| 순환(이론상 불가) | `buildStepTree`가 방문 집합으로 방지, 순환 노드는 최상위로 |
| latency 음수 가능성 | monotonic이라 불가, 방어로 `max(0, …)` |

---

## 7. Security Considerations

- [ ] 신규 컬럼·필드는 내부 id·정수뿐 — 노출 정보 증가 없음. 런 상세 API 기존 권한(admin) 그대로.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit (BE) | `_resolve_hierarchy` H1~H4, `track_step` 계층·latency·예외 경로, `with_step_id`, tracker 인자, 매퍼 | pytest |
| DDL | V079 COMMENT | `tests/db/test_migration_ddl_comments.py` |
| API | `StepDto` 직렬화 (필드 포함·기본값) | pytest |
| Unit (FE) | `buildStepTree` | vitest |
| Component (FE) | StepTree 들여쓰기·토글·평면 하위호환 | vitest + RTL |
| L3 | `[멀티] 문의 처리 매니저` 시나리오 2 실런 | 인프로세스 TestClient + DB 조회 |

### 8.2 Backend Unit

| # | Case | Expected |
|---|------|----------|
| B1 | 최상위 노드 (current None) | parent None, depth 0 |
| B2 | 중첩 track_step 2단 (wrapper 안 child) | child.parent = wrapper id, depth 1 |
| B3 | 3단 (wrapper > wrapper > child) | depth 2, parent = 안쪽 wrapper |
| B4 | child 종료 후 다음 형제 | 형제 parent도 wrapper (restore 확인) |
| B5 | wrapper 종료 후 다음 최상위 노드 | parent None, depth 0 |
| B6 | child가 예외로 종료 | 복원 정상, 다음 노드 parent 정상 |
| B7 | ctx 없음 + parent 있음 | depth 1 (H4) |
| B8 | latency: 노드 50ms sleep | update_step에 latency_ms ≈ 50 (≥0, 오차 범위) — DB started_at 미사용 |
| B9 | `update_step(latency_ms=None)` | 기존 계산 경로 유지 |
| B10 | record_step 실패 | 실행 계속, 자식 parent는 바깥 값 |
| B11 | `with_step_id(ctx, sid)` 기존 호출 | step_depth 유지 |
| B12 | repo save/load | parent_step_id·depth 왕복 |
| B13 | StepDto | 두 필드 직렬화, 기본값 None/0 |

### 8.3 Frontend

| # | Case | Expected |
|---|------|----------|
| F1 | buildStepTree 평면(전부 parent null) | 루트 N개, children 없음 |
| F2 | 2단·3단 | 올바른 중첩, step_index 순서 보존 |
| F3 | 부모 id가 목록에 없음 | 최상위로 승격 |
| F4 | StepTree: 자식 있는 step | 토글·"하위 N" 표시, 기본 펼침 |
| F5 | 토글 클릭 | 자식 숨김, `aria-expanded=false` |
| F6 | 과거 런(평면) | 토글 없음, 기존 렌더 |

### 8.4 L3 실런 — `[멀티] 문의 처리 매니저` 시나리오 2

| # | Check | Success |
|---|-------|---------|
| L3-1 | 분석가 내부 step(supervisor·list_inquiries·get_inquiry·quality_gate) | 전부 parent = 분석가 wrapper id, depth 1 (SC-1) |
| L3-2 | 작성자 내부 step | 전부 parent = 작성자 wrapper id, depth 1 (SC-1) |
| L3-3 | 최상위 supervisor·wrapper | parent NULL, depth 0 (SC-2) |
| L3-4 | tool_call(list_inquiries·get_inquiry) step_id | 자식 step id (SC-3) |
| L3-5 | 전 step latency_ms | ≥ 0 (SC-4) |
| L3-6 | 스트리밍 섞임 실측(FR-09) | `/run/stream` 이벤트의 node_name 시퀀스 기록 — 수정 없음 |
| L3-7 | 화면 | 실행 상세에서 트리·접기 확인 (SC-5) |

### 8.5 L3 실행 결과 (2026-10-06, run `8863101d`, WebSocket `/ws/agent/{room}`, gpt-5.1)

| # | 결과 | 근거 |
|---|:---:|------|
| L3-1 | ✅ | 분석가 내부 7 step(#3~#9: supervisor×3·list_inquiries_worker·get_inquiry_worker·quality_gate×2) 전부 parent = 분석가 wrapper(#2), depth 1 |
| L3-2 | ✅ | 작성자 내부 2 step(#13 supervisor, #14 submit_reply_worker) parent = 작성자 wrapper(#12), depth 1 |
| L3-3 | ✅ | 최상위 5 step(#1·#2·#10·#11·#12) parent NULL, depth 0 |
| L3-4 | ✅ | tool_call 2건(list_inquiries·get_inquiry) → depth 1 자식 step 귀속. llm_call도 각 자식 step(depth 1)에 귀속 |
| L3-5 | ✅ | 14 step 전부 latency ≥ 0 (quality_gate 0ms·16ms — 이전 −122ms·−476ms 사례 해소) |
| L3-6 | ⚠ 기록 | **스트리밍(WS)에 자식 노드가 섞인다**: 자식 `supervisor`·`quality_gate`가 부모와 같은 이름의 `agent_node_started/completed`로 흘러나오고 계층 표식이 없다. 자식 도구 워커 노드는 node 이벤트로 안 나오고 tool 이벤트로만 나온다 → 다음 사이클 후보 (D-08) |
| L3-7 | — | 화면 확인은 사용자 확인 대기 (컴포넌트 테스트 F4~F6 통과) |
| 부수 발견 | ⚠ | SSE `GET /{agent_id}/run/stream`은 `get_auth_context_from_query_token` placeholder(`Depends(lambda: None)`)가 main.py에서 교체되지 않아 **항상 401** — 프론트는 WS를 쓰므로 실사용 영향 없음, master 상시 실패 `test_agent_builder_router_stream` 9건과 일치. 범위 밖 |

---

## 9. Clean Architecture — Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `AgentRunStep` 필드 | Domain | `src/domain/agent_run/entities.py` |
| `RunContext.step_depth`, `with_step_id` | Application | `src/application/agent_run/context.py` |
| `_resolve_hierarchy`, `track_step` | Application | `src/application/agent_run/step_tracking.py` |
| `RunTracker` 인자 | Application | `src/application/agent_run/tracker.py` |
| ORM·매퍼·V079 | Infrastructure | `models/agent_run.py`, `agent_run_repository.py`, `db/migration/` |
| `StepDto` | Interfaces | `src/interfaces/schemas/agent_run_response.py` |
| `buildStepTree`, `StepTree` | Frontend | `idt_front/src/utils/`, `pages/AgentRunDetailPage/components/` |

---

## 10. Coding Convention Reference

| Item | Convention |
|------|-----------|
| DDL | 전 컬럼 COMMENT + ORM `comment=` |
| 함수 | 40줄 이하 — `track_step`이 길어지면 enter/exit 보조 함수로 분리 |
| 프론트 상수 | 컴포넌트 파일 런타임 상수 export 금지, 타입은 `src/types` |
| 주석 | `# Design Ref: subagent-step-observability §3.4 H1 — …` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/db/migration/V079__add_hierarchy_to_ai_run_step.sql            (신규)
idt/src/domain/agent_run/entities.py                               (수정)
idt/src/infrastructure/persistence/models/agent_run.py             (수정)
idt/src/infrastructure/persistence/repositories/agent_run_repository.py (수정)
idt/src/application/agent_run/context.py                           (수정)
idt/src/application/agent_run/step_tracking.py                     (수정)
idt/src/application/agent_run/tracker.py                           (수정)
idt/src/interfaces/schemas/agent_run_response.py                   (수정)
idt_front/src/types/agentRunAdmin.ts                               (수정)
idt_front/src/utils/buildStepTree.ts (+ .test.ts)                  (신규)
idt_front/src/pages/AgentRunDetailPage/components/StepTree.tsx (+ .test.tsx) (수정/신규)
```

### 11.2 Implementation Order (TDD)

1. [ ] B12·DDL 테스트 Red → V079·ORM·엔티티·매퍼
2. [ ] B1~B11 Red → context·track_step·tracker
3. [ ] B13 Red → StepDto
4. [ ] F1~F6 Red → 타입·buildStepTree·StepTree
5. [ ] 로컬 DB에 V079 적용 → L3-1~7 실런
6. [ ] 백엔드 전체 회귀(기준선 53 대조), 프론트 vitest·수정 파일 lint/tsc

### 11.3 Session Guide

| Module | Scope Key | Description | Est. Turns |
|--------|-----------|-------------|:---:|
| DB·모델 | `module-1` | V079, ORM, 엔티티, 매퍼 + B12·DDL | 4~6 |
| 기록 | `module-2` | context·track_step·tracker + B1~B11 | 6~8 |
| API·프론트 | `module-3` | StepDto(B13), 타입, buildStepTree, StepTree + F1~F6 | 6~8 |
| 검증 | `module-4` | 로컬 V079 적용 + L3-1~7 + 회귀 | 5~7 |

Recommended: 세션 1 `--scope module-1,module-2` / 세션 2 `--scope module-3,module-4`

---

## 12. Decision Record

| ID | Decision | Rationale |
|----|----------|-----------|
| D-01 | Option C | 계약 변경 없이 정확한 트리 (Checkpoint 3) |
| D-02 | 부모 = `callback._current_step_id` | 기존 enter/restore 계약 재사용, 컴파일러·래퍼 무변경 |
| D-03 | `parent_step_id` FK 없음 | best-effort 관측 — 부모 기록 실패가 자식 INSERT 실패로 번지지 않게 (사용자 선택) |
| D-04 | depth를 `RunContext.step_depth`로 전파 | contextvar가 자식 그래프까지 따라감, DB 조회 불필요 |
| D-05 | latency = track_step monotonic, `update_step`은 전달값 우선 | DB 반올림 의존 제거, 기존 경로 하위호환 |
| D-06 | API 평면 유지, 트리는 프론트 `buildStepTree` | 다른 소비자·과거 런 무영향 |
| D-07 | 부모 미발견 노드는 최상위로 승격 | 기록 실패 시에도 step 유실 없이 표시 |
| D-08 | 스트리밍은 실측만(FR-09) | Plan 범위 결정 |
| D-09 | `/admin/usage/by-node` 집계는 현행 유지 | 집계 의미(부모+자식 합산) 변경은 사용자 결정 사항 — 후속 후보로 기록 |
| D-10 | (Q-D3 실측) 승인 재개 런은 별도 처리 없음 | `RunAgentUseCase.resume_from_snapshot`(`run_agent_use_case.py:804`)도 `compile(tracker=…)`(:930) → `_wrap_step` → `track_step` 동일 경로라 계층·latency 기록이 그대로 적용된다. 재개 런에서 서브에이전트 내부가 다시 실행되면 같은 규칙으로 parent/depth가 남는다 (재개 런 실런 검증은 승인 실행이 실제 문의 답변을 등록하므로 미수행) |
| D-11 | (Check G-2) `buildStepTree` 순환 승격을 방문 집합 기반으로 | 자기참조만 막던 초안은 A→B→A에서 두 노드가 화면에서 사라졌다 — 부모 체인이 자기에게 돌아오면 최상위로 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-06 | Initial draft — Option C, FK 없음, Q-D1~D4 실측 확정 | 배상규 |
| 0.2 | 2026-10-07 | §8.5 L3 결과, D-10(Q-D3 재개 경로 기록 — Check G-1), D-11(순환 승격 — Check G-2) | 배상규 |
