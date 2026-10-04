# subagent-context-scope Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt)
> **Version**: —
> **Author**: 배상규
> **Completion Date**: 2026-10-04
> **PDCA Cycle**: Plan → Design → Do(module-1~4) → Check(1회, Act 없음) → Report

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | 서브에이전트에 전달되는 문맥 범위 확장 (+ 서브에이전트 런타임 복구) |
| Start Date | 2026-10-02 |
| End Date | 2026-10-04 |
| Duration | 3일 (Plan·Design 1일, Do 4모듈, Check 1회) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100%                       │
├─────────────────────────────────────────────┤
│  ✅ Complete:     12 / 12 FR (FR-10~12 추가)  │
│  ⏳ In Progress:   0                          │
│  ❌ Cancelled:     0                          │
│  Match Rate: 100% (static / runtime 포함)     │
│  Success Criteria: 7 / 7                     │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 서브에이전트가 supervisor 지시(`worker_task`)를 받지 못하고 부모 마지막 메시지 1건만 받았다. 조사 중 더 큰 사실이 드러났다 — **서브에이전트 런타임은 운영에서 한 번도 동작한 적이 없었다**(저장소 DI 누락 → 노드 래핑 회귀 → name 패턴 400의 3중 차단). |
| **Solution** | 입력 조립을 `SubAgentContextStrategy`로 분리하고 기본 전략 `[원 질문] + [참고 자료(이번 턴 워커 산출, 최신 우선 4000자)] + [현재 작업(+재시도 사유)]`을 적용. 규칙은 domain `SubAgentContextPolicy`가 소유. 차단 3건은 세션 스코프 저장소 DI·`function_node_ids` 등록·`sanitize_llm_name`으로 해소. |
| **Function/UX Effect** | 실런(gpt-5.1)에서 부모 지침의 호출 방식(대상·기간·형식)이 자식 `[현재 작업]`에 그대로 도달하고, 자식은 참고자료를 근거로 **재검색 0회**로 요약했다(run `41cc2367`). 실행 이력 step에 `서브에이전트 입력: 원질문 O / 참고자료 1건 1052자 / 재시도 X` 요약이 남는다. |
| **Core Value** | 서브에이전트 조합(P2 핵심 시나리오)이 처음으로 실제 동작한다. 전략 인터페이스와 `resolve_strategy()` 단일 확장 지점으로 다음 사이클의 연결별 `context_mode`를 컴파일러 수정 없이 붙일 수 있다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | worker_task가 첫/중간/재시도 3경로에 포함 | ✅ Met | S1·S2·S3, C1 / L3-1 run `41cc2367` |
| SC-2 | QG 재시도 시 원 지시 + 피드백 | ✅ Met | P1·P9·S3 / L3-3 run `d6b5affc` (QG 강제 활성) |
| SC-3 | 참고자료 상한·절단 | ✅ Met | P5~P7 (`_pick_within_budget`) |
| SC-4 | 이전 턴·재주입·QG 피드백 제외 | ✅ Met | P1~P3 |
| SC-5 | 컴파일러 수정 없이 전략 교체 | ✅ Met | C2·C3 (생성자 주입 → `resolve_strategy` → 래퍼) |
| SC-6 | 산출 계약·승인 게이트 전파 회귀 0 | ✅ Met | C4, `test_gated_run_termination` 무수정 통과, 전체 회귀 신규 실패 0 |
| SC-7 | L3 실런 — 지시 수행·재수집 없음 | ✅ Met | 도구 호출 2건 모두 부모 워커, 자식 supervisor "추가 검색 없이 3줄 요약" |

**Success Rate**: 7/7 (100%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 대화 범위 = 지시 + 이번 턴 원 질문 (이전 턴은 task로 간접) | ✅ | 자식 토큰 최소, supervisor가 task에 대상·기간을 녹여 전달함을 실런 확인 |
| [Plan] | 이번 턴 워커 산출을 상한 내 참고자료로 | ✅ | 자식 재검색 0 — 중복 수집 방지 효과 실측 |
| [Plan] | 고정 정책 + 인터페이스화 | ✅ | `SubAgentContextStrategy`/`resolve_strategy` — 연결별 설정 확장 지점 1곳 |
| [Design] D-01 | Option C (Policy + Protocol + resolve) | ✅ | 신규 2파일, 과추상화 없음 |
| [Design] D-02/03 | 최신 우선 채움·시간순 출력, 전용 상한 4000자 | ✅ | P5~P7 |
| [Design] D-04 | 메시지 3건, 마지막 `[현재 작업]` | ✅ | 자식 search 파이프라인이 과제를 쿼리로 집음 |
| [Design] D-05 | 턴 경계 재정의 (`_current_turn_messages` 미사용) | ✅ | QG 피드백을 경계로 오인하던 기존 함수 회피 |
| [Design] D-08/11 | 조립 실패 시 현행 입력 fail-safe (`legacy_input`) | ✅ | 기존 MagicMock 테스트 5건 무수정 통과, C5 |
| [Design] D-10 | (FR-10) sub_agent `function_node_ids` 등록 | ✅ | C0 — 컴파일 그래프에서 실제 노드 실행 |
| [Design] D-12 | (FR-11) SessionScoped 저장소 DI | ✅ | 배선 계약 테스트 2건, 실런 성공 |
| [Design] D-13 | (FR-12) `sanitize_llm_name` + `clamp_llm_name` 금지 문자 치환 | ✅ | 서브에이전트 다음 supervisor 400 소멸 (run `41cc2367`) |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [subagent-context-scope.plan.md](../01-plan/features/subagent-context-scope.plan.md) (v0.3) | ✅ Finalized |
| Design | [subagent-context-scope.design.md](../02-design/features/subagent-context-scope.design.md) (v0.3) | ✅ Finalized |
| Check | [subagent-context-scope.analysis.md](../03-analysis/subagent-context-scope.analysis.md) | ✅ Complete |
| Act | Current document | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 입력 조립 인터페이스 `SubAgentContextStrategy` | ✅ | `@runtime_checkable` Protocol |
| FR-02 | 기본 전략 `TaskWithOriginStrategy` | ✅ | |
| FR-03 | domain `SubAgentContextPolicy` (R1~R8) | ✅ | LangChain 비의존, 재주입 판별은 기존 `AnalysisSnapshotPolicy` 재사용 |
| FR-04 | `_wrap_sub_agent` 적용, 출력 계약 불변 | ✅ | |
| FR-05 | QG 재시도 원 지시 + 피드백 | ✅ | 운영에서 QG 비활성 — 실효는 QG 활성 시 |
| FR-06 | worker_task 공백 시 원 질문 폴백 | ✅ | 원 질문 블록 중복 생략 |
| FR-07 | 입력 요약 step output_summary | ✅ | 본문 미포함 (C4·C4b) |
| FR-08 | 전략 DI (생성자, 기본값) | ✅ | `main.py` 무변경으로 기본 전략 |
| FR-09 | `resolve_strategy` 확장 지점 | ✅ | 현재 항상 default |
| FR-10 | (추가) 서브에이전트 노드 래핑 회귀 수정 | ✅ | 회귀 기점 `3a25eb7` (2026-06-14) |
| FR-11 | (추가) 컴파일러 저장소 DI 누락 수정 | ✅ | 도입 이후 미주입 |
| FR-12 | (추가) worker_id 공백 → OpenAI name 400 수정 | ✅ | 신규 id 정규화 + 저장 id 메시지 단계 방어 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 토큰 | 증가분 ≤ 참고자료 상한 + 원 질문 + task | 상한 4000자 강제 (P7) | ✅ |
| 아키텍처 | domain → 외부 import 0 | `dataclasses` + domain 모듈만 | ✅ |
| 로깅 | 본문 미포함, 예외 스택 | C4b, C5 (`exception=e`) | ✅ |
| 호환 | 기존 컴파일러·게이트 테스트 무수정 | 무수정 통과 | ✅ |
| 회귀 | 신규 실패 0 | 53 failed / 10289 passed — 기준선 동일 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| Domain Policy | `src/domain/agent_builder/sub_agent_context_policy.py` (신규) | ✅ |
| Strategy | `src/application/agent_builder/sub_agent_context.py` (신규) | ✅ |
| Session-scoped repo | `src/infrastructure/agent_builder/session_scoped_agent_repository.py` (신규) | ✅ |
| Compiler wiring | `src/application/agent_builder/workflow_compiler.py` | ✅ |
| DI | `src/api/main.py` | ✅ |
| Name sanitize | `src/domain/agent_builder/rag_tool_config.py`, `sub_agent_worker_builder.py` | ✅ |
| Tests | 신규 72건 (Policy 31, Strategy 15, Adapter 10, Compiler C0~C6+C4b 8, clamp 5, wiring 2, builder 1) | ✅ |
| 수정 파일 diff | 8 files, +357 / −9 | — |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority |
|------|--------|----------|
| 서브에이전트 연결별 `context_mode` 설정 (DB·API·모달) | Plan Out of Scope — 확장 지점만 마련 | Medium |
| 자식 그래프 step 관측 구분 (부모·자식 `supervisor` 혼재, 음수 latency) | 범위 밖 관측 | Medium |
| `quality_gate_enabled` 운영 활성화 여부 결정 | 운영 경로 항상 False — FR-05 실효 좌우 | Low |
| 실행 시점 서브에이전트 권한 재확인 | Plan Out of Scope | Low |
| `SubAgentAccessPolicy`·`subscription_repo` 잔여 정리 | 이전 사이클 accepted-minor | Low |

### 4.2 Accepted Minor (Check)

| Item | Reason |
|------|--------|
| G3 `_wrap_sub_agent`의 `self._logger` 의존 | `__new__` 테스트 모두 설정, 동작 영향 없음 |
| G4 `_wrap_sub_agent` 64줄(클로저 포함) | 기존 구조, 이번 증가분 약 1줄 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final |
|--------|--------|-------|
| Design Match Rate | 90% | **100%** (최초 98.8% → G1·G2 해소) |
| Success Criteria | 7/7 | 7/7 |
| Critical / Important gaps | 0 | 0 |
| 신규 회귀 | 0 | 0 |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| 서브에이전트가 worker_task 미수신 | 전략 기반 입력 조립 | ✅ |
| QG 재시도 시 피드백 문장만 전달 | 원 task + `[재시도 사유]` | ✅ |
| `function_node_ids` 누락 → `AttributeError` | sub_agent 분기 등록 + C0 | ✅ |
| 컴파일러 `agent_repository` 미주입 → compile 실패 | SessionScoped 어댑터 DI + 배선 계약 테스트 | ✅ |
| worker_id 공백 → OpenAI 400 → 조기 종료 | `sanitize_llm_name` + `clamp_llm_name` 치환 | ✅ |
| G1 로그 명세 불일치 / G2 로그 본문 미검증 / G5 Plan 문구 | Design §6 갱신 / C4b 추가 / FR-07 문구 갱신 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **실런을 Do 마지막 모듈로 고정한 것이 결정적이었다.** 단위·통합 테스트는 모두 초록이었지만, 운영 차단 버그 2건(FR-11·12)은 L3 실런에서만 드러났다.
- **경로 추적형 조사**: "문맥이 좁다"는 가설을 메시지 흐름(`worker_task` 저장 위치 → 래퍼 소비)으로 추적해 실제 결함(지시 미전달)을 Plan 단계에서 확정했다.
- **fail-safe 하위호환 설계(D-08)** 덕에 기존 MagicMock 테스트를 하나도 고치지 않았다.
- 범위 추가 시마다 사용자 승인 → Plan/Design 버전 기록으로 문서가 실제 구현을 따라갔다.

### 6.2 What Needs Improvement (Problem)

- 서브에이전트 런타임은 2026-06 사이클에서 "런타임 위임은 범위 외"로 남겨진 채 아무도 실행해 보지 않아 3중 결함이 4개월 잠복했다.
- 기존 테스트가 `_compile_sub_agent`를 `AsyncMock`으로 대체해 실제 노드 실행 경로를 한 번도 타지 않았다 — 모킹이 결함을 가렸다.
- 앱 싱글톤 DI 누락은 단위 테스트로 잡히지 않는다(배선 계약 테스트가 없던 영역).

### 6.3 What to Try Next (Try)

- 새 노드 유형·워커 유형을 추가하면 **컴파일된 그래프에서 노드를 실제 실행하는 테스트**(C0 형태)를 기본으로 둔다.
- 앱 싱글톤 생성부의 선택 의존성은 `test_runtime_tool_factory_wiring.py` 같은 **배선 계약 테스트**로 고정한다.
- "범위 외"로 넘긴 런타임 경로는 다음 사이클 백로그에 L3 실런 항목으로 명시한다.

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 기존 기능의 런타임 동작을 가정 | 의존하는 기존 경로를 먼저 1회 실런해 전제 확인 |
| Do | 실런이 마지막 모듈 | 의존 경로가 처음 쓰이는 기능이면 실런 스모크를 module-1 전에 수행 |
| Check | gap-detector 정적 분석 | 실런 trace(run_id) 근거를 분석 문서에 함께 기록 (이번 사이클 적용) |

---

## 8. Next Steps

1. feature 브랜치 생성 후 커밋·PR — 운영 차단 버그 3건 수정 포함이므로 PR 본문에 FR-10/11/12를 명시
2. `/pdca archive subagent-context-scope`
3. 후속 후보: 자식 step 관측 구분, 연결별 `context_mode`, `quality_gate_enabled` 정책 결정

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-10-04 | 완료 보고서 — Match 100%, SC 7/7, FR 12/12 | 배상규 |
