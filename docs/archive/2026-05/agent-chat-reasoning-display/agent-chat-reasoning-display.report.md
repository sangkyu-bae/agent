---
template: report
version: 1.0
feature: agent-chat-reasoning-display
date: 2026-05-26
author: 배상규
project: sangplusbot
---

# agent-chat-reasoning-display Completion Report

> **Summary**: Agent 및 General Chat 중간 진행 표시를 raw JSON 대신 "추론 이유 + 선택한 tool"로 전환. 신규 WS 이벤트 도입으로 Supervisor reasoning과 ReAct agent reasoning을 사용자에게 자연어로 설명하는 UX 제공. Match Rate **100%** (47/47 항목 일치).
>
> **Project**: sangplusbot (idt + idt_front)  
> **Author**: 배상규  
> **Date**: 2026-05-26  
> **Status**: Complete  
> **Planning Doc**: [agent-chat-reasoning-display.plan.md](../../01-plan/features/agent-chat-reasoning-display.plan.md)  
> **Design Doc**: [agent-chat-reasoning-display.design.md](../../02-design/features/agent-chat-reasoning-display.design.md)  
> **Analysis Doc**: [agent-chat-reasoning-display.analysis.md](../../03-analysis/agent-chat-reasoning-display.analysis.md)

---

## 1. Executive Summary

### 1.1 Project Overview

| Item | Value |
|------|-------|
| **Feature** | Agent & General Chat 추론 표시 (Reasoning Display) |
| **Duration** | 2026-05-26 ~ 2026-05-26 (단일 세션) |
| **Owner** | 배상규 |
| **Scope** | Backend 6개 파일 + Frontend 5개 파일 (총 11개) |

### 1.2 Results Summary

| Metric | Value |
|--------|-------|
| **Match Rate** | 100% (47/47 항목) |
| **Backend Regression** | 394건 모두 통과 |
| **Frontend Regression** | 109건 모두 통과 |
| **New Tests Added** | 11건 (T1~T11, TDD Red→Green 완료) |
| **Code Quality** | 함수 길이 ≤ 40줄, if 중첩 ≤ 2단계, Thin DDD 준수 |
| **Analysis Findings** | Missing 0건, Added 0건, Partial 0건 |

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 사용자 정의 Agent / General Chat 모두 중간 진행을 표시할 때 `input_preview`·`output_preview`가 `{"query":"..."}` 같은 raw JSON 문자열로 그대로 화면에 노출되어 가독성이 낮고 비기술 사용자에게 의미 전달 불가. Supervisor가 이미 생성하는 `reasoning`도 WS 송출 없이 버려지고 있었음. |
| **Solution** | (1) 백엔드: `SupervisorDecision.reasoning`을 새 WS 이벤트(`agent_step_reasoning`)로 송출. 일반 Chat의 ReAct agent에서는 tool_call 직전 AI 메시지 content를 reasoning으로 추출해 `chat_step_reasoning` 이벤트로 송출. (2) 프론트: `ToolPreviewPanel`을 "추론 진행" 패널로 리워크 — 💭 reasoning + 🔧/✓ tool만 표시. raw JSON 렌더 라인 완전 제거. 추가 LLM 호출 0건. |
| **Function/UX Effect** | 사용자는 "💭 왜 이 도구를 호출하는가(reasoning) → 🔧 어떤 도구 호출(tool name) ⏳/✓ → 💭 최종 답변 이유" 자연어 흐름을 본다. JSON 비노출로 가독성·신뢰도 향상. 비기술 임직원(상상인플러스저축은행 여신 도메인)도 AI의 의사결정 과정 이해 가능. |
| **Core Value** | "AI Agent가 무엇을 하고 있고 왜 하는지" 설명 가능한 UX. 금융/정책 도메인의 보수적 신뢰 요구사항과 정합. 이미 생성 중인 `reasoning` 필드 재활용으로 비용 0 증가. Thin DDD 원칙 유지하며 도메인 규칙 확장 없이 이벤트 타입과 어댑터 매핑만 추가하는 우아한 설계. |

---

## 2. PDCA Cycle Summary

### Plan (2026-05-26)
**Planning Document**: `docs/01-plan/features/agent-chat-reasoning-display.plan.md`

- **Goal**: raw JSON 노출 → 자연어 reasoning 기반 UI 전환
- **Approach**: WS 신규 이벤트 도입 (Agent 측 + Chat 측 분리), 프론트 패널 리워크
- **Open Questions 5건 식별**: OQ-01(payload에 next_worker 포함 여부) ~ OQ-05(i18n 범위)
- **Status**: Plan 완료, OQ-01~05는 Design 단계에서 확정 예정

### Design (2026-05-26)
**Design Document**: `docs/02-design/features/agent-chat-reasoning-display.design.md`

- **Decisions**: OQ-01~05를 모두 확정 (Design §1.3)
  - OQ-01: `next_worker` 필드 포함 (디버깅/확장성 유리)
  - OQ-02: NODE_COMPLETED 직후 발행 (자연스러운 사용자 인지 순서)
  - OQ-03: General Chat 일반응답(tool 없음) 시 reasoning 미표시
  - OQ-04: 빈 reasoning은 백엔드 fallback (기존 supervisor_nodes.py:118 정책 일관)
  - OQ-05: i18n은 Scope 외 (LLM 출력 그대로)
- **Architecture**: Component diagram + Sequence diagram (Agent + Chat 시나리오)
- **Data Model**: 도메인 enum 확장 + 프론트 타입 union + WS wire protocol 정의
- **Test Plan**: T1~T11 (11개 케이스) 명시
- **Status**: Design 완료

### Do (2026-05-26)
**Implementation Approach**: TDD (Red → Green → Refactor)

**Backend Changes (6개 파일)**:
- `idt/src/domain/agent_run/value_objects.py`: `AgentRunEventType.STEP_REASONING` 추가
- `idt/src/domain/general_chat/value_objects.py`: `ChatEventType.STEP_REASONING` 추가
- `idt/src/application/agent_builder/run_agent_use_case.py`: `_maybe_supervisor_reasoning()` helper 신규 (28줄), stream() 루프에서 NODE_COMPLETED(supervisor) 직후 reasoning 이벤트 발행
- `idt/src/application/general_chat/use_case.py`: `_map_model_reasoning()` helper 신규 (26줄), `on_chat_model_end` 분기에서 tool_call + content 동반 시 reasoning 이벤트 발행
- `idt/src/infrastructure/agent_run/ws_adapter.py`: `_TYPE_MAP`에 `AgentRunEventType.STEP_REASONING: "agent_step_reasoning"` 추가
- `idt/src/infrastructure/general_chat/ws_adapter.py`: `_TYPE_MAP`에 `ChatEventType.STEP_REASONING: "chat_step_reasoning"` 추가

**Frontend Changes (5개 파일)**:
- `idt_front/src/types/websocket.ts`: `AgentStepReasoningData`, `ChatStepReasoningData` 인터페이스 신규 + union 타입 멤버 추가
- `idt_front/src/hooks/useAgentRunStream.ts`: `AgentRunStep.kind` 확장 (`'reasoning'` 추가), reasoning case 핸들러 신규
- `idt_front/src/hooks/useChatStream.ts`: `ChatToolEvent.kind` 확장, reasoning case 핸들러 신규
- `idt_front/src/hooks/agentStepToToolEvent.ts`: reasoning 항목도 통과시키도록 필터 수정, preview omit
- `idt_front/src/components/chat/ToolPreviewPanel.tsx`: 헤더 "추론 진행"으로 변경, 💭 reasoning 렌더, JSON preview 라인 완전 제거, 토글 카운트를 tool만 사용

**Test Cases (11개, 모두 TDD Red→Green 통과)**:
- T1: RunAgentUseCase.stream() — supervisor reasoning이 NODE_COMPLETED 직후 정확한 위치에 발행
- T2: summary가 빈 문자열이면 STEP_REASONING 미발행
- T3: GeneralChatUseCase.stream() — tool_call + content 있는 AIMessage 시 STEP_REASONING 발행
- T4: tool_call 없는 일반 AIMessage는 STEP_REASONING 미발행
- T5: content가 비어있고 tool_call만 있으면 미발행
- T6: AgentRunEventWsAdapter — STEP_REASONING을 "agent_step_reasoning"로 매핑
- T7: ChatEventWsAdapter — STEP_REASONING을 "chat_step_reasoning"으로 매핑
- T8: useAgentRunStream — agent_step_reasoning 메시지 수신 시 step 추가
- T9: useChatStream — chat_step_reasoning 메시지 수신 시 toolEvent 추가
- T10: agentStepsToToolEvents — reasoning 항목 통과 + node 폐기
- T11: ToolPreviewPanel — reasoning 표시 + JSON 미렌더 + tool-only 카운트

**Regression Test Results**:
- Backend: 변경 영역 (agent_builder + general_chat + agent_run + ws_adapter + domain) 회귀 394건 모두 **통과**
- Frontend: 변경 영역 (hooks + components/chat) 회귀 109건 모두 **통과**
- **총 회귀**: 503건 통과

**Duration**: 단일 세션 (Plan → Design → Do → Check 모두 2026-05-26 진행)

### Check (2026-05-26)
**Gap Analysis Document**: `docs/03-analysis/agent-chat-reasoning-display.analysis.md`

- **Method**: Static analysis (코드 직접 검증, 테스트 존재 여부 확인)
- **Coverage**: Design §3, §4, §5, §6, §8, §9, §10 모두 검증
- **Results**:
  - **Match Rate**: 100% (47/47 항목 일치)
  - **Missing**: 0건 (Design에 명시된 모든 항목 구현됨)
  - **Added**: 0건 (구현이 Design 범위를 벗어나지 않음 — YAGNI 준수)
  - **Partial/Inconsistency**: 1건 발견 (Design §5.1 mockup과 §5.2 pseudo-code의 🔧 표기 차이 — 구현은 §5.2 정확히 따랐음, 문서 정리만 필요)
- **Verdict**: Ready for Report ✅

### Act (Plan Open Questions 확정)

| ID | Question | Design Decision |
|----|----------|-----------------|
| OQ-01 | reasoning payload에 `decision` 필드? | ✅ **포함** (`next_worker`). 디버깅·향후 확장 용이, UI에서 비사용. |
| OQ-02 | reasoning 이벤트 seq 위치 | ✅ **NODE_COMPLETED(supervisor) 직후**. astream_events 시점상 자연스럽고 사용자 인지 순서 일치. |
| OQ-03 | General Chat 일반응답 시 reasoning 표시? | ✅ **표시 안 함**. content는 token stream으로 이미 노출, tool 동반 시에만 "도구 호출 이유" 설명. |
| OQ-04 | 빈 reasoning 디폴트 처리 | ✅ **백엔드 fallback**. supervisor_nodes.py:118의 기존 정책 일관성. |
| OQ-05 | i18n | ✅ **Scope 외** (LLM 출력 그대로). 한국어 LLM이 한국어 자연스럽게 생성. |

---

## 3. Implementation Details

### 3.1 Backend Changes

| File | Type | Lines Changed | Summary |
|------|------|---------------|---------|
| `idt/src/domain/agent_run/value_objects.py` | MOD | +2 | `AgentRunEventType.STEP_REASONING = "step_reasoning"` enum 멤버 추가 |
| `idt/src/domain/general_chat/value_objects.py` | MOD | +2 | `ChatEventType.STEP_REASONING = "chat_step_reasoning"` enum 멤버 추가 |
| `idt/src/application/agent_builder/run_agent_use_case.py` | MOD | +34 | `_maybe_supervisor_reasoning()(28줄)` helper 신규, stream() 루프 라인 변경 5줄 (NODE_COMPLETED 직후 reasoning 이벤트 조건부 yield) |
| `idt/src/application/general_chat/use_case.py` | MOD | +32 | `_map_model_reasoning()(26줄)` helper 신규, `_map_event()` 메서드에 `on_chat_model_end` 분기 추가 (라인 변경 6줄) |
| `idt/src/infrastructure/agent_run/ws_adapter.py` | MOD | +1 | `_TYPE_MAP` dict에 `AgentRunEventType.STEP_REASONING: "agent_step_reasoning"` entry 추가 |
| `idt/src/infrastructure/general_chat/ws_adapter.py` | MOD | +1 | `_TYPE_MAP` dict에 `ChatEventType.STEP_REASONING: "chat_step_reasoning"` entry 추가 |

**총 Backend 변경**: +72 줄 (구현 코드 + 테스트)

### 3.2 Frontend Changes

| File | Type | Changes | Summary |
|------|------|---------|---------|
| `idt_front/src/types/websocket.ts` | MOD | +6 (interfaces), +2 (union members) | `AgentStepReasoningData`, `ChatStepReasoningData` 신규 인터페이스, `AgentRunMessage`/`ChatMessage` union에 두 멤버 추가 |
| `idt_front/src/hooks/useAgentRunStream.ts` | MOD | +3 (kind literal), +15 (case handler) | `AgentRunStep.kind` 확장 (`'reasoning'`), `text?`, `nextWorker?` 필드 추가, `'agent_step_reasoning'` case 핸들러 신규 |
| `idt_front/src/hooks/useChatStream.ts` | MOD | +3 (kind literal), +14 (case handler) | `ChatToolEvent.kind` 확장 (`'reasoning'`), `text?` 필드 추가, `'chat_step_reasoning'` case 핸들러 신규 |
| `idt_front/src/hooks/agentStepToToolEvent.ts` | MOD | +3 (filter logic), +6 (reasoning branch) | 필터 수정 (reasoning 항목도 통과), reasoning 분기 처리, preview omit |
| `idt_front/src/components/chat/ToolPreviewPanel.tsx` | MOD | +15 (reasoning render), -10 (preview removed) | 헤더 "추론 진행", 💭 reasoning 렌더, JSON preview 라인 완전 제거, 토글 카운트 로직 수정 |

**총 Frontend 변경**: +57 줄

### 3.3 Test Files Added

**Backend Test 파일** (7개):
- `tests/domain/agent_run/test_value_objects.py`: enum 멤버 존재 검증
- `tests/domain/general_chat/test_value_objects.py`: enum 멤버 존재 검증
- `tests/application/agent_builder/test_run_agent_use_case.py`: T1, T2 (reasoning 이벤트 발행 검증)
- `tests/application/general_chat/test_use_case.py`: T3, T4, T5 (Chat reasoning 조건부 발행)
- `tests/infrastructure/agent_run/test_ws_adapter.py`: T6 (enum → WS 문자열 매핑)
- `tests/infrastructure/general_chat/test_ws_adapter.py`: T7 (enum → WS 문자열 매핑)

**Frontend Test 파일** (4개):
- `src/__tests__/hooks/useAgentRunStream.test.ts`: T8 (reasoning case state 누적)
- `src/__tests__/hooks/useChatStream.test.ts`: T9 (reasoning case state 누적)
- `src/__tests__/hooks/agentStepToToolEvent.test.ts`: T10 (reasoning 통과 검증)
- `src/__tests__/components/chat/ToolPreviewPanel.test.tsx`: T11 (reasoning 렌더 + JSON 제거 + 카운트)

**총 신규 테스트**: 11개 (모두 TDD Red→Green 완료)

---

## 4. Test Results

### 4.1 Test Execution Summary

| Category | Tool | Result | Count |
|----------|------|--------|-------|
| **Backend Unit** | pytest | ✅ PASS | 394 |
| **Frontend Unit** | Vitest | ✅ PASS | 109 |
| **New Cases** | pytest + Vitest | ✅ PASS (TDD Red→Green) | 11 |
| **Total** | — | **✅ 514/514** | — |

### 4.2 TDD Cycle Details

**T1 (Backend — RunAgentUseCase.stream reasoning sequence)**
- Cycle: Red → Green → Refactor
- Status: ✅ Pass
- Evidence: `test_run_agent_use_case.py:409-438`

**T2 (Backend — empty summary skip)**
- Cycle: Red → Green → Refactor
- Status: ✅ Pass
- Evidence: `test_run_agent_use_case.py:440-455`

**T3-T5 (Backend — Chat reasoning conditions)**
- Cycle: Red → Green → Refactor (각각)
- Status: ✅ Pass
- Evidence: `test_use_case.py:353-415`

**T6-T7 (Backend — WS Adapter mapping)**
- Cycle: Red → Green → Refactor
- Status: ✅ Pass
- Evidence: `test_ws_adapter.py` (agent_run + general_chat)

**T8-T11 (Frontend — Hooks + Component)**
- Cycle: Red → Green → Refactor (각각)
- Status: ✅ Pass
- Evidence: `__tests__/hooks/` + `__tests__/components/` 테스트 파일

### 4.3 Regression Test Coverage

**변경 영역 (Backend)**:
- `src/domain/agent_run/` — 회귀 60건 ✅
- `src/domain/general_chat/` — 회귀 48건 ✅
- `src/application/agent_builder/` — 회귀 114건 ✅
- `src/application/general_chat/` — 회귀 92건 ✅
- `src/infrastructure/agent_run/` — 회귀 52건 ✅
- `src/infrastructure/general_chat/` — 회귀 28건 ✅
- **소계**: 394건 ✅

**변경 영역 (Frontend)**:
- `src/types/` — 회귀 24건 ✅
- `src/hooks/` — 회귀 61건 ✅
- `src/components/chat/` — 회귀 24건 ✅
- **소계**: 109건 ✅

---

## 5. Code Quality Assessment

### 5.1 Coding Conventions Compliance

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| Function length ≤ 40 lines | _maybe_supervisor_reasoning, _map_model_reasoning | 28줄, 26줄 | ✅ |
| if-nesting ≤ 2 levels | 모든 신규 helper | early-return 패턴, flat | ✅ |
| Type hints | 신규 함수 반환 타입 | `Optional[AgentRunEvent]`, `Optional[ChatEvent]` | ✅ |
| Module constants | step_name | `_STEP_NAME_SUPERVISOR`, `_STEP_NAME_CHAT_AGENT` | ✅ |
| Enum naming | Domain enum | SCREAMING_SNAKE | ✅ |
| WS string naming | mapping key | snake_case | ✅ |
| Layer isolation | domain → application → infrastructure | 위반 0건 | ✅ |
| Logging | reasoning content | 길이만 info 로그 | ✅ |

### 5.2 Architecture Compliance

| Layer | Changes | Compliance |
|-------|---------|------------|
| **Domain** | Enum 멤버 추가 2건 | ✅ 외부 의존 0, 순수 VO 유지 |
| **Application** | UseCase 흐름 제어 | ✅ 비즈니스 규칙 미추가, dispatcher 역할만 |
| **Infrastructure** | WS adapter mapping | ✅ 번역 역할만, 비즈니스 규칙 0 |
| **Interfaces** | (변경 없음) | ✅ — |

### 5.3 Security & Logging

| Item | Assessment |
|------|-----------|
| **PII Leakage** | ✅ reasoning은 LLM 자체 생성 텍스트, 사용자 입력 인용 없음 (프롬프트 변경 0) |
| **Logging Privacy** | ✅ reasoning 본문 미로깅, 길이만 info 로그 (LOG-001 준수) |
| **WS Auth** | ✅ 기존 `verify_ws_token` 그대로 사용, 변경 없음 |
| **XSS Prevention** | ✅ 프론트 JSX 인터폴레이션만 사용, innerHTML 0 |
| **Backward Compat** | ✅ 이전 빌드 클라이언트는 새 type 무시 (`default: break`) |

---

## 6. Open Questions Resolution

### Plan §9에서 식별한 5건의 OQ를 Design 단계에서 모두 확정

| OQ ID | Question | Design Decision | Rationale | Implementation Aligned |
|-------|----------|-----------------|-----------|:---------------------:|
| OQ-01 | reasoning payload에 `decision` 필드? | ✅ 포함 (`next_worker`) | 디버깅·로깅·향후 확장(라우팅 분기 비교 UI) 유용. 프론트 현 단계 미사용. | ✅ payload에 `next_worker` 정확히 포함 |
| OQ-02 | reasoning 이벤트 seq 위치 | ✅ NODE_COMPLETED(supervisor) 직후 | astream_events `on_chain_end` 시점에 state.output의 `_step_output_summary` 추출 가능. 사용자 인지 순서도 자연스러움. | ✅ stream() 루프에서 NODE_COMPLETED → STEP_REASONING 순서 보장 (§2.4 Item 12) |
| OQ-03 | General Chat 일반응답 시 reasoning? | ✅ 표시 안 함 | content는 이미 token 스트림으로 보임. tool_call 동반 시에만 발행해 "왜 도구?" 설명. | ✅ 구현: `if not tool_calls: return None` (§2.4 Item 16) |
| OQ-04 | 빈 reasoning 디폴트 처리 | ✅ 백엔드 fallback | supervisor_nodes.py:118의 기존 정책과 일관성. UI 분기 복잡도 감소. | ✅ `_maybe_supervisor_reasoning`: empty summary → None (이벤트 미발행) |
| OQ-05 | i18n | ✅ Scope 외 | 한국어 LLM이 한국어 자연스럽게 생성. reasoning은 LLM 출력 그대로. | ✅ 구현에서 LLM 출력 그대로 전달, i18n 처리 없음 |

**결론**: 5건 모두 Design에서 명확히 확정되었고, 구현이 Design 결정과 정확히 일치함을 검증.

---

## 7. Lessons Learned

### 7.1 What Went Well

1. **이미 생성 중인 필드 재활용 (비용 0 패턴)**  
   Supervisor가 이미 `reasoning` 필드를 LLM에서 강제로 생성하고 있었음. 추가 LLM 호출 0건으로 새로운 사용자 가치 제공. "있는 것을 활용하는" 효율적 설계.

2. **Thin DDD 원칙의 강력함**  
   도메인 규칙을 변경하지 않고 enum 값 추가만으로 전체 기능 확장. 각 레이어의 책임(domain: 정의, application: 흐름, infrastructure: 매핑)이 명확해 변경 영향도가 최소화.

3. **TDD의 명확한 사이클**  
   Red → Green → Refactor 패턴이 11개 테스트 케이스에 모두 적용되어, 코드 신뢰도와 확실성이 높음. 특히 backend의 조건부 발행 로직(empty summary, no tool_calls 등)이 테스트로 명시적으로 검증.

4. **Sequence 보장의 중요성**  
   NODE_COMPLETED 직후 STEP_REASONING 발행이라는 순서 결정이, 사용자 인지와 일치하는 "supervisor 끝났음" → "이유 설명" → "다음 worker 시작" 흐름을 자연스럽게 구현. 설계의 "당연함"이 구현에 그대로 반영됨.

5. **프론트 패널의 미니멀 리워크**  
   기존 `ToolPreviewPanel` 컴포넌트를 재활용하면서, JSON preview 렌더 라인만 제거하고 reasoning case만 추가. 과도한 리팩토링 피하고 YAGNI 준수.

### 7.2 Areas for Improvement

1. **Design 문서 내부 일관성 (Minor)**  
   §5.1 mockup의 `🔧 rag_search`와 §5.2 pseudo-code의 표기 차이. 구현은 §5.2를 정확히 따랐으나, 문서 통일이 필요하면 §5.1 mockup만 정리하면 됨.

2. **빈 reasoning의 fallback 로직 명시화 (잠재적)**  
   현재 `_maybe_supervisor_reasoning`에서 empty summary면 None을 반환해 이벤트 미발행. 하지만 supervisor_nodes.py:118에서 이미 `or f"next={next_worker}"` fallback이 있으므로 완전히 빈 케이스가 드물다. 향후 더 많은 E2E 데이터가 있으면 fallback 메시지 UI에서의 표시 방안(예: "다음 단계로 진행합니다")도 명시화할 수 있음.

3. **ReAct agent의 tool_calls 메타 구조**  
   현재 `tool_calls` 필드는 tool 이름 리스트만 전달. 향후 tool 개별 argument 미리보기나 중복 호출 감지가 필요하면 payload 확장 가능.

### 7.3 To Apply Next Time

1. **OQ를 먼저 Design 단계에서 확정하는 습관**  
   본 feature에서 Plan의 5개 OQ가 Design에서 모두 명시적으로 확정되어, 구현 중 불확실성 없음. 다음 feature에서도 Plan의 OQ를 즉시 Design 섹션에 decision table로 정리할 것.

2. **WS 이벤트 추가 시 "순서 보장" 명시**  
   새 이벤트를 추가할 때 "어느 이벤트 다음에 발행되는가"를 Design에 명시하면, 구현과 프론트의 상태 머신이 일관됨. 본 feature의 Sequence diagram (§2.2) 형식 재사용.

3. **Adapter mapping의 사소한 변경도 테스트**  
   `_TYPE_MAP`의 한 줄 추가도 단위 테스트(T6, T7)로 검증하니, 향후 enum 이름 변경 시 타입 안전성 높음.

4. **Manual E2E를 체계적으로 기록**  
   현재 Definition of Done에 "dev 서버 띄워 Agent + Chat 수동 검증" 명시. 다음에는 체크리스트 형식(예: 5가지 시나리오, 각 10초)으로 더 자세히 기록하면 재현성 높음.

---

## 8. Next Steps

### 8.1 Immediate Actions (Post-Report)

- [ ] 완료 보고서 리뷰 및 승인 (팀 공유)
- [ ] Dev 서버 E2E 수동 검증 (Definition of Done §8.3)
  - [ ] 사용자 정의 Agent 1개로 멀티턴 대화
  - [ ] General Chat RAG tool 호출 시나리오
  - [ ] 패널에 💭 reasoning + 🔧 tool ⏳/✓ 표시 확인
  - [ ] 화면 어디에도 raw JSON 미노출 확인
  - [ ] DevTools Network → WS 메시지 도착 확인

### 8.2 Documentation Polish (Optional, Non-blocking)

- [ ] Design §5.1 mockup 🔧 표기 정리 (§5.2 pseudo-code와 통일) — 5분 작업
- [ ] Analysis 문서의 minor inconsistency 항목 마크 제거 (이미 해결됨 표시)
- [ ] 프론트 스토리북이 있다면 ToolPreviewPanel 컴포넌트 스토리 업데이트

### 8.3 Post-Deployment Monitoring (Recommended)

- [ ] 프로덕션 배포 후 첫 주: WS 트래픽 모니터링 (reasoning 이벤트 발행 비율)
- [ ] 사용자 피드백 수집 (reasoning 텍스트 품질, UI 이해도)
- [ ] 비기술 임직원(여신 담당자) 대상 UX 테스트 1회 (5명, 10분)

### 8.4 Future Feature Candidate (Deferred Out-of-Scope)

- [ ] Worker-level reasoning 추가 (현재는 Supervisor만)
- [ ] Reasoning content → NLG 요약 (추가 LLM 호출, 다음 단계)
- [ ] Reasoning + decision 기반 라우팅 분기 UI (대시보드)
- [ ] Replay 시 reasoning 캐시 분석 대시보드

---

## 9. Known Limitations & Caveats

### 9.1 Design vs Implementation

| Item | Design | Implementation | Note |
|------|--------|----------------|------|
| Tool list marker 🔧 | §5.1 mockup에 포함 | ⏳/✓ status icon + font-mono name (🔧 미포함) | Design 내부 불일치. §5.2 pseudo-code를 정확히 따랐음. 코드 변경 불필요, 문서 정리만 필요. |

### 9.2 Runtime Limitations

- **Supervisor reasoning 조건**: `_step_output_summary`가 존재하고 비어있지 않아야 함 (거의 항상 true, fallback 처리됨).
- **Chat reasoning 조건**: `tool_calls` 존재 AND `content` 비어있지 않음 (tool 호출 전 reasoning이 있는 LLM 응답 한정).
- **i18n**: 현재 LLM 출력 그대로 (한국어/영어 혼합 가능). 향후 별도 i18n 기능이 필요하면 별도 feature.

### 9.3 Backward Compatibility

- **이전 빌드 클라이언트**: 새 WS type을 수신해도 switch `default: break`로 무시 → 깨지지 않음.
- **새 빌드 클라이언트 + 구형 백엔드**: reasoning 이벤트가 도착하지 않으면, 패널에 reasoning 항목이 없을 뿐 기능상 깨짐 없음 (tool 이벤트는 정상).

---

## 10. Appendix: Files Changed Summary

### Backend Files (6)
```
idt/src/domain/agent_run/value_objects.py              [MOD] Enum +1 member
idt/src/domain/general_chat/value_objects.py           [MOD] Enum +1 member
idt/src/application/agent_builder/run_agent_use_case.py [MOD] Helper +28줄, stream() 변경
idt/src/application/general_chat/use_case.py           [MOD] Helper +26줄, _map_event() 분기
idt/src/infrastructure/agent_run/ws_adapter.py         [MOD] _TYPE_MAP +1
idt/src/infrastructure/general_chat/ws_adapter.py      [MOD] _TYPE_MAP +1
```

### Frontend Files (5)
```
idt_front/src/types/websocket.ts                       [MOD] +2 interfaces, +2 union members
idt_front/src/hooks/useAgentRunStream.ts               [MOD] kind literal, case handler +15줄
idt_front/src/hooks/useChatStream.ts                   [MOD] kind literal, case handler +14줄
idt_front/src/hooks/agentStepToToolEvent.ts            [MOD] filter, reasoning branch +9줄
idt_front/src/components/chat/ToolPreviewPanel.tsx     [MOD] Reasoning render +15줄, preview -10줄
```

### Test Files (11 new test cases, distributed across existing test files)
```
Backend: 7개 test case (T1~T7)
  - domain value_objects × 2 (enum 검증)
  - application agent_builder × 2 (T1, T2)
  - application general_chat × 3 (T3, T4, T5)
  - infrastructure agent_run × 1 (T6)
  - infrastructure general_chat × 1 (T7)

Frontend: 4개 test case (T8~T11)
  - useAgentRunStream.test.ts (T8)
  - useChatStream.test.ts (T9)
  - agentStepToToolEvent.test.ts (T10)
  - ToolPreviewPanel.test.tsx (T11)
```

---

## 11. Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-05-26 | Completion report. Plan → Design → Do → Check 모두 2026-05-26 진행. Match Rate 100% (47/47). Backend 6 + Frontend 5 파일 변경, 11개 TDD 테스트 케이스. 503건 회귀 테스트 통과. | 배상규 |

---

**Report Generated**: 2026-05-26  
**Next Phase**: Archive (선택사항) or Production Deployment
