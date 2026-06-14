# FIX-CHAT-REASONING-OBJECT-RENDER: /chatpage 스트리밍 추론 토큰이 `[object Object]`로 표시되는 버그 수정

> 상태: Plan
> 연관 Task: CHAT-RENDER-001
> 작성일: 2026-06-07
> 우선순위: High

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | `/chatpage`에서 WS 요청 후 추론(토큰) 스트림을 화면에 띄울 때 일부 텍스트가 `[object Object]`(또는 `object`)로 표시된다. 특정 LLM이 스트리밍 chunk의 `content`를 **문자열이 아니라 content block 리스트**로 내려줄 때 발생한다. |
| **Solution** | 백엔드 스트리밍 매핑 지점(`run_agent_use_case._map_chat_stream`, `general_chat/use_case._map_token`)에서 chunk content를 **항상 평탄화된 문자열로 정규화**하는 공용 헬퍼를 도입한다. 프론트엔드에는 방어적 string 가드를 추가한다. |
| **Function UX Effect** | Agent / General Chat 양쪽 경로에서 추론 토큰이 깨지지 않고 사람이 읽는 텍스트로 자연스럽게 흐른다. content block 기반 모델(reasoning/tool-call 동반)에서도 동일하게 동작. |
| **Core Value** | 사용자가 보는 핵심 출력(스트리밍 답변)의 **신뢰성** 회복. `[object Object]`는 "제품이 깨졌다"는 즉각적 인상을 주는 치명적 표시 결함이므로 우선 제거. |

---

## 1. 문제 정의 (Problem Statement)

`/chatpage`(`idt_front/src/pages/ChatPage/index.tsx`)에서 메시지 전송 → WS 구독 → 토큰 스트림 수신 → placeholder 메시지 content 누적 → 화면 렌더의 흐름에서, 스트리밍 중 일부 구간이 `[object Object]`로 표시된다.

재현 경로(둘 다 동일 증상):
- General Chat / SUPER agent: `WS /ws/chat/{session_id}` → `chat_token`
- 사용자 정의 Agent(supervisor): `WS /ws/agent/{run_id}` → `agent_token`

사용자 관점 증상: "추론 과정을 받아서 페이지에 띄울 때 글자 대신 `object`가 뜬다."

---

## 2. 근본 원인 분석 (Root Cause)

### 2-1. [Critical] 스트리밍 chunk content가 list일 때 그대로 전송됨

LangChain `on_chat_model_stream` 이벤트의 `chunk.content`는 모델/구성에 따라 **`str` 또는 content block 리스트**(`[{"type": "text", "text": "..."}, ...]`)로 내려온다. reasoning/tool-call content block을 쓰는 모델에서 list가 빈번하다.

**파일 A — Agent 경로**: `src/application/agent_builder/run_agent_use_case.py:650-664`

```python
def _map_chat_stream(self, raw, data, seq, run_id, state):
    chunk_obj = data.get("chunk")
    chunk_text = getattr(chunk_obj, "content", None)   # ← list일 수 있음
    if not chunk_text:
        return None
    ...
    return self._build_event(
        seq, AgentRunEventType.TOKEN, run_id,
        {"chunk": chunk_text, "node_name": node_name},  # ← list 그대로 payload에 실림
    )
```

**파일 B — General Chat 경로**: `src/application/general_chat/use_case.py:399-408`

```python
def _map_token(self, data, seq, session_id):
    chunk_obj = data.get("chunk")
    chunk_text = getattr(chunk_obj, "content", None)   # ← 동일 패턴
    if not chunk_text:
        return None
    return self._build_event(
        seq, ChatEventType.TOKEN, session_id, {"chunk": chunk_text},
    )
```

### 2-2. [Critical] 프론트엔드가 chunk를 문자열로 그대로 결합

payload의 `chunk`가 list여도 프론트는 문자열 결합을 수행한다.

- `idt_front/src/hooks/useChatStream.ts:93`
  ```ts
  case 'chat_token':
    setState((s) => ({ ...s, tokens: s.tokens + msg.data.chunk }));  // string + array → "[object Object]"
  ```
- `idt_front/src/hooks/useAgentRunStream.ts:128-129`
  ```ts
  case 'agent_token':
    setState((s) => ({ ...s, tokens: s.tokens + msg.data.chunk }));  // 동일
  ```

누적된 `tokens`가 `ChatPage`의 placeholder `content`로 들어가고(`index.tsx:193-197`), `MessageBubble`(`MessageBubble.tsx:41`)이 `{message.content}`를 그대로 렌더 → 화면에 `[object Object]` 노출.

### 2-3. 타입 계약은 이미 string

프론트 타입(`types/websocket.ts:57,116`)은 `chunk: string`으로 선언돼 있다. 즉 **백엔드가 계약을 위반(list 전송)** 하는 것이 1차 원인이고, 프론트는 방어가 없어 깨진 값을 그대로 표시하는 것이 2차 원인이다.

### 2-4. STEP_REASONING(추론 요약) 경로는 정상

`agent_step_reasoning`/`chat_step_reasoning`의 `reasoning` 필드는 백엔드에서 이미 문자열로 보장됨:
- `use_case.py:386` — `if not isinstance(content, str): return None`
- `run_agent_use_case.py:638-645` — `_step_output_summary`는 `(decision.reasoning or ...)[:1024]` 문자열 슬라이스

→ ToolPreviewPanel(`{text}`)은 원인이 아니다. **원인은 토큰 스트림 chunk.** (실제 객체가 JSX 자식으로 들어가면 React가 throw하므로, 화면에 보이는 `[object Object]`는 문자열 결합 산물 = chunk 경로로 확정.)

---

## 3. 수정 범위 (Scope)

| # | 수정 위치 | 내용 | 우선순위 |
|---|-----------|------|----------|
| 1 | (신규) `src/application/agent_builder/_text.py` 또는 기존 공용 util | `coerce_message_text(content) -> str` 헬퍼: `str`이면 그대로, `list`면 각 block의 `text`(dict) / str 요소를 join, 그 외 `""` | Critical |
| 2 | `run_agent_use_case.py::_map_chat_stream` | `chunk_text` 추출 후 헬퍼로 정규화. 정규화 결과가 빈 문자열이면 기존처럼 `None` 반환(스킵) | Critical |
| 3 | `general_chat/use_case.py::_map_token` | 동일 헬퍼 적용 | Critical |
| 4 | `useChatStream.ts` / `useAgentRunStream.ts` | `msg.data.chunk`를 `String(...)` 또는 가드로 방어적 처리(2차 안전망) | High |
| 5 | 테스트 | 백엔드: list content → str 정규화 단위테스트 / 프론트: chunk가 비정상일 때 `[object Object]` 미발생 회귀테스트 | High |

**범위 외**:
- STEP_REASONING(추론 요약) 표시 로직 — 이미 정상
- 차트/sources 렌더 — 본 이슈와 무관

---

## 4. 수정 방향 (Solution Design)

### 4-1. 공용 정규화 헬퍼 (백엔드, 1차 근본 수정)

```python
def coerce_message_text(content: object) -> str:
    """LangChain message content(str | list[block]) → 평탄화 문자열.

    - str: 그대로 반환
    - list: text block(dict의 "text") 또는 str 요소만 이어붙임
    - 그 외: 빈 문자열
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""
```

> 위치는 application 공용 util 또는 domain의 순수 함수로 둔다(외부 의존 없음 → 레이어 규칙 위반 아님). 두 use_case가 import해 사용.

### 4-2. 적용

```python
# run_agent_use_case._map_chat_stream
chunk_text = coerce_message_text(getattr(chunk_obj, "content", None))
if not chunk_text:
    return None

# general_chat/use_case._map_token
chunk_text = coerce_message_text(getattr(chunk_obj, "content", None))
if not chunk_text:
    return None
```

빈 문자열이면 기존 `if not chunk_text` 가드가 그대로 스킵 처리 → 잡음 토큰 미발행 동작 보존.

### 4-3. 프론트 방어적 가드 (2차 안전망)

```ts
// useChatStream.ts / useAgentRunStream.ts
const chunk = typeof msg.data.chunk === 'string'
  ? msg.data.chunk
  : '';
setState((s) => ({ ...s, tokens: s.tokens + chunk }));
```

백엔드 정규화가 1차 수정이지만, 계약 위반 재발 시 `[object Object]`가 다시 새지 않도록 프론트에도 string 가드를 둔다.

---

## 5. 테스트 계획 (TDD)

### 5-1. 백엔드 — content 정규화 단위 테스트
```python
def test_coerce_message_text_passthrough_str():
    assert coerce_message_text("hello") == "hello"

def test_coerce_message_text_flattens_block_list():
    blocks = [{"type": "text", "text": "안"}, {"type": "text", "text": "녕"}]
    assert coerce_message_text(blocks) == "안녕"

def test_coerce_message_text_ignores_non_text_blocks():
    blocks = [{"type": "tool_use", "id": "x"}, {"type": "text", "text": "ok"}]
    assert coerce_message_text(blocks) == "ok"

def test_coerce_message_text_none_returns_empty():
    assert coerce_message_text(None) == ""
```

### 5-2. 백엔드 — 매핑 회귀 테스트
- `_map_chat_stream`에 content=list인 fake chunk 주입 → payload `chunk`가 `str`이고 `[object` 문자열을 포함하지 않음.
- content=list이지만 text block이 전혀 없을 때 → `None` 반환(스킵).

### 5-3. 프론트 — 토큰 결합 회귀 테스트
- `useChatStream` / `useAgentRunStream`에 `chunk`가 객체/배열인 비정상 메시지를 흘려도 `tokens`에 `[object Object]`가 포함되지 않음 확인(가드 동작).
- 정상 string chunk 누적은 기존대로 동작.

---

## 6. 영향 범위 / 리스크

| 항목 | 영향 | 비고 |
|------|------|------|
| 정상 string chunk 경로 | **변경 없음** | 헬퍼가 str을 그대로 통과 |
| list content 모델 | **수정됨** | 평탄화 문자열로 정상 표시 |
| 토큰 스킵 로직 | 보존 | 빈 문자열 → 기존 `if not chunk_text` 스킵 |
| 레이어 규칙 | 위반 없음 | 순수 함수 헬퍼(외부 의존 X) |
| 프론트 타입 계약 | 변경 없음 | `chunk: string` 유지, 가드만 추가 |
| 기존 테스트 | 영향 없음 예상 | 신규 테스트만 추가 |

---

## 7. 구현 순서

1. (RED) 5-1 헬퍼 테스트 작성 → 실패 확인
2. (GREEN) `coerce_message_text` 헬퍼 구현
3. `_map_chat_stream` / `_map_token`에 헬퍼 적용 + 5-2 회귀 테스트
4. 프론트 `useChatStream` / `useAgentRunStream` string 가드 + 5-3 테스트
5. 로컬 dev 서버에서 list-content 모델로 `/chatpage` 수동 검증(추론 토큰 정상 표시)
6. `/pdca analyze fix-chat-reasoning-object-render` → Gap 분석 → Report

---

## 8. 미해결/후속 이슈

- **계약 검증 자동화**: WS payload 스키마(pydantic)에서 `chunk: str` 강제 검증을 추가하면 백엔드 단계에서 list 전송을 조기 차단 가능. 별도 검토.
- **chunk 메타데이터 손실**: tool_use 등 non-text block은 토큰 표시에서 제외된다. 추론 가시화가 더 필요하면 STEP_REASONING 경로로 별도 노출 검토.
