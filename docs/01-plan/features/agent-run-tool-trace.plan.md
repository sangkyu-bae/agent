# agent-run-tool-trace Planning Document

> **Summary**: 에이전트 답변 아래에 그 실행에서 호출한 도구(MCP 포함)와 추론을 시간 순서로 접어 두고, 각 호출의 입력·결과를 펼쳐 볼 수 있게 한다. 세션을 다시 열어도 복원한다.
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-03
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 채팅 화면은 스트리밍 중에만 하단 "추론 진행" 패널에 도구 이름과 소요 시간을 보여 주고, 도구가 받은 입력과 돌려준 결과는 보여 주지 않는다. 답변이 끝나거나 세션을 다시 열면 그마저 사라져, 사용자는 도구가 실제로 값을 가져왔는지 확인할 수 없다. |
| **Solution** | 실행 기록(`ai_tool_call`, `ai_run_step`)을 시간 순서의 "도구 실행 내역"으로 조립하는 정책을 만들고, 실시간 WS 이벤트와 세션 단위 조회 API가 같은 표시 형태를 쓰게 한다. 프론트는 답변마다 접이식 내역과 호출별 드릴다운을 표시한다. |
| **Function/UX Effect** | 답변 아래 "도구 실행 내역 (N)"을 펼치면 추론 → 도구 → 추론 순서가 보이고, 각 호출을 펼치면 정리된 입력(키: 값)과 결과(텍스트·정리된 JSON)를 볼 수 있다. 원문 보기 토글, 잘림 표시, 실패 사유, 서브에이전트 워커 라벨을 제공한다. |
| **Core Value** | P2(에이전트 소유자)가 채팅 화면에서 바로 도구 연결이 동작하는지 확인하고, P1·P4는 답변이 어떤 값을 근거로 만들어졌는지 직접 볼 수 있다. 관리자 런 상세 화면을 열지 않아도 된다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 도구 입력·결과는 WS로 전송되고 DB에도 저장되지만 화면에 표시되지 않는다. 사용자는 도구가 값을 실제로 가져왔는지 알 수 없다. |
| **WHO** | P2 KB 운영자·에이전트 소유자(주), P1 여신 심사역·P4 일반 사용자(보조). |
| **RISK** | 도구 결과에 포함된 개인정보·민감정보 노출, 타인 세션 열람, 2026-05에 raw JSON 노출을 제거한 결정(agent-chat-reasoning-display FR-04)과 같은 가독성 문제 재발, 실시간과 재진입 표시 불일치. |
| **SUCCESS** | 실시간과 재진입의 내역 순서·항목 일치, MCP 포함 실런 표시, 타인 세션 0건 노출, 답변 흐름 비차단, 기존 경로 회귀 0건. |
| **SCOPE** | M1 표시 정책(백엔드 도메인) → M2 세션 도구 내역 API → M3 실시간 경로 정리 → M4 프론트 접이식 내역·드릴다운 |

---

## 1. Overview

### 1.1 Purpose

채팅에서 에이전트가 도구(내부 도구, MCP)를 호출해 답할 때, 어떤 도구를 어떤 순서로 호출했고 각 도구가 어떤 값을 돌려줬는지를 답변 자리에서 확인할 수 있게 한다.

### 1.2 Background

코드 대조 결과는 다음과 같다.

| 구간 | 현재 상태 | 근거 |
|------|----------|------|
| 실시간 도구 이벤트 | `input_preview`·`output_preview`(1KB, `_truncate_json`)를 이미 송신 | `idt/src/application/agent_builder/run_agent_use_case.py:1431-1463` |
| 프론트 스트림 상태 | 이벤트의 preview를 버리고 이름·소요 시간만 보관 | `idt_front/src/hooks/useAgentRunStream.ts:124-141` |
| 변환 함수 | preview 필드 없음 | `idt_front/src/hooks/agentStepToToolEvent.ts:15-28` |
| 화면 | 하단 고정 패널 1개, 이름·ms만 표시, 답변별 보존·재진입 복원 없음 | `idt_front/src/components/chat/ToolPreviewPanel.tsx`, `idt_front/src/pages/ChatPage/index.tsx:526-534` |
| 저장 | `ai_tool_call.arguments_json`(1KB), `result_summary`(1KB), `status`, `error_text`, `latency_ms`, `step_id` | `idt/src/domain/agent_run/entities.py:74-90`, `idt/src/infrastructure/llm/usage_callback.py:38-40` |
| 추론 저장 | supervisor 판단 요약이 `ai_run_step.output_summary`에 저장됨 | `idt/src/application/agent_run/step_tracking.py:39,295` |
| 기존 조회 API | `GET /agents/runs/{run_id}`는 소유자·관리자에게 런 상세 트리를 준다. 세션 단위 일괄 조회는 없다 | `idt/src/api/routes/agent_run_router.py:160` |
| 근거 칩 | MCP 결과는 칩으로 표시되지만 승인 필요·`category=action`·실패·카탈로그 미등록 호출은 제외 | `idt/src/domain/agent_run/source_policy.py:240-256` |

두 가지를 먼저 밝힌다.

1. **이전 결정의 부분 번복.** `agent-chat-reasoning-display`(2026-05) FR-04는 raw JSON이 읽기 어렵다는 이유로 preview를 화면에서 뺐다. 이번에는 raw 문자열을 그대로 두지 않고 정리된 형태를 기본으로 보여 주며, 원문은 토글 뒤에 둔다. 하단 실시간 패널의 동작은 바꾸지 않는다.
2. **"MCP는 표시되지 않는다"는 부분적으로만 맞다.** 조회형 MCP는 근거 칩(PR #86)으로 이미 표시된다. 다만 도구 호출 순서, 입력, 승인·action·실패 호출은 어디에도 보이지 않는다. 이 기능은 근거 칩을 대체하지 않고, 칩이 다루지 않는 "실행 과정"을 맡는다.

`conventions/data-exists-exposure-missing.md`에 해당하는 사례다. 새 수집·저장 없이 노출 경로만 추가한다.

### 1.3 Related Documents

- 시나리오: `docs/USER-SCENARIOS.md` P2, P1, S2
- 선행 사이클: `docs/archive/2026-05/agent-chat-reasoning-display/`, `docs/01-plan/features/agent-run-source-citations.plan.md`(PR #86)
- 위키: `conventions/data-exists-exposure-missing.md`, `conventions/additive-contract-extension.md`, `conventions/false-green-quality-gates.md`, `backend/patterns/mcp-runtime-tool-shape.md`, `backend/patterns/run-step-hierarchy-and-latency.md`, `backend/db/erd-agent-run.md`, `frontend/chat/streaming-message-action-id.md`, `frontend/screens/chat-screens.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] 실행 기록을 표시용 "도구 실행 내역"으로 변환하는 단일 정책 (M1)
- [ ] 세션 단위 도구 내역 조회 API, 인증 필수, 요청 사용자 세션만 (M2)
- [ ] 실시간 WS 이벤트를 같은 표시 형태로 맞추는 additive 필드 (M3)
- [ ] 답변별 접이식 "도구 실행 내역"과 호출별 입력·결과 드릴다운 (M4)
- [ ] 추론과 도구 호출의 시간 순서 혼합 표시, 서브에이전트 워커 라벨 (M1, M4)
- [ ] 정리된 표시(키: 값, 정리된 JSON, 텍스트) + 원문 보기 토글 + 잘림 표시 (M4)
- [ ] 세션 재진입 시 내역 복원 (M2, M4)

### 2.2 Out of Scope

- 저장 한도(1KB) 상향, 새 테이블·컬럼·마이그레이션
- 하단 "추론 진행" 패널 동작 변경 (실시간 표시로 유지)
- 워커별 트리 표시 (관리자 런 상세의 `buildStepTree`는 그대로 둔다)
- 근거 칩(`sources`) 계약·필터 규칙 변경
- 일반 채팅(`/ws/chat`) 경로의 답변별 내역 (실시간 패널만 유지)
- 웹훅·백그라운드·스케줄 응답 payload 변경
- 도구 결과에 대한 PII 마스킹 구현 (`pii-masking-integration` 범위, §5 R1 참조)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 도구 실행 내역은 정책 1곳에서 조립하고, 실시간 경로와 재진입 경로가 같은 항목 형태(종류, 이름, 상태, 소요 시간, 입력, 결과, 잘림 여부, 워커 라벨)를 쓴다. | High | Pending |
| FR-02 | 항목은 추론(supervisor `output_summary`)과 도구 호출을 시간 순서로 섞는다. 정렬 키는 생성 시각과 id다. | High | Pending |
| FR-03 | 도구 이름은 사람이 읽을 이름으로 표시한다. MCP는 카탈로그 `name`을 쓰고 UUID 합성명(`mcp_{uuid}...`)을 노출하지 않는다. 카탈로그에 없으면 "MCP 도구"로 폴백한다. 내부 도구는 카탈로그 이름, 없으면 런타임 이름을 쓴다. | High | Pending |
| FR-04 | 승인 필요 도구, `category=action` 도구, 실패 호출도 목록에 포함한다. 실패는 상태와 짧은 오류 문구만 보이고 스택·내부 경로는 내보내지 않는다. `status=SUCCESS`이지만 본문이 `Error executing tool`로 시작하는 MCP 호출은 실패로 표시한다. | High | Pending |
| FR-05 | 결과는 `result_summary`의 `{"content": ...}` 래퍼를 벗긴 뒤 표시한다. 기존 `unwrap_tool_summary`를 재사용한다. | High | Pending |
| FR-06 | 저장 한도로 잘린 입력·결과는 `truncated` 표시를 단다. | Medium | Pending |
| FR-07 | 서브에이전트 안에서 호출된 도구에는 소속 워커 라벨을 붙인다. 부모 step을 찾지 못하면 라벨 없이 표시한다. | Medium | Pending |
| FR-08 | `GET /conversations/agents/{agent_id}/sessions/{session_id}/tool-traces`로 assistant 메시지별 내역을 반환한다. 토큰의 사용자 세션만 조회하고, 없는 세션·타인 세션은 존재 여부를 숨기려 빈 200을 준다(세션 근거 API와 같은 규칙). 세션 단위 일괄 조회만 허용하고 메시지별 반복 조회를 금지한다. | High | Pending |
| FR-09 | 메시지↔런 연결은 세션 근거 API와 같은 규칙을 쓴다. user 메시지 1건에 런이 여러 개면 마지막 런을 쓴다. | Medium | Pending |
| FR-10 | 내역 조회·조립이 실패해도 히스토리와 답변은 정상 반환하고 내역만 생략한다. 스택 트레이스를 포함한 warning을 남긴다. | High | Pending |
| FR-11 | 실시간 경로: `agent_tool_started`·`agent_tool_completed`에 표시용 이름과 정리용 필드를 additive로 추가하거나, 답변 완료 시 같은 정책 결과를 싣는다. 방식은 Design에서 정한다. 기존 `input_preview`·`output_preview`는 유지한다. | High | Pending |
| FR-12 | 프론트: 답변 아래(근거 칩 다음)에 "도구 실행 내역 (N)"을 기본 접힘으로 표시한다. N은 도구 호출 수이며 추론은 세지 않는다. 내역이 없으면 영역을 표시하지 않는다. | High | Pending |
| FR-13 | 각 도구 항목을 펼치면 입력은 키: 값 목록, 결과는 JSON이면 들여쓴 JSON, 아니면 줄바꿈을 보존한 텍스트로 보인다. "원문 보기" 토글로 저장된 문자열을 그대로 보인다. 모든 값은 일반 텍스트로만 렌더링한다(HTML·마크다운 해석 금지). | High | Pending |
| FR-14 | 상태는 아이콘과 텍스트를 함께 쓴다(성공/실패/승인 대기). 색만으로 구분하지 않는다. | Medium | Pending |
| FR-15 | 하단 "추론 진행" 패널은 현재 동작을 유지한다. 답변이 완료되면 해당 답변 아래 내역이 표시된다. | Medium | Pending |
| FR-16 | 재진입 시 히스토리 메시지와 내역을 메시지 id로 병합한다. id가 없는 메시지는 내역을 표시하지 않는다(`streaming-message-action-id` 규칙). | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 성능 | 세션 내역 API는 세션당 쿼리 수가 메시지 수에 비례하지 않는다 | 쿼리 횟수 단언 테스트 |
| 보안 | 타인 세션 요청 시 내역 0건 | 라우터 TestClient 테스트 |
| 보안 | 입력·결과 렌더링에 `dangerouslySetInnerHTML`·마크다운 렌더러를 쓰지 않는다 | 컴포넌트 테스트 + 소스 검사 |
| 호환성 | WS·REST 계약은 additive만. 기존 소비자 무변경 | 기존 테스트 회귀 0건(FAILED 목록 diff) |
| 접근성 | 접기/펼치기는 `button` + `aria-expanded`, 키보드로 조작 가능 | 컴포넌트 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-16 구현
- [ ] 정책 단위 테스트: 정렬, 이름 폴백, MCP 오류 본문 판정, 래퍼 제거, 잘림, 워커 라벨
- [ ] 실시간 표시와 재진입 표시가 같은 런에서 같은 항목·순서를 낸다 (같은 픽스처로 두 경로 비교 테스트)
- [ ] 실 LLM·실 MCP 서버(예: 네이버 검색 MCP) 1회 실런에서 입력·결과 표시 확인
- [ ] 세션을 다시 열어 같은 내역이 보이는지 화면 확인
- [ ] 백엔드 pytest·프론트 vitest 회귀 0건 (master 상시 실패 목록과 FAILED diff 비교)

### 4.2 Quality Criteria

- [ ] 신규 정책·서비스 커버리지 80% 이상, 신규 컴포넌트 60% 이상
- [ ] `npm run lint`, `tsc -b` 통과
- [ ] 라우터는 `app.routes` 순회가 아닌 TestClient 실요청으로 검증

---

## 5. Risks and Mitigation

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| R1 | 도구 결과에 개인정보가 포함되어 화면에 그대로 나온다 | High | Medium | 요청 사용자 본인 세션으로만 제한(FR-08). 사용자는 이미 같은 결과를 바탕으로 한 답변을 받고 있다. PII 마스킹이 도구 결과 저장 경로에 적용되면 자동으로 따라가도록 저장값만 읽는다(별도 원본 경로 금지). `pii-masking-integration` Check 시 이 경로를 대상에 포함한다. |
| R2 | 공유·구독 에이전트에서 소유자가 아닌 사용자가 도구 입력(시스템이 만든 인자)을 본다 | Medium | Medium | 입력은 LLM이 사용자 질문으로 만든 인자다. 비밀값은 도구 설정(`tool_config`)·MCP 헤더에 있고 `arguments_json`에는 없다. Design에서 실데이터 표본으로 확인한다. |
| R3 | raw JSON 가독성 문제 재발(2026-05 결정과 충돌) | Medium | Medium | 기본 접힘 + 정리된 표시 + 원문은 토글 뒤(FR-12, FR-13). 하단 패널은 그대로 둔다. |
| R4 | 실시간(WS preview)과 재진입(DB) 값이 달라 표시가 어긋난다 | Medium | High | 두 원천의 직렬화가 다르다(`_truncate_json` vs `UsageCallback` 요약). Design에서 단일 원천 방식(답변 완료 시 정책 결과 전달 등)을 비교해 정한다. 비교 테스트로 고정한다(DoD). |
| R5 | 1KB 잘림으로 결과가 중간에 끊겨 "가져오지 못한 것"처럼 보인다 | Low | High | `truncated` 표시와 "저장 한도로 일부만 표시" 안내(FR-06). 한도 상향은 범위 밖. |
| R6 | 긴 실행(도구 수십 건)에서 답변 아래가 길어진다 | Low | Medium | 기본 접힘, 항목별 펼침. 상한은 Design에서 config로 정한다. |
| R7 | supervisor `output_summary`가 추론이 아닌 다른 요약을 담는 step이 있다 | Low | Medium | supervisor 노드의 step만 추론으로 취급한다. Design에서 실데이터로 확인한다. |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `idt/src/domain/agent_run/` | 도메인 정책 | 도구 실행 내역 조립 정책 신규 |
| `idt/src/application/agent_run/` | 서비스·유스케이스 | 세션 내역 조회 유스케이스 신규 |
| `idt/src/api/routes/agent_run_router.py` | REST | `.../sessions/{session_id}/tool-traces` 추가 |
| `idt/src/interfaces/schemas/agent_run_response.py` | 스키마 | 응답 타입 신규(기존 타입 무변경) |
| `idt/src/application/agent_builder/run_agent_use_case.py` | WS 이벤트 | additive 필드 (Design에서 결정) |
| `idt_front/src/types/` | 타입 | 내역 항목 타입, WS 이벤트 optional 필드 |
| `idt_front/src/services/`, `src/hooks/`, `src/constants/api.ts` | API 연동 | 세션 내역 조회 서비스·훅 |
| `idt_front/src/hooks/useAgentRunStream.ts` | 스트림 상태 | 항목별 입력·결과 보관 |
| `idt_front/src/components/chat/` | UI | 접이식 내역·드릴다운 컴포넌트 신규, 메시지 렌더에 배치 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `agent_tool_started/completed` | WS 수신 | `useAgentRunStream.ts`, `AgentRunProgress.tsx` | additive만 — 무영향 |
| `input_preview`/`output_preview` | WS 수신 | `useChatStream.ts`(일반 채팅) | 무변경 |
| `ToolPreviewPanel` | 렌더 | `ChatPage/index.tsx:526` | 무변경 |
| `ai_tool_call`, `ai_run_step` | READ | 관리자 런 상세, 근거 칩, 👎 드릴다운 | 읽기 추가만 |
| `unwrap_tool_summary` | 호출 | `source_policy.py` | 재사용, 시그니처 무변경 |

### 6.3 Verification

- [ ] 위 소비자 테스트 회귀 0건
- [ ] 관리자 런 상세·근거 칩·👎 드릴다운 화면 동작 불변

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (기존 레이어드 구조 유지) | ✅ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 데이터 원천 | 새 수집 / 기존 `ai_tool_call`·`ai_run_step` | 기존 기록 | 마이그레이션 0, 근거 칩과 같은 원천 |
| 배치 | 하단 패널 확장 / 답변별 접이식 | 답변별 접이식 | 답변마다 보존, 재진입 복원 가능 (사용자 선택) |
| 표시 형식 | raw / 정리+원문 토글 / 한도 상향 | 정리+원문 토글 | 2026-05 가독성 문제 회피 (사용자 선택) |
| 노출 범위 | 본인·전체 도구 / 본인·조회형만 / 소유자·관리자 | 본인 세션·전체 도구 | 실패·승인 호출까지 보여야 "가져왔는지" 판단 가능 (사용자 선택) |
| 서브에이전트 | 평면+라벨 / 트리 | 평면+워커 라벨 | 좁은 채팅 폭 (사용자 선택) |
| 실시간 원천 일치 방식 | WS 필드 확장 / 완료 시 정책 결과 전달 / 완료 후 API 재조회 | Design에서 결정 | R4 |

### 7.3 Clean Architecture Approach

```
domain/agent_run/tool_trace_policy.py   순수 정책 (DB·LangChain 무의존)
application/agent_run/                   기록 조회 → 정책 → DTO, 실패 흡수
api/routes/agent_run_router.py           인증 + 세션 소유 확인
idt_front: types → services → hooks → components/chat
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md`, `idt_front/CLAUDE.md`
- [x] 계약 확장 additive (`conventions/additive-contract-extension.md`)
- [x] 컴포넌트 파일 런타임 상수 export 금지 (`frontend/patterns/tsx-authoring-pitfalls.md`)
- [x] 회귀는 FAILED 목록 diff로 증명 (`conventions/false-green-quality-gates.md`)

### 8.2 Conventions to Define/Verify

| Category | Rule |
|----------|------|
| wire 값 | 항목 `kind`(`reasoning`/`tool`), `status` 값은 StrEnum value로 고정 — 변경은 프론트 계약 변경 |
| 네이밍 | 백엔드 `ToolTrace*`, 프론트 `ToolTrace*` 로 통일 |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope |
|----------|---------|-------|
| 없음 | 상한(항목 수)은 기존 config 클래스에 키 추가 여부를 Design에서 정한다 (소비 지점 명기) | Server |

---

## 9. Next Steps

1. [ ] `/pdca design agent-run-tool-trace` — 실시간 원천 일치 방식(R4) 결정, 실데이터 표본으로 R2·R7 확인
2. [ ] 구현 (M1 → M2 → M3 → M4)
3. [ ] Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-03 | 초안 — 사용자 결정 7건 반영(배치·형식·노출·복원·추론·하단 패널·서브에이전트) | 배상규 |
