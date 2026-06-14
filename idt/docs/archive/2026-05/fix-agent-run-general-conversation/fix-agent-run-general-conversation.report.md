# fix-agent-run-general-conversation Completion Report

> **Feature**: Agent Run API 일반 대화 응답 버그 수정
> **Date**: 2026-05-18
> **Author**: 배상규
> **Status**: Completed
> **Match Rate**: 100%

---

## Executive Summary

| Item | Detail |
|------|--------|
| Feature | fix-agent-run-general-conversation |
| Started | 2026-05-18 |
| Completed | 2026-05-18 |
| Duration | 1 session |
| PDCA Iterations | 0 (First pass 100%) |

### Results

| Metric | Value |
|--------|-------|
| Match Rate | 100% |
| Design Items | 7 sections |
| Files Changed | 1 production + 2 test |
| Lines Added | ~35 (production) + ~55 (test) |
| Tests Added | 4 new |
| Tests Total Pass | 48+ (all existing + new) |

### Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | `POST /api/v1/agents/{id}/run`에서 "고마워", "안녕" 등 일반 대화 입력 시 supervisor가 즉시 FINISH → 사용자 쿼리가 answer로 그대로 반환되는 버그 |
| **Solution** | `SupervisorDecision.answer` 필드 추가 + decision_prompt에 직접 응답 지시 + FINISH 시 AIMessage 생성 |
| **Function/UX Effect** | 도구 호출 불필요한 질문에도 에이전트가 자연스러운 대화 응답 생성. 추가 LLM 호출 없이 해결 |
| **Core Value** | 에이전트 UX 정상화 — 모든 유형의 질문에 적절한 응답 보장 |

---

## 1. Root Cause

`supervisor_nodes.py`의 `decision_prompt`가 "워커 호출 or FINISH" 두 가지만 제시. 일반 대화가 들어오면:

1. LLM이 도구 불필요 → `FINISH` 반환
2. 그래프 즉시 종료 → AI 응답 메시지 없음
3. `_parse_result()`가 `messages[-1]` (사용자 원본 쿼리)을 answer로 반환

## 2. Solution Applied

### 2.1 Production Code (1 file)

**`src/application/agent_builder/supervisor_nodes.py`**

| Change | Description |
|--------|-------------|
| `SupervisorDecision.answer` | `default=""` 필드 추가 — FINISH 시 직접 응답 |
| `decision_prompt` | "워커 없이 직접 답변 가능하면 FINISH + answer 작성" 지시 추가 |
| FINISH 분기 | `decision.answer` 존재 시 `AIMessage(content=answer)`를 state.messages에 추가 |

### 2.2 Test Code (2 files, 4 tests)

| Test | File | Purpose |
|------|------|---------|
| `test_finish_with_answer_creates_ai_message` | test_supervisor_nodes.py | FINISH + answer → AIMessage 생성 검증 |
| `test_finish_returns_end` (updated) | test_supervisor_nodes.py | FINISH + answer="" → messages 없음 (기존 동작 보존) |
| `test_worker_selection_ignores_answer` | test_supervisor_nodes.py | 워커 선택 시 answer 무시 검증 |
| `test_run_agent_general_conversation_returns_proper_answer` | test_agent_builder_router.py | 라우터 레벨 일반 대화 응답 검증 |

## 3. Design Decisions

| Decision | Rationale |
|----------|-----------|
| answer 필드를 SupervisorDecision에 추가 (방안 A) | 추가 LLM 호출 없이 최소 변경으로 해결. 기존 그래프 구조 변경 불필요 |
| fallback_answer 별도 노드 기각 (방안 B) | 불필요한 LLM 추가 호출 + 그래프 복잡도 증가 |
| _parse_result 후처리 기각 (방안 C) | 근본 원인 해결이 아닌 우회 |

## 4. Unchanged Files (Non-Goals)

| File | Status |
|------|--------|
| `workflow_compiler.py` | 변경 없음 (그래프 구조 유지) |
| `run_agent_use_case.py` | 변경 없음 (`_parse_result` 자연스럽게 동작) |
| `supervisor_state.py` | 변경 없음 (상태 필드 추가 불필요) |
| `prompt_generator.py` | 변경 없음 |

## 5. Gap Analysis

| Category | Score |
|----------|:-----:|
| Design Match | 100% |
| Architecture Compliance | 100% |
| Convention Compliance | 100% |
| **Overall** | **100%** |

Gap 0건. 모든 Design 섹션이 구현과 정확히 일치.

## 6. PDCA Cycle Summary

```
[Plan] > [Design] > [Do] > [Check 100%] > [Report]
```

| Phase | Output |
|-------|--------|
| Plan | `docs/01-plan/features/fix-agent-run-general-conversation.plan.md` |
| Design | `docs/02-design/features/fix-agent-run-general-conversation.design.md` |
| Do | supervisor_nodes.py 수정 + 테스트 4개 추가 |
| Check | `docs/03-analysis/fix-agent-run-general-conversation.analysis.md` (100%) |
| Report | 이 문서 |
