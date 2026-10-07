# subagent-step-observability Planning Document

> **Summary**: 서브에이전트(자식 그래프) 실행 step이 부모 런의 `ai_run_step`에 평평하게 섞여 기록돼 부모·자식을 구분할 수 없는 문제를 고친다. `ai_run_step`에 `parent_step_id`·`depth`를 추가해 계층을 기록하고, 실행 상세 화면(StepTree)을 들여쓰기·접기 트리로 바꾼다. 함께 모든 step의 latency가 초 단위 반올림 때문에 틀어지는(음수 포함) 기존 버그를 메모리 기준 계산으로 고친다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-10-06
> **Status**: Draft (v0.1)
> **Depends on**: subagent-context-scope (아카이브 2026-10), AGENT-OBS-003 (step tracking)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 서브에이전트를 쓰는 런에서 자식의 `supervisor`·`quality_gate`·워커 step이 부모 step과 같은 이름으로 한 목록에 섞인다(실런 `2397af25`: 14 step 중 8개가 자식 내부인데 구분 불가). 또 모든 step의 latency가 `DATETIME`(초) 반올림 때문에 최대 ±500ms 틀어지고, 1초 미만 step은 음수(−122ms, −476ms)로 찍힌다. |
| **Solution** | `track_step`이 기록 시점의 `callback._current_step_id`(= 감싸고 있는 서브에이전트 wrapper step)를 `parent_step_id`로, 부모 depth+1을 `depth`로 남긴다(V079 마이그레이션). latency는 DB 재조회값 대신 `track_step`이 들고 있는 시작 시각(monotonic)으로 계산한다. API `StepDto`에 두 필드를 싣고 StepTree를 트리로 렌더한다. |
| **Function/UX Effect** | 실행 상세 화면에서 서브에이전트 step 아래에 자식 step(supervisor·도구 워커·도구/LLM 호출)이 들여쓰기로 묶여 보이고 접고 펼 수 있다. latency가 항상 0 이상·ms 정확도로 표시된다. |
| **Core Value** | 멀티 에이전트 런을 운영자(P2)가 디버깅·검수할 수 있게 된다 — "어느 에이전트가 무엇을 했는가"가 실행 이력만으로 읽힌다. |

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

### 1.1 Purpose
멀티 에이전트 런의 실행 이력을 계층으로 기록·표시하고, step latency를 정확하게 만든다.

### 1.2 Background (코드 실측, 2026-10-06 / master `5154de4`)

| 지점 | 현재 동작 |
|------|-----------|
| `workflow_compiler.py` `_wrap_step` → `step_tracking.track_step` | 모든 노드가 `ai_run_step` 1행. 자식 그래프도 같은 tracker·callback·run_id로 컴파일돼 **같은 런에 평평하게** 쌓임 |
| `ai_run_step` (V021) | 계층 컬럼 없음 (`id, run_id, step_index, node_name, node_type, …, started_at DATETIME, ended_at DATETIME, latency_ms`) |
| `track_step` | enter 시 `prev_step_id = callback._current_step_id` 보관 → 노드 실행 → `_restore_context`로 복원. **자식 노드 시작 시점의 `_current_step_id` = 감싸는 서브에이전트 wrapper step id**, 최상위 노드는 None |
| `tracker.update_step` | DB에서 step을 **다시 읽어** `started_at`(초 단위 반올림)과 메모리상 `ended_at`(정밀)의 차로 latency 계산 → ±500ms 오차, 1초 미만 step은 음수 가능 |
| `StepTree.tsx` | 이름과 달리 step 평면 목록 (`#step_index node_name [type]`) |
| 스트리밍(`astream_events` → `agent_node_started`) | `node_names`(부모 그래프 노드 이름) 매칭 — 자식 `supervisor`가 부모 `supervisor`와 이름이 같아 섞일 가능성 (미실측) |

실측 런 `2397af25` (14 step): step 3~10은 분석가 내부, 13~14는 작성자 내부지만 이름만으로 구분 불가. quality_gate latency −122ms.

### 1.3 Related Documents
- `docs/archive/2026-10/subagent-context-scope/` — 보고서 §4.1 "자식 그래프 step 관측 구분" 후속 항목
- V021 `create_agent_run_tables.sql`, AGENT-OBS-003 (step tracking)

---

## 2. Scope

### 2.1 In Scope
- [ ] **FR-01 마이그레이션 V079**: `ai_run_step`에 `parent_step_id VARCHAR(36) NULL`(감싸는 step id), `depth INT NOT NULL DEFAULT 0` 추가. 테이블·컬럼 COMMENT 필수(`test_migration_ddl_comments`), ORM `comment=` 동일 반영
- [ ] **FR-02 엔티티·매퍼**: 도메인 `AgentRunStep`·ORM 모델·리포지토리 매퍼에 두 필드 반영 (기존 행은 None/0으로 읽힘)
- [ ] **FR-03 계층 기록**: `track_step`이 기록 시점 `callback._current_step_id`를 `parent_step_id`로, 부모 step depth+1을 `depth`로 넘긴다. 최상위는 None/0
- [ ] **FR-04 latency 정확화**: `track_step`이 진입 시각(monotonic)을 보관하고 종료 시 `latency_ms`를 계산해 `update_step`에 전달. `update_step`은 전달값이 있으면 그것을 쓴다(DB 재조회 반올림값 미사용). 모든 step에 적용
- [ ] **FR-05 API**: `StepDto`에 `parent_step_id: str | None`, `depth: int = 0` 추가 (하위호환 — 필드 추가만)
- [ ] **FR-06 프론트 타입**: `idt_front/src/types/agentRunAdmin.ts` `StepDto` 동기화 (API 계약 동기화 규칙)
- [ ] **FR-07 StepTree 트리**: `parent_step_id`로 트리 구성, depth 들여쓰기, 서브에이전트 step 접기/펼치기(기본 펼침), 자식 수 배지. 기존 tool/llm call 표시는 각 step 아래 유지
- [ ] **FR-08 귀속 검증**: 자식 노드 안의 tool_call·llm_call이 자식 step id에 귀속되는지 실런으로 확인(코드 변경은 문제 발견 시에만)
- [ ] **FR-09 스트리밍 실측**: 실시간 진행 이벤트에 자식 노드가 섞이는지 실런으로 확인하고 결과를 기록(수정은 다음 사이클)

### 2.2 Out of Scope
- 실시간 진행(스트리밍) 이벤트의 부모/자식 구분 수정 — 실측 결과에 따라 다음 사이클
- `ai_run_step.agent_id` 컬럼 (사용자 선택: parent_step_id·depth만)
- `started_at/ended_at` 정밀도 변경(DATETIME(3)) — 사용자 선택: 메모리 계산만
- `ai_tool_call`·`ai_llm_call`의 latency 계산 방식 (별도 경로)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | V079: `parent_step_id`, `depth` 컬럼 + COMMENT | High | Pending |
| FR-02 | 엔티티·ORM·매퍼 반영 | High | Pending |
| FR-03 | `track_step` 계층 기록 (`_current_step_id` 기반) | High | Pending |
| FR-04 | latency 메모리 기준 계산 (전 step) | High | Pending |
| FR-05 | `StepDto` 필드 추가 | High | Pending |
| FR-06 | 프론트 `StepDto` 타입 동기화 | High | Pending |
| FR-07 | StepTree 트리 렌더 (들여쓰기·접기·자식 수) | Medium | Pending |
| FR-08 | 자식 tool/llm call 귀속 실런 검증 | Medium | Pending |
| FR-09 | 스트리밍 섞임 실측·기록 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 무중단 | 컬럼 추가만, 기존 행 NULL/0 — 기존 런 상세 정상 표시 | 마이그레이션 적용 후 과거 run 상세 API 조회 |
| 관측 best-effort | 계층·latency 기록 실패가 노드 실행을 막지 않음 (기존 best-effort 계약 유지) | 단위 테스트 (record 실패 시 진행) |
| 레이어 | domain 엔티티는 외부 의존 없음 | `/verify-architecture` |
| DDL | 테이블·전 컬럼 COMMENT | `tests/db/test_migration_ddl_comments.py` |
| 프론트 | 기존 vitest 상시 실패 목록 외 신규 실패 0, 수정 파일 lint·tsc 신규 오류 0 | vitest diff, 수정 파일 lint |

---

## 4. Success Criteria

### 4.1 Definition of Done
- [ ] SC-1: 실런(`[멀티] 문의 처리 매니저`, 시나리오 2)에서 자식 step 전부가 자신을 감싼 서브에이전트 wrapper step을 `parent_step_id`로 가진다 (분석가 내부 step → 분석가 wrapper, 작성자 내부 → 작성자 wrapper)
- [ ] SC-2: 최상위 step(부모 supervisor·wrapper·quality_gate)은 `parent_step_id` NULL, `depth` 0
- [ ] SC-3: 자식 내부 tool_call(list_inquiries·get_inquiry)·llm_call이 자식 step id에 귀속
- [ ] SC-4: 실런 전 step `latency_ms ≥ 0`, 단위 테스트로 1초 미만 step 정확도 확인
- [ ] SC-5: StepTree가 서브에이전트 step 아래 자식을 들여쓰기로 표시·접기 가능 (vitest + 실제 화면 확인)
- [ ] SC-6: 과거 런(컬럼 NULL) 상세가 평면으로 정상 표시 (하위호환)
- [ ] SC-7: 백엔드 전체 회귀 신규 실패 0 (master 기준선 53건 대조), 프론트 상시 실패 목록 외 신규 0

### 4.2 Quality Criteria
- [ ] TDD(Red→Green), 신규 모듈 테스트 존재
- [ ] 함수 40줄·if 중첩 2단계

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `_current_step_id`가 어떤 경로에서 복원되지 않아 무관 step이 자식으로 묶임 | High | Low | 예외 경로 포함 복원 계약 단위 테스트 + 실런에서 전 step 부모 관계 전수 검증(SC-1·2) |
| record_step 실패(best-effort)로 wrapper step id가 None → 자식이 최상위로 기록 | Low | Low | 의도된 저하(관측 실패 ≠ 실행 실패). depth만으로도 구분 가능하게 depth는 컨텍스트에서 독립 계산 |
| 승인 재개 런(`resume_from_snapshot`)에서 계층이 끊김 | Medium | Medium | Design에서 재개 경로 step 기록 방식 실측 — 범위는 기록만, 수정은 판단 후 |
| latency 계산 변경이 기존 테스트의 `_compute_latency_ms` 기대와 충돌 | Low | Medium | 전달값 우선·미전달 시 기존 계산 유지(하위호환) |
| 프론트 트리 렌더가 깊은 중첩·대량 step에서 느림 | Low | Low | step 수는 런당 수십 개 수준, 단순 재귀 렌더 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `ai_run_step` | DB | V079 컬럼 2개 추가 |
| `AgentRunStepModel`, `AgentRunStep`, 리포지토리 매퍼 | Model/Entity | 필드 추가 |
| `track_step`, `RunTracker.record_step/update_step` | Application | 계층·latency 인자 추가 (기본값으로 하위호환) |
| `StepDto` (`agent_run_response.py`) | API Schema | 필드 2개 추가 |
| `agentRunAdmin.ts` `StepDto`, `StepTree.tsx` | Frontend | 타입 동기화, 트리 렌더 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `ai_run_step` | WRITE | `track_step` → `RunTracker.record_step/update_step` | 의도된 변경 |
| `ai_run_step` | READ | `find_steps` → 런 상세 API → `StepTree` | 필드 추가, 하위호환 |
| `ai_run_step` | READ | 런 목록/통계·평가(eval-hub)·잡 등 step 조회 경로 | Design에서 전수 확인 (컬럼 추가라 무영향 예상) |
| `record_step` | CALL | `track_step` 외 직접 호출부 | Design에서 전수 확인 |
| `StepDto` | READ | `AgentRunDetailPage`, `StepTree` | 동기화 |

### 6.3 Verification
- [ ] `find_steps`/런 상세 API 소비자 전수 확인
- [ ] 과거 런 조회 하위호환 (SC-6)

---

## 7. Architecture Considerations

### 7.1 Project Level
Enterprise 상당 — Thin DDD 유지, 레이어 이동 없음.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 계층 저장 | 컬럼 추가 / +agent_id / node_name 접두 | **parent_step_id + depth 컬럼** | 트리 정확 복원, API로 그대로 노출 (사용자 선택) |
| 부모 판별 | 컴파일러가 명시 전달 / 런타임 컨텍스트 | **런타임 `_current_step_id`** | 이미 존재하는 enter/restore 계약 재사용 — 컴파일러 변경 없음 |
| latency | 메모리 계산 / +DATETIME(3) / 제외 | **메모리(monotonic) 계산** | 스키마 변경 최소, 모든 step 정확화 (사용자 선택) |
| 범위 | 백엔드만 / +상세 트리 / +스트리밍 | **백엔드 + 실행 상세 트리** | 스트리밍은 실측 후 판단 (사용자 선택) |
| 검증 | 단위만 / 실런 | **실런 트레이스 기준** | 이전 사이클 교훈 — 런타임 경로는 실런에서만 드러남 (사용자 선택) |

---

## 8. Convention Prerequisites

| Category | Rule | Check |
|----------|------|-------|
| DDL | 테이블·전 컬럼 COMMENT, ORM `comment=` | `tests/db/test_migration_ddl_comments.py` |
| 마이그레이션 번호 | V079 (현재 최신 V078) — 착수 시 다른 브랜치와 충돌 확인 | `git ls-tree origin/master db/migration` |
| API 계약 | 백엔드 스키마 변경 시 프론트 타입 동시 수정 | `/api-cotract` |
| 프론트 | 컴포넌트 파일 런타임 상수 export 금지 | idt_front 규칙 |
| 테스트 | `uv run python -m pytest`, 프론트 vitest | — |

---

## 9. Next Steps

1. [ ] `/pdca design subagent-step-observability` — Design에서 확정할 열린 질문:
   - Q-D1: depth 계산 위치 — 컨텍스트에 부모 depth 보관 vs parent_step_id로 DB 조회 (조회 없이 컨텍스트 보관 권장)
   - Q-D2: `parent_step_id` FK(self, ON DELETE SET NULL) 둘지 여부
   - Q-D3: 승인 재개 런의 step 기록 경로 실측
   - Q-D4: `record_step` 직접 호출부·`find_steps` 소비자 전수
2. [ ] 구현 (TDD) — M1~M5
3. [ ] `/pdca analyze` + L3 실런

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-06 | Initial draft — 코드 실측 + 사용자 질의 4건 반영 | 배상규 |
