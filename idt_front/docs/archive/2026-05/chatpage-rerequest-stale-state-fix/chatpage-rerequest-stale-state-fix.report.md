---
template: report
version: 1.0
feature: chatpage-rerequest-stale-state-fix
date: 2026-05-27
author: 배상규
project: idt_front
project_version: 0.0.0
status: Completed
match_rate: 97
iteration_count: 0
---

# chatpage-rerequest-stale-state-fix 완료 보고서

> **Summary**: ChatPage 에서 같은 세션 내 두 번째 이후 질문이 서버로 전송되지 않고 직전 답변이 그대로 표시되던 버그를 수정. `useChatStream` / `useAgentRunStream` 의 stale state 가 view 를 통해 ChatPage 의 완료 effect 를 즉시 발화시키던 race condition 을, **streamId 기반 render-time 동기 리셋 + view.streamId 일치 가드** 로 해결.
>
> **Project**: idt_front (React 19 + TypeScript + Vitest)
> **Completion date**: 2026-05-27
> **Author**: 배상규
> **Final Match Rate**: **97%** (목표 90%)
> **Iteration**: 0회 (1차 구현으로 threshold 통과)

---

## Executive Summary

### 1.1 기능 목표

사용자가 ChatPage 진입 후 같은 세션에서 **N번째 질문(N≥2)을 보낼 때마다 WebSocket 으로 새로운 subscribe 가 전송되어 새 답변이 스트리밍** 되어야 한다. AS-IS 에서는 두 번째 질문부터 서버 호출 없이 직전 답변이 그대로 placeholder 에 복사되어 채팅 기능의 핵심 가치가 손상되어 있었다.

### 1.2 최종 상태

| 항목 | 상태 |
|------|------|
| **기능 요구사항** | ✅ 19/19 핵심 항목 (1건은 의도된 trade-off) |
| **설계 준수** | ✅ 97% Match Rate |
| **자동 테스트** | ✅ 103/103 통과 (신규 7건 포함) |
| **타입 안전성** | ✅ tsc --noEmit 0 errors |
| **회귀 보호** | ✅ Q1 mutex / 라우팅 / replay 동작 유지 |
| **수동 QA** | ⏳ dev server 검증은 사용자 영역 |

### 1.3 Value Delivered

| 관점 | 설명 | 측정값 |
|------|------|--------|
| **Problem** | 같은 세션 내 N번째 질문이 stale `isDone/answer` 때문에 즉시 "완료" 처리되어 WS 재구독 없이 직전 답변이 그대로 표시됨. 사용자가 "서버 요청이 안 가는 것 같다"고 보고한 실제 증상 | 신뢰성 0% (재질문 시) |
| **Solution** | activeStream 마다 UUID `streamId` 발급, 두 hook 이 render body 에서 `streamId` 변화 감지 시 INITIAL 동기 리셋, ChatPage 두 effect 가 `view.streamId === activeStream.streamId` 일 때만 fire | 3 production + 3 test 파일 |
| **Function UX Effect** | 같은 세션에서 N번째 질문도 매번 새 WS subscribe 가 전송되어 새 답변 스트리밍. 일반/RAG/Agent 3개 모드 모두 회복 | 자동 검증 7 케이스 추가, 103/103 통과 |
| **Core Value** | 채팅 핵심 기능 신뢰성 회복 — 단일 세션 다중 질의가 정상 동작해야 사용 가치 성립. React 권장 패턴(Adjusting state while rendering) 채택으로 미래 확장에도 안전 | Match Rate 97% / iteration 0회 |

---

## 2. PDCA 사이클 개요

```
┌─────────────────────────────────────────────────────────────┐
│ [Plan] 2026-05-27                                           │
│ • 사용자 보고 증상 ↔ 코드 trace 로 race condition 식별       │
│ • 4가지 대안 비교 후 streamId 기반 안 채택                  │
│ • 영향 범위 3 production + 3 test 파일 산정                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ [Design] 2026-05-27                                         │
│ • ActiveStream / hook options / view 에 streamId 도입       │
│ • Render-time 동기 리셋 (React 공식 권장 패턴)               │
│ • ChatPage 두 effect 에 streamId 일치 가드                  │
│ • isPending 보강으로 mutex 안전망 한 겹 추가                │
│ • 회귀 위험 4가지 + 완화 방안 명시                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ [Do] 2026-05-27                                             │
│ TDD Red → Green                                             │
│ • useChatStream.ts: streamId I/O + render reset             │
│ • useAgentRunStream.ts: 동일 패턴                            │
│ • ChatPage/index.tsx: ActiveStream/view/effect 가드          │
│ • 테스트 +7 (hook 5 + ChatPage 2)                            │
│ • npm run type-check ✓, vitest 103/103 ✓                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ [Check] 2026-05-27                                          │
│ Gap Analysis (Design vs 구현)                                │
│ • 19개 핵심 요구사항 중 18.5 일치 → Match Rate 97%          │
│ • Gap 1건 (streamId optional vs required): 의도된 trade-off │
│ • Gap 2건 (수동 QA 미실행): 사용자 검증 영역                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ [Act] 2026-05-27                                            │
│ iteration 0회 — 1차 구현으로 90% threshold 통과              │
│ Report 단계 진입                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 변경 사항 상세

### 3.1 production 코드 (3 파일)

| 파일 | 변경 라인 (대략) | 핵심 변경 |
|------|------------------|----------|
| `src/hooks/useChatStream.ts` | +12 / -3 | `streamId` prop/state 추가, `if (enabled && streamId && streamId !== state.streamId) setState(INITIAL)` 렌더 동기 리셋, connect effect deps 에 `streamId` 추가, `setState(INITIAL)` 호출은 effect 에서 제거 (render 단계에서 처리) |
| `src/hooks/useAgentRunStream.ts` | +12 / -3 | 동일 패턴 적용 |
| `src/pages/ChatPage/index.tsx` | +17 / -6 | `ActiveStream` 에 streamId 추가, `handleSend` 에서 `crypto.randomUUID()` 발급, `view` 에 streamId 매핑, 두 effect 에 `view.streamId === activeStream.streamId` 가드, `isPending` 보강 |

### 3.2 테스트 코드 (3 파일, +7 케이스)

| 파일 | 신규 케이스 |
|------|------------|
| `src/hooks/useChatStream.test.ts` | streamId 리셋 / idempotent / disabled 가드 (3) |
| `src/hooks/useAgentRunStream.test.ts` | streamId 리셋 / idempotent (2) |
| `src/pages/ChatPage/streamRouting.test.tsx` | 새 streamId 발급 / UUID 형식 검증 (2) |

### 3.3 핵심 패턴 — Adjusting State While Rendering

```ts
// useChatStream.ts:74-76 / useAgentRunStream.ts:67-69
if (enabled && streamId && streamId !== state.streamId) {
  setState({ ...INITIAL_STATE, streamId });
}
```

React 공식 가이드("You Might Not Need an Effect — Adjusting state while rendering") 패턴.
- 같은 컴포넌트에서 render body 의 `setState` 는 React 가 즉시 re-render 로 처리
- effect 안 setState 와 달리 **commit 이전에 state 가 갱신** 되어 같은 render 의 view 계산이 새 INITIAL 을 본다
- 이로써 ChatPage 완료 effect 가 stale `isDone:true` 를 읽고 잘못 fire 하는 race 가 원천 차단됨

---

## 4. 결과 측정

### 4.1 자동화 검증

```
$ npx vitest run --pool=threads src/hooks src/pages/ChatPage

 Test Files  12 passed (12)
      Tests  103 passed (103)
   Duration  58.46s

$ npm run type-check
> tsc --noEmit
(0 errors)
```

### 4.2 신규 테스트 케이스 명세

| 영역 | 케이스 | 검증 의도 |
|------|--------|----------|
| useChatStream | streamId 변경 시 같은 render 에서 state 가 INITIAL 로 리셋 | 핵심 race 차단 |
| useChatStream | 동일 streamId 재호출 시 state 보존 | 무한 루프 방지 (idempotent) |
| useChatStream | enabled=false / streamId="" 시 리셋 발생 안함 | 가드 정확성 |
| useAgentRunStream | streamId 변경 시 INITIAL 리셋 | 동일 적용 검증 |
| useAgentRunStream | 동일 streamId 시 보존 | idempotent |
| ChatPage routing | handleSend 마다 새 UUID streamId 발급 | 통합 검증 |
| ChatPage routing | streamId UUID 형식 (/^[0-9a-f-]{36}$/i) | 형식 보장 |

### 4.3 회귀 보호

기존 기능이 변경 없이 유지됨을 확인한 항목:
- `Q1 mutex` (두 hook 동시 enabled 인 적 없음) — 기존 테스트 통과
- SUPER / UUID / null agent 라우팅 — 기존 테스트 통과
- `chat_failed`, `agent_run_failed` 에러 표시 — INITIAL 에 포함
- `isReplayed` (cached marker) — 새 stream 마다 깨끗하게 시작

---

## 5. 잔여 항목 및 후속 작업

### 5.1 의도된 Trade-off

**`streamId` prop 이 optional 로 구현됨 (Design 은 required)**
- 이유: 기존 21개 message-handling 테스트가 streamId 없이 호출. required 강제 시 무관한 테스트들이 타입 에러로 깨짐
- 런타임 영향: ChatPage 는 항상 streamId 전달 → production 동작 영향 없음
- 후속: 별도 PR 에서 기존 테스트에 streamId 주입 후 required 로 승격 권장

### 5.2 사용자 검증 권장 항목 (Design §4.2)

- [ ] 일반 채팅(SUPER agent) — 같은 세션 3회 연속 다른 질문 → 매번 새 답변
- [ ] RAG 토글 ON/OFF 전환 후 재질문 → topK 변경 반영
- [ ] 사용자 정의 Agent — 같은 세션 재질문 시 WS `/ws/agent/{run_id}` 새 연결
- [ ] 첫 질문 도중 두 번째 입력 → mutex 차단 (기존 동작 보존)
- [ ] 세션 전환 후 새 세션 첫 질문 정상
- [ ] DevTools Network → WS frame 마다 `subscribe` 프레임 관찰

### 5.3 향후 개선 (선택)

- 두 hook 의 공통 패턴(`streamId` 기반 lifecycle) 을 `useStreamLifecycle` 유틸로 추출 — Design §6.5 의 refactor 후보
- `streamId` 가 placeholderId 와 1:1 매칭되므로 후자를 재사용해 prop 수를 줄이는 변형도 고려 가능

---

## 6. 산출물 경로

| 단계 | 문서 |
|------|------|
| Plan | `docs/01-plan/features/chatpage-rerequest-stale-state-fix.plan.md` |
| Design | `docs/02-design/features/chatpage-rerequest-stale-state-fix.design.md` |
| Analysis | `docs/03-analysis/features/chatpage-rerequest-stale-state-fix.analysis.md` |
| Report | `docs/04-report/features/chatpage-rerequest-stale-state-fix.report.md` (본 문서) |

---

## 7. 학습 포인트

1. **stale state race 의 본질**: hook 내부 state 가 `useEffect` 에 의해 비동기로만 리셋될 때, 부모 컴포넌트의 effect 가 같은 commit 사이클에 stale 값을 그대로 읽어 잘못된 행동을 한다. → render body 동기 리셋 패턴이 가장 단순한 해법.
2. **streamId 같은 lifecycle id 의 유효성**: deps 배열, view 정규화, effect 가드 등 여러 지점에서 "같은 stream 의 데이터인가"를 한 줄로 검사할 수 있어 정합성 검증 비용이 매우 낮아짐.
3. **TDD 사이클의 보호 효과**: 신규 케이스 3종(reset / idempotent / disabled)이 추후 무한 루프, 회귀, 가드 누락 같은 미묘한 버그를 즉시 감지할 안전망을 형성.
