---
template: plan
version: 1.2
feature: agent-chat-reasoning-display
date: 2026-05-26
author: 배상규
project: sangplusbot
---

# agent-chat-reasoning-display Planning Document

> **Summary**: 채팅 중간 진행 표시를 raw JSON(input_preview/output_preview) 대신 "추론 이유 + 선택한 tool" 형태로 전환한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-05-26
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 사용자 정의 Agent / General Chat 모두 중간 진행을 보여줄 때 `input_preview`·`output_preview`가 `_truncate_json()` 결과(`{"query":"..."}` 같은 raw JSON 문자열) 그대로 화면에 노출되어 가독성이 낮고 비기술 사용자에게 의미가 전달되지 않는다. Supervisor가 이미 생성하는 `reasoning`(왜 이 worker를 골랐는가)도 WS 이벤트로 송출되지 않아 버려지고 있다. |
| **Solution** | (1) 백엔드: `SupervisorDecision.reasoning`을 새 WS 이벤트(`agent_step_reasoning`)로 송출. (2) General Chat의 ReAct agent에서는 tool_call 직전 AI 메시지의 content를 reasoning으로 추출해 동일한 이벤트(`chat_step_reasoning`)로 송출. (3) 프론트: 기존 `ToolPreviewPanel`을 "추론 진행" 패널로 개편 — `{reasoning → tool name}` 시퀀스만 표시. `input_preview/output_preview`는 UI 미사용(payload 자체는 호환을 위해 유지, 단 화면 노출만 제거). |
| **Function/UX Effect** | 사용자는 "왜 그 도구를 호출했는지 → 어떤 도구를 호출했는지 → 완료"의 자연어 흐름을 본다. JSON 미노출로 가독성·신뢰도 향상. 비기술 임직원(상상인플러스저축은행 여신 도메인)도 진행 상황을 이해 가능. |
| **Core Value** | "AI Agent가 무엇을 하고 있는지" 설명 가능한 UX. 금융/정책 도메인의 보수적 신뢰 요구사항과 정합. 추가 LLM 호출 0건(이미 reasoning 필드는 생성 중) → 비용 증가 없음. |

---

## 1. Overview

### 1.1 Purpose

현재 두 채팅 화면(`/ws/agent/{run_id}`, `/ws/chat/{session_id}`)에서 중간 진행 정보를 표시할 때 LangGraph가 넘긴 tool input/output dict가 `json.dumps`된 raw 문자열로 그대로 노출된다. 이를 (a) "왜 이 단계가 실행되었는지(reasoning)"와 (b) "어떤 tool이 호출되었는지"만 남기는 형태로 정리한다.

### 1.2 Background

- 백엔드 `RunAgentUseCase._map_tool_start/end` (`idt/src/application/agent_builder/run_agent_use_case.py:516-548`) — `_truncate_json(data.get("input"))`을 그대로 `input_preview`로 전송.
- 백엔드 `GeneralChatUseCase._map_tool_start/end` (`idt/src/application/general_chat/use_case.py:284-316`) — 동일 패턴.
- 프론트 `ToolPreviewPanel` (`idt_front/src/components/chat/ToolPreviewPanel.tsx:60-62`) — `e.preview`를 truncate만 적용 후 그대로 출력 → 사용자가 본 "JSON 자체".
- `SupervisorDecision.reasoning` (`idt/src/application/agent_builder/supervisor_nodes.py:50-56`) — 이미 LLM에게 강제로 받고 있는 required 필드. `_step_output_summary`로 state에 저장은 되지만 WS 이벤트로 송출은 안 됨.
- 사용자 답변(2026-05-26 클라리피케이션): "추론 과정 즉 이유와 어떤 툴을 선택했는지만 보여주고 싶다", "JSON은 완전히 숨김", "패널은 메시지 위 현재 위치 유지".

### 1.3 Related Documents

- 기존 설계: `docs/02-design/features/fe-websocket-integration-guide.design.md` §5.3-5.4
- 기존 설계: `docs/02-design/features/ws-chat-streaming.design.md` §3.6 / §5.4
- 기존 설계: `docs/02-design/features/ws-agent-chat-streaming.design.md` §3.1-3.3
- AGENT-OBS-003 (이미 reasoning을 `_step_output_summary`로 저장 중)
- 루트 규칙: `CLAUDE.md` §4.1 API 계약 동기화

---

## 2. Scope

### 2.1 In Scope

- [ ] **백엔드 - Agent**: `RunAgentUseCase`가 supervisor `_step_output_summary`(reasoning)를 새 이벤트 타입(`AgentRunEventType.STEP_REASONING`)으로 송출
- [ ] **백엔드 - Chat**: `GeneralChatUseCase`가 tool_call 직전 AI 메시지 content를 reasoning으로 추출해 `ChatEventType.STEP_REASONING`으로 송출
- [ ] **백엔드 - 도메인**: `AgentRunEvent` / `ChatEvent` value object에 새 event type 추가
- [ ] **백엔드 - WS Adapter**: `AgentRunEventWsAdapter`, `ChatEventWsAdapter`에 새 이벤트 매핑 추가 (`agent_step_reasoning`, `chat_step_reasoning`)
- [ ] **프론트 - 타입**: `idt_front/src/types/websocket.ts`에 `AgentStepReasoningData`, `ChatStepReasoningData` 및 discriminated union 멤버 추가
- [ ] **프론트 - 훅**: `useAgentRunStream`, `useChatStream`에서 reasoning 이벤트 처리, `AgentRunStep`/`ChatToolEvent`에 `kind: 'reasoning'` 추가
- [ ] **프론트 - 변환**: `agentStepsToToolEvents` reasoning 항목도 통과시키도록 수정 (현재는 `kind === 'tool'`만 통과)
- [ ] **프론트 - 패널**: `ToolPreviewPanel`을 "추론 진행"으로 리네이밍/리워크 — reasoning은 💭 아이콘 + 자연어, tool은 🔧 아이콘 + 이름만, JSON preview 렌더 코드 제거
- [ ] **테스트**: 백엔드 pytest (`tests/application/agent_builder/test_run_agent_use_case.py`, `test_supervisor_nodes.py`, `test_use_case.py` for general chat) — reasoning 이벤트 송출 검증. 프론트 Vitest — 패널 렌더링 + 훅 상태 머신.

### 2.2 Out of Scope

- Worker LLM 응답에 별도 reasoning 필드 추가 (사용자 답변: Supervisor reasoning만)
- LLM 추가 호출이 필요한 자연어 변환(JSON → 한 줄 요약) 방안 — 비용·지연 증가로 제외
- `input_preview/output_preview` payload 자체 제거 (디버깅/로깅 호환을 위해 페이로드는 유지, 화면 노출만 제거)
- LangSmith 트레이스 UI 변경
- Quality Gate / Worker step에 reasoning 추가 — 차후 별도 feature
- WebSocket replay cache 동작 변경 (이벤트 시퀀스에 새 type만 추가)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 사용자 정의 Agent 실행 시, Supervisor가 결정을 내릴 때마다 `reasoning` 텍스트가 WS 이벤트로 클라이언트에 전달된다 (tool 선택 / FINISH 케이스 모두) | High | Pending |
| FR-02 | General Chat ReAct agent 실행 시, tool_calls를 가진 AI 메시지의 텍스트 content를 reasoning으로 추출해 WS 이벤트로 전달한다. content가 비어 있으면 이벤트를 발행하지 않는다(잡음 방지) | High | Pending |
| FR-03 | 프론트엔드는 reasoning과 tool을 시간 순서대로 한 패널에 표시한다. 형식: `💭 {reasoning}` 줄과 그 다음 `🔧 {tool_name} [duration]` 줄. 완료된 tool은 `✓`, 진행 중은 `⏳`. | High | Pending |
| FR-04 | `input_preview`, `output_preview` 페이로드 값은 어떠한 화면 영역에도 렌더링되지 않는다. (백엔드 송신은 호환 위해 유지) | High | Pending |
| FR-05 | reasoning이 LLM 실패로 비어있을 때(supervisor fallback `next={next_worker}`) 디폴트 문구로 대체되어 표시된다 (이미 백엔드 `supervisor_nodes.py:118`에서 fallback 처리됨) | Medium | Pending |
| FR-06 | 패널 토글(`도구 호출 보기 (N)` / `숨기기`)은 유지하되 카운트는 "reasoning + tool" 합산 개수가 아닌 "tool" 개수만 사용 (사용자 직관 유지) | Medium | Pending |
| FR-07 | WS replay cache(ws-chat-streaming) 재접속 시에도 새 reasoning 이벤트가 정상 복원된다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 추가 LLM 호출 0건. Supervisor당 단일 WS 메시지 추가(< 2KB) | 코드 리뷰 + WS 페이로드 크기 측정 |
| Compatibility | 기존 클라이언트(이전 빌드)는 알 수 없는 type(`agent_step_reasoning`)을 default 분기에서 무시 → 깨지지 않음 | `useAgentRunStream`/`useChatStream`의 `default: break` 패턴 |
| Test Coverage | 백엔드: reasoning 이벤트 송출 단위 테스트 추가, 기존 `test_supervisor_nodes`·`test_run_agent_use_case` 회귀 통과. 프론트: 패널 + 훅 테스트 추가 | pytest + vitest |
| Security | reasoning 텍스트에 사용자 PII 누수 가능성 — Supervisor가 사용자 메시지를 그대로 인용하지 않도록 프롬프트 그대로 유지(현재 reasoning은 모델 자체 생성) | 코드 리뷰 |
| Logging | 백엔드 LoggerInterface로 reasoning 길이만 info 로그(내용 미로깅) | LOG-001 / `logging.md` 규칙 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] Supervisor reasoning이 WS로 송출되어 프론트 패널에 표시됨 (E2E 수동 검증, 실제 사용자 정의 Agent 1개로 확인)
- [ ] General Chat에서 RAG tool 호출 직전 reasoning이 표시됨 (수동 검증)
- [ ] 화면 어디에서도 `{"query": "..."}` 형태 raw JSON이 보이지 않음
- [ ] 백엔드 pytest 통과 + 새 단위 테스트 추가
- [ ] 프론트 Vitest 통과 + 새 단위 테스트 추가
- [ ] `docs/02-design/features/agent-chat-reasoning-display.design.md` 작성 완료
- [ ] CLAUDE.md §4.1 API 계약 동기화 체크리스트 통과 (백엔드 enum/스키마 ↔ 프론트 타입)

### 4.2 Quality Criteria

- [ ] 백엔드 함수 길이 40줄 제한 준수 (`CLAUDE.md` §3)
- [ ] 레이어 위반 0 (`verify-architecture` skill 통과)
- [ ] LOG-001 통과 (`verify-logging` skill)
- [ ] 백엔드 TDD: 테스트가 먼저 실패 → 구현 후 통과 순서 유지
- [ ] Gap analysis Match Rate ≥ 90%

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Supervisor가 reasoning 필드를 비어 있게 반환(LLM 일탈) | Medium | Low | 이미 `supervisor_nodes.py:118`에서 `or f"next={next_worker}"` fallback. 빈 reasoning일 때 이벤트 생략 옵션도 도입 |
| ReAct agent의 AI 메시지 content가 비어있고 tool_calls만 있을 수 있음(특정 모델) | Medium | Medium | content 비어 있으면 reasoning 이벤트를 발행하지 않고 그대로 tool 이벤트만 표시 (자연스럽게 degrade) |
| 이전 빌드 프론트가 새 이벤트 type을 받았을 때 동작 | Low | Low | 두 훅 모두 switch의 `default: break` — 무시되므로 안전 |
| reasoning에 한국어 + 영어 혼합 길이가 1024 chars 초과 | Low | Low | 이미 `step_summary[:1024]` 슬라이스됨 |
| LangSmith 트레이스/관측성 코드와 충돌(`_step_output_summary` 활용 중) | Medium | Low | 신규 이벤트 송출은 기존 `_step_output_summary` 흐름과 분리, 동일 값 재사용 |
| 사용자 정의 Agent는 supervisor 외 worker도 reasoning 보내고 싶어할 수 있음 | Low | Medium | Out of Scope에 명시 — 다음 feature로 분리 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단일 정적 사이트 | - | ☐ |
| **Dynamic** | feature-based, BaaS | - | ☐ |
| **Enterprise** | 엄격한 레이어, DI | sangplusbot(이미 채택) | ☑ |

본 feature는 기존 Thin DDD(`domain`/`application`/`infrastructure`/`interfaces`) 구조 안에서 신규 이벤트 타입과 WS 어댑터 매핑만 추가한다.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| reasoning 전송 방식 | (A) 별도 새 이벤트 타입 / (B) `agent_node_completed` payload 확장 / (C) HTTP polling | **(A) 새 이벤트 타입** | tool 흐름과 분리 가능, 옵트인 가능, replay cache와 호환 |
| reasoning 추출 위치(Agent) | (A) supervisor_node return / (B) astream_events에서 `_step_output_summary` 추출 / (C) 별도 callback | **(B) astream_events에서 추출** | `_step_output_summary`가 이미 state로 흐르고 chain_end에서 관측 가능. supervisor 수정 최소화 |
| reasoning 추출 위치(Chat) | (A) on_chat_model_end의 AIMessage.content / (B) on_tool_start 직전 buffer | **(A) on_chat_model_end** | LangGraph v2 이벤트 이름 명확, tool_calls 메타 존재 시에만 발행 |
| 백워드 호환 | (A) preview 필드 즉시 제거 / (B) 페이로드 유지 + UI에서만 숨김 | **(B) UI에서만 숨김** | 디버깅/로깅/MCP 도구 호환성 보장. 추후 별도 feature로 제거 가능 |
| 신규 이벤트 enum 이름 | `STEP_REASONING` / `SUPERVISOR_DECISION` / `THINKING` | **`STEP_REASONING`** | Agent(Supervisor)와 Chat(ReAct) 모두에 의미 통일 가능 |

### 6.3 Clean Architecture Approach

```
Layer 영향 (Thin DDD):

domain/
  agent_run/value_objects.py
    └─ AgentRunEventType.STEP_REASONING  ← 추가
  general_chat/value_objects.py
    └─ ChatEventType.STEP_REASONING      ← 추가

application/
  agent_builder/run_agent_use_case.py
    ├─ _map_chain_end()                  ← _step_output_summary 추출 → STEP_REASONING 이벤트
    └─ supervisor_nodes.py               ← 변경 없음 (이미 _step_output_summary 생성 중)
  general_chat/use_case.py
    └─ _map_event()                      ← on_chat_model_end 핸들러 추가

infrastructure/
  agent_run/ws_adapter.py
    └─ STEP_REASONING → "agent_step_reasoning" 매핑 추가
  general_chat/ws_adapter.py
    └─ STEP_REASONING → "chat_step_reasoning" 매핑 추가

interfaces/
  api/routes/ws_router.py                ← 변경 없음 (어댑터가 자동 처리)

(프론트 idt_front/)
  src/types/websocket.ts                 ← 신규 type union 멤버 추가
  src/hooks/useAgentRunStream.ts         ← case 추가 + AgentRunStep 'reasoning' 추가
  src/hooks/useChatStream.ts             ← case 추가 + ChatToolEvent 'reasoning' 추가
  src/hooks/agentStepToToolEvent.ts      ← reasoning 통과 로직
  src/components/chat/ToolPreviewPanel.tsx ← 렌더 리워크 (JSON 제거)
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` (루트 + `idt/CLAUDE.md` + `idt_front/CLAUDE.md`) — 모두 존재
- [x] `docs/rules/logging.md` (LOG-001), `docs/rules/db-session.md`, `docs/rules/testing.md`
- [x] `tsconfig.json`, ESLint(프론트), pytest 설정(백엔드)
- [x] `docs/task-registry.md` (Task 등록 규칙)

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **WS Event 명명** | `agent_node_*`, `chat_token` 등 snake_case 일관 | `agent_step_reasoning`, `chat_step_reasoning` 동일 패턴 적용 | High |
| **Domain Enum 명명** | `AgentRunEventType.*`, `ChatEventType.*` SCREAMING_SNAKE | `STEP_REASONING` 동일 패턴 | High |
| **프론트 Step kind 명명** | `'node' | 'tool'` | `'reasoning'` 추가 (literal union 확장) | High |
| **테스트 위치** | 백 `tests/application/...`, 프론트 `__tests__/` 또는 `*.test.ts` | 동일 유지 | - |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (none) | - | - | ☐ |

신규 환경 변수 없음. 모든 변경은 기존 코드 경로 안에서 이루어진다.

### 7.4 Pipeline Integration

본 feature는 9-phase 파이프라인 중 **Phase 4 (API)** + **Phase 6 (UI Integration)** 사이의 점진적 개선에 해당. 새 phase 진입 없이 PDCA 사이클(Plan → Design → Do → Check → Act → Report)만 수행한다.

---

## 8. Implementation Plan (참고)

> 실제 구현 순서는 Design 단계에서 확정. 여기서는 큰 그림만.

1. **백엔드 - 도메인**
   - `AgentRunEventType.STEP_REASONING`, `ChatEventType.STEP_REASONING` 추가
   - 새 payload schema(`step_name`, `reasoning`, optional `decision`)

2. **백엔드 - Application (TDD)**
   - 테스트 먼저: "supervisor 실행 후 STEP_REASONING 이벤트가 정확한 순서로 yield된다"
   - `RunAgentUseCase._map_chain_end()` 수정 — output에 `_step_output_summary` 있으면 reasoning 이벤트 yield
   - `GeneralChatUseCase._map_event()` — `on_chat_model_end` 분기 추가, AIMessage.content + tool_calls 존재 시 reasoning 이벤트 yield

3. **백엔드 - WS Adapter**
   - 두 adapter에 새 매핑 추가
   - 단위 테스트: adapter가 STEP_REASONING을 올바른 type 문자열로 변환

4. **프론트 - 타입 & 훅**
   - `websocket.ts`에 신규 인터페이스 + union 멤버
   - `useAgentRunStream`, `useChatStream` switch 케이스 추가
   - `AgentRunStep`/`ChatToolEvent`에 `kind: 'reasoning'` 추가, payload는 `text: string`

5. **프론트 - 패널 리워크**
   - `ToolPreviewPanel` → "추론 진행 패널"로 리네이밍(타이틀만 변경, 컴포넌트명은 유지 가능)
   - `preview` 표시 라인(line 60-62) 제거
   - reasoning 항목 렌더 추가 (`💭 {text}`)
   - `agentStepsToToolEvents` reasoning 통과

6. **테스트 / 회귀**
   - 백엔드 pytest 실행
   - 프론트 vitest 실행
   - 개발 서버 띄워서 실제 Agent + General Chat 시나리오 수동 검증

7. **검증**
   - `/pdca analyze agent-chat-reasoning-display` 실행 → gap-detector
   - Match Rate ≥ 90% 확인 후 `/pdca report`

---

## 9. Open Questions (Design 단계에서 결정)

| ID | Question | 기본 가정 |
|----|----------|----------|
| OQ-01 | reasoning 이벤트의 payload에 `decision`(next worker name) 필드를 같이 넣을지? | 넣는다 — 디버깅·확장성. 프론트에서는 표시 안 함 |
| OQ-02 | reasoning 이벤트의 `seq` 위치 — `NODE_STARTED` 이전 vs 이후 vs `NODE_COMPLETED` 직후? | `NODE_COMPLETED`(supervisor) 직후. 추론 → 결정 → 실행 순서가 가장 자연스럽지만 supervisor가 이미 결정한 후 reasoning이 알려지므로 |
| OQ-03 | General Chat의 ReAct agent에서 tool_call 없이 일반 응답일 때 reasoning을 표시할 것인가? | 표시 안 함(잡음). content는 token stream으로 이미 노출됨 |
| OQ-04 | 빈 reasoning 시 디폴트 텍스트("다음 단계로 진행합니다") 표시 여부 | 표시. fallback 동작은 일관성에 유리 |
| OQ-05 | i18n? 현재 reasoning은 LLM이 생성하므로 한국어/영어가 섞일 수 있음 | Scope 외, LLM 출력 그대로 |

---

## 10. Next Steps

1. [ ] 본 Plan 검토 및 승인
2. [ ] `/pdca design agent-chat-reasoning-display` — Design 문서 작성 (OQ-01~05 결정)
3. [ ] TDD로 백엔드부터 구현 (`/pdca do agent-chat-reasoning-display`)
4. [ ] 프론트 구현
5. [ ] Gap 분석 → 필요 시 iterate → 완료 보고서

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-26 | Initial draft (사용자 클라리피케이션 4건 반영) | 배상규 |
