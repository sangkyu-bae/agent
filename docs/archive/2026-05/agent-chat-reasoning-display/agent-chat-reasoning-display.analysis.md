---
template: analysis
version: 1.0
feature: agent-chat-reasoning-display
date: 2026-05-26
author: 배상규 (gap-detector agent)
project: sangplusbot
---

# agent-chat-reasoning-display Gap Analysis Report

> **Summary**: Design 문서와 실제 구현 코드의 항목별 매칭률 측정. Match Rate **100%** (47/47).
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: gap-detector agent
> **Date**: 2026-05-26
> **Status**: Final
> **Design Doc**: [agent-chat-reasoning-display.design.md](../02-design/features/agent-chat-reasoning-display.design.md)
> **Plan Doc**: [agent-chat-reasoning-display.plan.md](../01-plan/features/agent-chat-reasoning-display.plan.md)

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Match Rate** | **100%** (47/47) |
| Matched (✅) | 47 |
| Partial (⚠️) | 0 |
| Missing (❌) | 0 |
| Verdict | Ready for /pdca report |

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match (§3, §4, §5) | 100% | ✅ |
| Architecture Compliance (§9) | 100% | ✅ |
| Convention Compliance (§10) | 100% | ✅ |
| Test Coverage (T1~T11) | 100% | ✅ |

---

## 1. Analysis Overview

- **Method**: Static analysis only (코드 직접 읽기). 테스트 실행 / E2E는 별도 단계.
- **Scope**: Design §3 Data Model, §4 API Spec, §5 UI/UX, §6 Error Handling, §9 Clean Architecture, §10 Conventions, §8 Test Plan (T1~T11).
- **Files Analyzed**: Backend 6개 구현 + 6개 테스트, Frontend 5개 구현 + 4개 테스트.

---

## 2. Item-by-Item Verification

### 2.1 Domain Layer (§3.1)

| # | Item | Expected | Implementation | Status | Evidence |
|---|------|----------|----------------|:------:|----------|
| 1 | Agent enum | `AgentRunEventType.STEP_REASONING = "step_reasoning"` | Exact match | ✅ | `idt/src/domain/agent_run/value_objects.py:130` |
| 2 | Chat enum | `ChatEventType.STEP_REASONING = "chat_step_reasoning"` | Exact match | ✅ | `idt/src/domain/general_chat/value_objects.py:26` |
| 47 | Chat enum member count = 8 | `len(list(ChatEventType)) == 8` | Test asserts | ✅ | `tests/domain/general_chat/test_value_objects.py:25-26` |

### 2.2 Event Payload (§3.2)

| # | Item | Expected | Implementation | Status | Evidence |
|---|------|----------|----------------|:------:|----------|
| 3 | Agent payload schema | `{step_name, reasoning, next_worker}` | `_maybe_supervisor_reasoning` constructs exactly these | ✅ | `idt/src/application/agent_builder/run_agent_use_case.py:575-582` |
| 4 | Chat payload schema | `{step_name, reasoning, tool_calls}` | `_map_model_reasoning` constructs exactly these | ✅ | `idt/src/application/general_chat/use_case.py:293-302` |

### 2.3 Frontend Types (§3.3)

| # | Item | Expected | Implementation | Status | Evidence |
|---|------|----------|----------------|:------:|----------|
| 5 | `AgentStepReasoningData` | `{step_name, reasoning, next_worker}` | Exact | ✅ | `idt_front/src/types/websocket.ts:36-40` |
| 6 | `ChatStepReasoningData` | `{step_name, reasoning, tool_calls}` | Exact | ✅ | `idt_front/src/types/websocket.ts:119-123` |
| 7 | Union members | `agent_step_reasoning`, `chat_step_reasoning` | Both in unions | ✅ | `idt_front/src/types/websocket.ts:81, 157` |
| 8 | `AgentRunStep.kind` | `'node' \| 'tool' \| 'reasoning'` + `text?`, `nextWorker?` | Exact | ✅ | `idt_front/src/hooks/useAgentRunStream.ts:19-26` |
| 9 | `ChatToolEvent.kind` | `'started' \| 'completed' \| 'reasoning'` + `text?` | Exact | ✅ | `idt_front/src/hooks/useChatStream.ts:20-27` |

### 2.4 WebSocket Protocol (§4.1)

| # | Item | Expected | Implementation | Status | Evidence |
|---|------|----------|----------------|:------:|----------|
| 10 | Agent WS mapping | `STEP_REASONING → "agent_step_reasoning"` | Exact | ✅ | `idt/src/infrastructure/agent_run/ws_adapter.py:19` |
| 11 | Chat WS mapping | `STEP_REASONING → "chat_step_reasoning"` | Exact | ✅ | `idt/src/infrastructure/general_chat/ws_adapter.py:16` |
| 12 | Sequence ordering (Agent) | `STEP_REASONING` immediately after `NODE_COMPLETED` | Loop yields `mapped`, then `extra` for same `raw_ev` | ✅ | `run_agent_use_case.py:213-219` |
| 13 | Sequence ordering (Chat) | `STEP_REASONING` on `on_chat_model_end` | Dispatch in `_map_event` | ✅ | `use_case.py:268-270` |
| 14 | Trigger — Agent skip if empty summary | Empty/None summary → None | `if not summary: return None` | ✅ | `run_agent_use_case.py:572-574` |
| 15 | Trigger — Agent supervisor-only | Name guard `_STEP_NAME_SUPERVISOR` | Explicit name check | ✅ | `run_agent_use_case.py:567-568` |
| 16 | Trigger — Chat skip if no tool_calls | Empty → None | `if not tool_calls: return None` | ✅ | `use_case.py:287-289` |
| 17 | Trigger — Chat skip if empty content | Empty/whitespace → None | `if not content.strip(): return None` | ✅ | `use_case.py:290-292` |

### 2.5 UI/UX (§5.1, §5.2)

| # | Item | Expected | Implementation | Status | Evidence |
|---|------|----------|----------------|:------:|----------|
| 18 | Panel header text | "추론 진행" | Exact | ✅ | `idt_front/src/components/chat/ToolPreviewPanel.tsx:40` |
| 19 | Status markers (💭 / ⏳ / ✓) | reasoning 💭, started ⏳, completed ✓ | All three present (§5.2 pseudo-code follow) | ✅ | `ToolPreviewPanel.tsx:56, 69` |
| 20 | No JSON preview rendering | preview 라인 완전 제거 | preview 미참조 | ✅ | `ToolPreviewPanel.tsx:49-78` |
| 21 | Toggle count = tool only | `events.filter(e => e.kind !== 'reasoning').length` | Exact | ✅ | `ToolPreviewPanel.tsx:23` |

### 2.6 Hooks State Machine (§5.3)

| # | Item | Expected | Implementation | Status | Evidence |
|---|------|----------|----------------|:------:|----------|
| 22 | `useAgentRunStream` case | Append `{kind:'reasoning', name, text, nextWorker}` | Exact | ✅ | `useAgentRunStream.ts:85-99` |
| 23 | `useChatStream` case | Append `{kind:'reasoning', toolName, text}` | Exact | ✅ | `useChatStream.ts:83-96` |
| 24 | `agentStepsToToolEvents` | reasoning 통과 + preview omit | Filter includes reasoning, tool branch omits preview | ✅ | `agentStepToToolEvent.ts:15-27` |

### 2.7 Error Handling (§6)

| # | Item | Expected | Implementation | Status | Evidence |
|---|------|----------|----------------|:------:|----------|
| 25 | Backend — empty summary 미발행 | None return | 동일 | ✅ | `run_agent_use_case.py:572-574` |
| 26 | Backend — empty chat content 미발행 | None return | 동일 | ✅ | `use_case.py:290-292` |
| 27 | Frontend — empty reasoning text skip render | null return | `if (!text) return null` | ✅ | `ToolPreviewPanel.tsx:52-53` |

### 2.8 Clean Architecture (§9)

| # | Item | Expected | Implementation | Status | Evidence |
|---|------|----------|----------------|:------:|----------|
| 28 | Domain layer pure | Enum 추가만, 외부 의존 0 | `Enum`, `dataclass`, `Mapping`, `datetime`만 사용 | ✅ | 두 VO 파일 |
| 29 | Application orchestration only | 비즈니스 규칙 미추가 | helper 두 개 모두 순수 dispatcher | ✅ | `run_agent_use_case.py:555-582`, `use_case.py:277-302` |
| 30 | Infrastructure mapping only | `_TYPE_MAP` 한 줄씩만 | 두 adapter 모두 entry 추가만 | ✅ | 두 adapter |

### 2.9 Coding Conventions (§10)

| # | Item | Expected | Implementation | Status | Evidence |
|---|------|----------|----------------|:------:|----------|
| 31 | Module constants | `_STEP_NAME_SUPERVISOR`, `_STEP_NAME_CHAT_AGENT` | 모듈 상수로 정의 | ✅ | `run_agent_use_case.py:74`, `use_case.py:48` |
| 32 | Function length ≤ 40 lines | 신규 helper 둘 다 | `_maybe_supervisor_reasoning`: 28줄, `_map_model_reasoning`: 26줄 | ✅ | — |
| 33 | Type hints | 모든 신규 함수에 명시적 반환 타입 | `Optional[AgentRunEvent]` / `Optional[ChatEvent]` | ✅ | 두 helper |
| 34 | if-nesting ≤ 2 levels | early-return 패턴 | 모두 flat | ✅ | 두 helper |
| 35 | snake_case WS strings | `"agent_step_reasoning"`, `"chat_step_reasoning"` | Exact | ✅ | adapter `_TYPE_MAP` |

### 2.10 Test Plan (§8) T1~T11

| # | Test | Expected | Implementation | Status | Evidence |
|---|------|----------|----------------|:------:|----------|
| 36 | T1 — reasoning after NODE_COMPLETED | seq + payload + 위치 검증 | Present | ✅ | `test_run_agent_use_case.py:409-438` |
| 37 | T2 — no STEP_REASONING when summary missing | 부재 검증 | Present | ✅ | `test_run_agent_use_case.py:440-455` |
| 38 | T3 — STEP_REASONING when tool_calls + content | payload 검증 | Present | ✅ | `test_use_case.py:353-378` |
| 39 | T4 — no STEP_REASONING when no tool_calls | 부재 검증 | Present | ✅ | `test_use_case.py:380-395` |
| 40 | T5 — no STEP_REASONING when content empty | 부재 검증 | Present | ✅ | `test_use_case.py:397-415` |
| 41 | T6 — Agent WS adapter maps | parametrize + payload pass-through | 둘 다 | ✅ | `test_ws_adapter.py:41, 102-114` (agent_run) |
| 42 | T7 — Chat WS adapter maps | parametrize + payload pass-through | 둘 다 | ✅ | `test_ws_adapter.py:38, 78-89` (general_chat) |
| 43 | T8 — `useAgentRunStream` reasoning case | step shape 검증 | Present | ✅ | `useAgentRunStream.test.ts:123-142` |
| 44 | T9 — `useChatStream` reasoning case | toolEvents shape 검증 | Present | ✅ | `useChatStream.test.ts:136-154` |
| 45 | T10 — `agentStepsToToolEvents` reasoning 통과 | reasoning 통과 + node 폐기 | Present | ✅ | `agentStepToToolEvent.test.ts:54-73` |
| 46 | T11 — `ToolPreviewPanel` reasoning + no JSON + tool-only count | 세 가지 모두 검증 | Present | ✅ | `ToolPreviewPanel.test.tsx:59-103` |

---

## 3. Summary of Findings

### 3.1 Missing (Design O, Implementation X)
**없음.** Design에 명시된 모든 항목이 구현되어 있다.

### 3.2 Added (Design X, Implementation O)
**없음.** 구현은 Design 범위를 벗어나지 않았다(YAGNI 준수).

### 3.3 Inconsistencies (Internal to Design)
| # | Item | Design | Implementation | Severity |
|---|------|--------|----------------|:--------:|
| A | Tool list marker 🔧 | §5.1 ASCII mockup에 `🔧 rag_search` | 구현은 `⏳/✓ rag_search` (font-mono name + status icon만) | Minor — §5.2 pseudo-code도 🔧 미포함. Design 내부 불일치이며 implementation은 §5.2를 정확히 따랐음. |

> **권고**: §5.1 mockup의 🔧를 제거해 §5.2와 일치시키는 문서 정리만 필요. 코드 변경 불필요.

### 3.4 Score Calculation
```
47 items evaluated
47 Match (✅)
 0 Partial (⚠️)  ← 위 §3.3 Item A는 Design 내부 불일치로 reconcile됨
 0 Missing (❌)

Match Rate = 47 / 47 = 100%
```

---

## 4. Recommended Actions

### 4.1 Immediate (none required)
Match Rate ≥ 90% → 즉시 `/pdca report agent-chat-reasoning-display` 진입 가능.

### 4.2 Documentation Polish (Optional, Non-blocking)
- Design §5.1 mockup의 `🔧 rag_search` 텍스트를 `⏳/✓ rag_search`로 정리해 §5.2 pseudo-code와 일치 (5분 작업).

### 4.3 Outstanding Runtime Verification (Out of Static-Analysis Scope)
- Design §8.3 수동 E2E 체크리스트(브라우저 + WS DevTools).
- 실제 `pytest` / `vitest` 실행 — 이 분석은 테스트 **존재**만 검증함. (단, 본 PDCA Do 단계에서 백엔드 394건, 프론트 109건 격 영역 회귀 모두 Green 확인됨.)

---

## 5. Conclusion

**Match Rate 100%** — Design과 구현이 항목 단위로 정확히 일치한다. 11개 테스트 케이스(T1~T11) 모두 Design intent와 일치하는 assertion으로 구현되어 있다. 발견된 minor inconsistency 한 건은 Design 문서 내부의 표기 차이이며, implementation은 §5.2 pseudo-code를 정확히 따랐다.

**Next phase**: `/pdca report agent-chat-reasoning-display` — 완료 보고서 작성.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-05-26 | Gap-detector static analysis. Match Rate 100% (47/47). | gap-detector agent |
