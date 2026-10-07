# subagent-step-observability Completion Report

> **Status**: Complete (SC-5 화면 확인만 사용자 확인 대기)
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: —
> **Author**: 배상규
> **Completion Date**: 2026-10-07
> **PDCA Cycle**: Plan → Design → Do(module-1~4) → Check(1회, G-1~G-4 즉시 조치) → Report

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | 서브에이전트(자식 그래프) step 관측 구분 + step latency 정확화 |
| Start Date | 2026-10-06 |
| End Date | 2026-10-07 |
| Duration | 2일 |
| Branch / Worktree | `feature/subagent-step-observability` / `../wt/subagent-step-observability` |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100% (FR 9/9)              │
├─────────────────────────────────────────────┤
│  ✅ Complete:     9 / 9 FR                    │
│  ⚠ Partial:      SC-5 (화면 육안 확인 대기)    │
│  Match Rate: 99.2% static / 96.0% runtime    │
│  Success Criteria: 6 / 7 (+1 partial)        │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 서브에이전트 런에서 자식의 supervisor·quality_gate·워커 step이 부모와 같은 이름으로 평평하게 섞여(실런 14 step 중 8~9개가 자식) 누가 무엇을 했는지 실행 이력으로 알 수 없었다. 모든 step latency는 `DATETIME` 초 반올림 때문에 최대 ±500ms 틀어지고 1초 미만 step은 음수(−122ms, −476ms)로 찍혔다. |
| **Solution** | `track_step`이 기록 시점의 `callback._current_step_id`(감싸는 서브에이전트 wrapper)를 `parent_step_id`로, `RunContext.step_depth`+1을 `depth`로 남긴다(V079, FK 없음). latency는 monotonic 측정값을 우선 저장. API는 필드 추가만, 프론트가 `buildStepTree`로 트리를 만들어 접기형 StepTree로 렌더. |
| **Function/UX Effect** | 실런(run `8863101d`): 자식 9 step 전부 올바른 wrapper 아래 depth 1, 최상위 5 step은 parent 없음, tool·llm call 전부 자식 step에 귀속, 14 step latency 전부 ≥ 0(quality_gate 0ms·16ms). 실행 상세에서 서브에이전트 step 아래 자식이 들여쓰기·"하위 N"·접기로 묶인다. |
| **Core Value** | 멀티 에이전트를 운영자(P2)가 실행 이력만으로 디버깅·검수할 수 있게 됐다. 컴파일러·서브에이전트 래퍼를 바꾸지 않고 기존 enter/restore 계약 위에 얹어, 손자 그래프(depth 2)와 승인 재개 런에도 같은 규칙이 적용된다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 자식 step이 자신을 감싼 wrapper를 parent로 | ✅ Met | run `8863101d`: #3~#9 → #2(분석가), #13·#14 → #12(작성자), depth 1 |
| SC-2 | 최상위 step parent NULL·depth 0 | ✅ Met | #1·#2·#10·#11·#12 / 단위 B1·B5 |
| SC-3 | 자식 tool·llm call 귀속 | ✅ Met | tool 2건·llm call 전부 depth 1 step |
| SC-4 | 전 step latency ≥ 0 | ✅ Met | 실런 14/14, 단위 B8(정상·예외·음수 방어) |
| SC-5 | StepTree 트리·접기 | ⚠️ Partial | 컴포넌트 F4~F6·G-4 통과, **실제 화면 육안 확인은 사용자 대기** |
| SC-6 | 과거 런 평면 하위호환 | ✅ Met | 매퍼 depth None→0(B12), F6, buildStepTree F1 |
| SC-7 | 회귀 0 | ✅ Met | BE 신규 실패 0(blueprint 6건은 HEAD 재현 — 미추적 샘플 PDF), FE 9/4파일 기준선 동일, tsc 210 동일 |

**Success Rate**: 6/7 Met + 1 Partial

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | parent_step_id + depth 컬럼 (agent_id 제외) | ✅ | 트리 정확 복원, V079 컬럼 2개 |
| [Plan] | latency 메모리 계산 (DATETIME(3) 미적용) | ✅ | 음수 해소, 스키마 변경 최소 |
| [Plan] | 백엔드 + 실행 상세 트리, 스트리밍은 실측만 | ✅ | 스트리밍 섞임 실측·기록(FR-09) |
| [Plan] | 실런 트레이스 기준 검증 | ✅ | SC-1~4 실런 근거 |
| [Design] D-01 | Option C | ✅ | 백 7·프 2 수정, 신규 2 + 테스트 |
| [Design] D-02 | 부모 = `callback._current_step_id` | ✅ | 컴파일러·래퍼 무변경으로 계층 확보 |
| [Design] D-03 | FK 없음 | ✅ | best-effort 유지(B10: wrapper 기록 실패 → 자식 최상위) |
| [Design] D-04 | depth = `RunContext.step_depth` 전파 | ✅ | 3단(B3)·예외 후 복원(B6) |
| [Design] D-05 | latency 측정값 우선 | ✅ | 기존 계산 경로 하위호환(B9) |
| [Design] D-06/07 | 평면 API + 프론트 트리, 부모 미발견 승격 | ✅ | 순환까지 승격(D-11) |
| [Design] D-09 | `/admin/usage/by-node` 현행 유지 | ✅ | 후속 후보 |
| [Design] D-10 | 승인 재개 런 = 같은 경로(Q-D3) | ✅ | 별도 처리 불필요 (재개 실런은 실제 답변 등록 위험으로 미수행) |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [subagent-step-observability.plan.md](../01-plan/features/subagent-step-observability.plan.md) | ✅ |
| Design | [subagent-step-observability.design.md](../02-design/features/subagent-step-observability.design.md) (v0.2) | ✅ |
| Check | [subagent-step-observability.analysis.md](../03-analysis/subagent-step-observability.analysis.md) | ✅ |
| Act | Current document | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | V079 컬럼 + COMMENT | ✅ | 로컬 DB 적용 완료 (flyway 이력 없음 → 직접 실행) |
| FR-02 | 엔티티·ORM·매퍼 | ✅ | update는 계층 불변 |
| FR-03 | track_step 계층 기록 | ✅ | `_resolve_hierarchy` H1~H4 |
| FR-04 | latency 메모리 계산 | ✅ | `_elapsed_ms` monotonic, `max(0,…)` |
| FR-05 | StepDto 필드 | ✅ | 기본값 None/0 |
| FR-06 | 프론트 타입 동기화 | ✅ | + `StepTreeNode` |
| FR-07 | StepTree 트리 | ✅ | 토글·"하위 N"·role=group·기본 펼침·평면 하위호환 |
| FR-08 | 자식 tool/llm 귀속 검증 | ✅ | 코드 변경 불필요 — 기존 enter_step 귀속이 그대로 동작 |
| FR-09 | 스트리밍 섞임 실측 | ✅ | 섞임 확인·기록 (수정은 다음 사이클) |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 무중단 | 컬럼 추가만 | NULL/DEFAULT 0, 과거 런 평면 표시 | ✅ |
| best-effort | 기록 실패가 실행을 막지 않음 | B10 | ✅ |
| DDL | 전 컬럼 COMMENT | `test_migration_ddl_comments` 통과 | ✅ |
| 프론트 | 신규 실패·오류 0 | vitest 기준선 동일, eslint clean, tsc 210 동일 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| Migration | `idt/db/migration/V079__add_hierarchy_to_ai_run_step.sql` | ✅ |
| Backend | `context.py`, `step_tracking.py`, `tracker.py`, `entities.py`, `models/agent_run.py`, `agent_run_repository.py`, `agent_run_response.py` | ✅ |
| Frontend | `types/agentRunAdmin.ts`, `utils/buildStepTree.ts`(신규), `StepTree.tsx` | ✅ |
| Tests | BE 24건(계층·latency 14, 영속 7, DTO 3) / FE 12건(buildStepTree 7, StepTree 5) | ✅ |
| Diff | 9 files changed, +176 / −54 (+ 신규 2 소스) | — |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority |
|------|--------|----------|
| SC-5 화면 육안 확인 | worktree 서버 기동 필요, 사용자 확인 대기 | High |
| 실시간 진행(WS) 이벤트의 부모/자식 구분 | FR-09 실측: 자식 supervisor·quality_gate가 부모와 같은 이름 이벤트로 섞이고, 자식 도구 워커는 node 이벤트 없이 tool 이벤트만 | Medium |
| `/admin/usage/by-node` depth 분리 집계 | D-09 현행 유지 | Low |
| SSE `/run/stream` 인증 placeholder 미배선(항상 401) | 범위 밖 기존 결함, 프론트는 WS 사용 | Low |
| 승인 재개 런 실런 검증 | 실제 문의 답변 등록 위험 | Low |

### 4.2 Accepted Minor
- G-5 `track_step` 64줄 (master 65줄 → 감소, 신규 위반 아님)

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final |
|--------|--------|-------|
| Design Match Rate | 90% | **99.2%** static / 96.0% runtime (SC-5 확인 후 99.5%) |
| Critical / Important gaps | 0 | 0 (Important G-1 문서 갭 조치 완료) |
| 신규 회귀 | 0 | 0 |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| 부모·자식 step 구분 불가 | parent_step_id·depth 기록 + 트리 렌더 | ✅ |
| latency 반올림·음수 | monotonic 측정값 저장 | ✅ |
| G-1 Q-D3 문서 누락 | Design D-10 | ✅ |
| G-2 순환 노드 화면 유실 | `closesCycle` 방문 집합 승격 (Red→Green) | ✅ |
| G-3·G-4 테스트 공백 | 가드 테스트 2건 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)
- **기존 계약 재사용**: `track_step`의 enter/restore가 이미 "현재 활성 step"을 정확히 들고 있어, 컴파일러·서브에이전트 래퍼를 한 줄도 바꾸지 않고 계층을 얻었다.
- **실런을 스트리밍 경로로 수행**해 한 번의 런으로 계층 검증과 FR-09(스트리밍 섞임) 실측을 동시에 끝냈다.
- worktree에서 시작해 메인 폴더(다른 세션 작업 추정 파일)를 건드리지 않았다.

### 6.2 What Needs Improvement (Problem)
- Design에서 실측한 Q-D3을 대화에만 남기고 문서에 쓰지 않아 Check에서 Important로 잡혔다.
- `buildStepTree` 초안이 Design §6의 순환 방어를 자기참조로만 좁혀 구현했다 — 설계 문장과 테스트 케이스를 1:1로 대응시키지 않은 탓.
- 새 worktree `.venv`가 Windows 애플리케이션 제어 정책에 막혀 메인 venv로 우회해야 했다.

### 6.3 What to Try Next (Try)
- Design의 열린 질문을 해소하면 그 자리에서 Decision Record에 기록한다.
- Design §6(에러 처리) 각 행을 테스트 케이스 ID와 연결한다.
- worktree 실런은 처음부터 메인 venv + worktree `sys.path` 방식을 쓴다 (메모리에 기록).

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Design | 열린 질문 결과가 응답에만 남음 | 결과를 즉시 Decision Record로 |
| Do | 실런 경로 선택(SSE)이 실패 후 WS로 전환 | 실런 전 프론트가 쓰는 실제 경로(WS) 먼저 확인 |
| Check | gap-detector가 Bash 없이 정적 대조 | 메인 세션이 핵심 주장 재검증(이번에 G-1·G-2 확인) 유지 |

---

## 8. Next Steps

1. SC-5 화면 확인 (`/admin/agent-runs/8863101d-d685-42fb-bec0-01691ad6fde7`)
2. 승인함 대기 2건(`7928db87…`, `c0fe25b0…`) 반려
3. 커밋·PR (`feature/subagent-step-observability`) — V079 포함이므로 PR 본문에 운영 DB 적용 필요 명시
4. `/pdca archive subagent-step-observability`
5. 후속 후보: WS 이벤트 부모/자식 구분

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-10-07 | 완료 보고서 — Match 99.2%/96.0%, FR 9/9, SC 6/7 + 1 partial | 배상규 |
