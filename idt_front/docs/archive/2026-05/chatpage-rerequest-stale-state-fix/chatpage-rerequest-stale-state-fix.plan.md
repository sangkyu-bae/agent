# chatpage-rerequest-stale-state-fix Plan

> ChatPage에서 첫 질문 이후 재질문 시 서버 호출 없이 이전 답변이 그대로 표시되는 버그 수정

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | ChatPage 재질문 시 stale stream state 로 인한 동일 응답 버그 수정 |
| 작성일 | 2026-05-27 |
| 예상 소요 | 45분 ~ 1시간 (양쪽 hook 수정 + 테스트 보강) |
| 영향 범위 | `src/hooks/useChatStream.ts`, `src/hooks/useAgentRunStream.ts`, `src/pages/ChatPage/index.tsx` + 관련 테스트 |

### Value Delivered

| 관점 | 설명 |
|------|------|
| Problem | 같은 세션에서 두 번째 질문부터 WebSocket이 다시 열리기 전에 이전 응답이 "완료" 상태로 잘못 적용되어 서버로 메시지가 전송되지 않고 직전 답변이 placeholder에 그대로 복사됨 |
| Solution | activeStream에 고유 `streamId`를 부여하고 useChatStream / useAgentRunStream 가 동기적으로 상태를 리셋하도록 변경. ChatPage의 완료 effect는 `view.streamId === activeStream.streamId` 일 때만 placeholder를 갱신 |
| Function UX Effect | 채팅 세션 내에서 N번째 질문도 매번 서버로 정상 전송되어 새 답변이 스트리밍됨. RAG / 일반 / 에이전트 모드 모두 회복 |
| Core Value | 채팅 핵심 기능 신뢰성 회복 — 단일 세션 다중 질의가 정상 동작해야 사용 가치가 성립 |

---

## 1. 배경 및 재현

### 증상
- `/chatpage` 진입 후 첫 질문은 정상적으로 답변이 스트리밍됨
- **같은 세션에서 두 번째, 세 번째 질문**을 보내면 즉시 첫 번째 질문의 답변이 그대로 표시됨
- 네트워크 탭에서 두 번째 이후 질문에 대한 WebSocket subscribe 메시지가 관찰되지 않음 → "서버로 요청이 가지 않는 것 같다"는 사용자 보고와 일치

### AS-IS (문제)
- `useChatStream` / `useAgentRunStream` 의 내부 state(`tokens`, `answer`, `isDone`)가 한 번 `isDone=true`가 되면 다음 stream 시작 시점까지 그대로 남아 있음
- `ChatPage`의 view normalizer는 hook이 반환하는 현재 state 를 그대로 매핑하므로, 재질문 직후 첫 렌더에서 `view.isDone=true`, `view.answer="A1"` 가 즉시 평가됨
- 완료 effect가 즉시 fire → 새 placeholder(p2)에 이전 답변(A1)을 덮어쓰고 `setActiveStream(null)` 호출 → 새 WS 연결은 enabled→false 로 즉시 cleanup 됨

### TO-BE (목표)
- 매 send 마다 새로 발행되는 `streamId` 가 hook 입력으로 전달됨
- hook은 streamId 변경 시 **렌더 단계에서 동기적으로** state 를 초기화 (`useLayoutEffect` or derived-state 패턴)
- ChatPage 완료 effect는 hook이 보고하는 `currentStreamId` 가 activeStream의 streamId 와 일치할 때만 동작
- 결과적으로 두 번째 이후 질문도 stream 재구독 → 새 답변 정상 수신

---

## 2. 원인 분석 (Root Cause)

### 2-1. 핵심 흐름 다이어그램

```
[Q1 send]
  setActiveStream({kind:'chat', sessionId:'A', message:'Q1', placeholderId:'p1'})
    → useChatStream({sessionId:'A', message:'Q1', enabled:true})
      → effect: setState(INITIAL), connect WS, send subscribe(Q1)
      → tokens streaming...
      → chat_done → state.isDone=true, state.answer='A1'

[ChatPage 완료 effect (line 176)]
  view.isDone=true → updateMessage(p1, 'A1') → setActiveStream(null)
    → useChatStream({sessionId:'', enabled:false})
      → cleanup: disconnect
      → effect 본체: !enabled 조기 return  ← state 리셋 안 됨!
  ※ 이 시점에 chatStream.{tokens, answer, isDone} 은 Q1의 값 그대로

[Q2 send] (같은 세션)
  setActiveStream({kind:'chat', sessionId:'A', message:'Q2', placeholderId:'p2'})
    → 리렌더 시점:
       useChatStream 호출 → 내부 state는 아직 Q1 값
       view = {tokens, answer:'A1', isDone:true, ...} ← STALE!
    → ChatPage 완료 effect 즉시 발화:
       updateMessage(p2, 'A1')  ← 새 placeholder에 옛 답변 복사
       setActiveStream(null)    ← Q2 진입을 스스로 종료
    → useChatStream effect 본체가 그제서야 실행되어도
       enabled가 false로 되돌아갔으므로 connect 안 됨
       (혹은 connect 후 onOpen 도달 전에 cleanup 으로 close)
```

### 2-2. 코드 레퍼런스

**`src/hooks/useChatStream.ts:152-161`** — 상태 초기화가 effect 안에서 비동기로 일어남
```ts
useEffect(() => {
  if (!enabled || !accessToken || !sessionId) return;
  setState(INITIAL_STATE);             // ← 다음 commit 이후에 반영
  const url = wsUrl(WS_ENDPOINTS.WS_CHAT(sessionId), { token: accessToken });
  connect(url);
  return () => { disconnect(); };
}, [enabled, accessToken, sessionId]);  // ← message / streamId 미포함
```

**`src/hooks/useAgentRunStream.ts:147-158`** — 동일 패턴, 동일 결함

**`src/pages/ChatPage/index.tsx:117-140`** — view를 그대로 매핑
```ts
const view = useMemo(() => {
  if (activeStream?.kind === 'chat') {
    return { tokens: chatStream.tokens, answer: chatStream.answer,
             isDone: chatStream.isDone, ... };
  }
  ...
}, [activeStream, chatStream, agentRun]);
```

**`src/pages/ChatPage/index.tsx:176-200`** — stale isDone/answer 에 그대로 반응
```ts
useEffect(() => {
  if (!activeStream || !view) return;
  if (!view.isDone) return;            // ← 직전 stream 의 true가 그대로 평가됨
  ...
  updateMessage(activeStream.sessionId, activeStream.placeholderId, {
    content: view.answer, ... });
  setActiveStream(null);
}, [view?.isDone, view?.answer, ...]);
```

### 2-3. 영향 범위

| 모드 | 영향 |
|------|------|
| 일반 chat (`/ws/chat/{session_id}`) | 두 번째 질문부터 답변 동일, WS subscribe 미전송 |
| Agent run (`/ws/agent/{run_id}`) | runId가 매번 바뀌므로 sessionId 기준 deps 는 통과하나, `setState(INITIAL_STATE)`가 commit 이후라 같은 race 가능 (특히 빠른 재질문 시) |
| RAG 토글 / topK 변경 | message 만 바뀌는 케이스에서 deps 가 안 잡혀 더 심각 |

---

## 3. 수정 계획

### 3-1. activeStream 에 streamId 부여 (ChatPage)

매 `handleSend` 호출마다 새 `streamId` (예: `crypto.randomUUID()`) 를 만들어 activeStream 에 포함한다. `placeholderId` 를 재사용해도 동일 효과 — 새 필드 도입 vs 재사용은 가독성 기준으로 결정.

```ts
type ActiveStream =
  | { kind: 'chat'; streamId: string; sessionId: string; message: string;
      topK?: number; placeholderId: string; }
  | { kind: 'agent'; streamId: string; runId: string; agentId: string;
      sessionId: string; message: string; placeholderId: string; };
```

### 3-2. useChatStream / useAgentRunStream — streamId 기반 동기 리셋

두 가지 옵션 중 택1:

**옵션 A (권장): derived-state 패턴 + ref**
- 렌더 도중 `streamId` 변화를 감지하면 setState 호출 없이 다음 render 의 반환값을 강제로 INITIAL 로 만든다.
- 또는 `useState` 의 lazy initializer 와 `useRef` 조합으로 "currentStreamId 가 바뀌면 state 도 즉시 INITIAL" 을 표현.

```ts
const [state, setState] = useState<ChatStreamState>(INITIAL_STATE);
const prevStreamIdRef = useRef('');

// 렌더 단계에서 동기 리셋
if (enabled && streamId && streamId !== prevStreamIdRef.current) {
  prevStreamIdRef.current = streamId;
  setState(INITIAL_STATE);   // 같은 render 내 두번째 setState는 React 가 즉시 반영
}
```

> React 공식 패턴(Adjusting state while rendering): 같은 컴포넌트의 setState 를 render 중 호출하면 즉시 re-render 되고 본래 effect 는 새 state 로 실행됨. → ChatPage 의 view 도 새 INITIAL 값을 보게 되어 완료 effect 가 fire 되지 않음.

**옵션 B: streamId 를 반환하고 ChatPage 에서 매칭**
- `useChatStream` 이 `currentStreamId` 를 반환
- ChatPage 완료 effect 에 `view.streamId === activeStream.streamId` 가드 추가
- 상태 자체는 비동기 리셋이어도 잘못된 commit 을 막음

→ **A + B 동시 적용** 권장. A로 stale 자체를 차단하고, B로 안전망을 한 겹 더 둔다.

### 3-3. ChatPage 완료 effect 가드

```ts
useEffect(() => {
  if (!activeStream || !view) return;
  if (!view.isDone) return;
  if (view.streamId !== activeStream.streamId) return;  // ← 신규 가드
  ...
}, [view?.isDone, view?.answer, view?.error, view?.sources, view?.streamId, activeStream, ...]);
```

### 3-4. 변경 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `src/pages/ChatPage/index.tsx` | `ActiveStream` 타입에 `streamId` 추가, `handleSend`에서 발급, view에 streamId 포함, 완료 effect 가드 추가 |
| `src/hooks/useChatStream.ts` | `streamId` 입력 받기, 렌더 단계 동기 리셋, 반환 state 에 `streamId` 포함 |
| `src/hooks/useAgentRunStream.ts` | 동일 패턴 적용 |
| `src/types/chat.ts` 또는 hook 모듈 | 필요 시 export 타입 정리 |

### 3-5. TDD 사이클

1. **Red** — `src/hooks/useChatStream.test.ts` 에 케이스 추가
   - "동일 sessionId 로 streamId 만 바꿔 호출하면 state 가 INITIAL 부터 재시작한다"
   - "이전 stream 의 isDone/answer 가 새 streamId 첫 렌더에 노출되지 않는다"
2. **Red** — `src/pages/ChatPage/streamRouting.test.tsx` 에 시나리오 추가
   - "Q1 응답 완료 후 Q2 전송 시 새 WS subscribe 가 호출된다 (MSW WS mock 으로 검증)"
   - "Q2 placeholder 가 Q1 의 answer 로 덮어써지지 않는다"
3. **Green** — 위 수정 적용
4. **Refactor** — 두 hook 간 공통 패턴을 `useStreamLifecycle` 같은 작은 유틸로 빼낼지 검토 (현 PR 범위 내 / 다음 PR 분리는 판단 후)

---

## 4. 검증 계획

### 4-1. 자동화 테스트
- `npm run test:run` — 신규 케이스 포함 그린
- `npm run type-check` — 타입 추가에 따른 회귀 없음

### 4-2. 수동 QA 체크리스트
- [ ] 일반 채팅(SUPER agent) — 같은 세션에서 3회 연속 다른 질문 → 모두 새 답변 수신
- [ ] RAG 토글 ON/OFF 전환 후 재질문 — topK 변경이 정상 반영되는지
- [ ] 사용자 정의 Agent(UUID) — 같은 세션에서 재질문 시 WS `/ws/agent/{run_id}` 새 연결 확인
- [ ] 첫 질문 도중 두 번째 질문 입력 → `isPending` 으로 차단되는지 (기존 mutex 동작 보존)
- [ ] 세션 전환 후 새 세션 첫 질문 → 정상
- [ ] DevTools Network → WS frame 에서 매 send 마다 `subscribe` 프레임 관찰

### 4-3. 회귀 위험
- **mutex 동작**: `isPending = activeStream !== null && !view.isDone` 의 의미 변화 없음
- **이어보기(replay) UX**: `isReplayed` 플래그도 INITIAL 로 리셋되므로, 새 stream 의 첫 cached marker 만 반영됨 → 정상

---

## 5. 일정 및 의존성

| 단계 | 산출물 | 예상 소요 |
|------|--------|----------|
| Design 문서 작성 | `docs/02-design/features/chatpage-rerequest-stale-state-fix.design.md` | 15분 |
| 테스트 추가 (Red) | 위 4-1 케이스 | 15분 |
| 구현 (Green) | hook + ChatPage 수정 | 20분 |
| QA + Refactor | 4-2 체크리스트 | 15분 |
| Gap analysis & Report | `docs/03-analysis`, `docs/04-report` | 10분 |

**선행 의존성**: 없음. 단독 PR 로 배포 가능.

---

## 6. 대안 검토

| 대안 | 장점 | 단점 | 채택 |
|------|------|------|------|
| **A. streamId + 동기 리셋 (본안)** | hook 재사용성 보존, 최소 변경, 회귀 위험 낮음 | hook 시그니처에 streamId 추가 | ✅ |
| B. `key` 로 ChatPage 내부 stream 영역 remount | React 패턴 명확 | hook 들을 sub-component 로 분리해야 함 → 구조 변경 큼 | ❌ |
| C. handleSend 에서 reset() 노출하고 setActiveStream 전에 호출 | 명시적 | hook 외부에서 reset 호출 순서 의존성 발생, 잊기 쉬움 | ❌ |
| D. `view` 메모를 `activeStream` 변경 시점에 강제 무효화 | ChatPage 만 수정 | 근본 원인(hook state 잔존) 미해결, 다른 호출처에서 재발 | ❌ |

---

## 7. 참고

- 백엔드 라우터: `idt/src/api/routes/ws_router.py` (변경 없음)
- 관련 Design: `agent-session-switching` (현재 do 단계) — 본 수정은 그와 독립
- React 공식 가이드: "You Might Not Need an Effect — Adjusting state while rendering"
