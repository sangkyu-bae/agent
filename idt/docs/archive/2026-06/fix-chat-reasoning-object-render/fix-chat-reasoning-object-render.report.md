# Fix Chat Reasoning Object Render — Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 1.0
> **Author**: 배상규
> **Completion Date**: 2026-06-08
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | fix-chat-reasoning-object-render |
| Start Date | 2026-06-07 |
| Completion Date | 2026-06-08 |
| Duration | < 1 day |
| Match Rate | 100% (모든 Plan 요구사항 충족) |
| Iteration Count | 0 (첫 Check에서 ≥90% 달성) |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────────────┐
│  Design Match Rate: 100%                             │
├──────────────────────────────────────────────────────┤
│  ✅ Plan Scope:        5 / 5 items                    │
│  ✅ Code Semantics:    7 / 7 items                    │
│  ✅ Test Cases:        5-1~5-3 모두 충족 (초과 달성)   │
│  ✅ 호환성 보존:        4 / 4 items                    │
│  🔴 Missing Gap:       0                              │
│  🟡 Minor Deviation:   1 (helper 위치 → domain, 개선) │
│  ✅ BE Tests:          helper 10 + agent 2 + chat 2   │
│  ✅ FE Tests:          useChatStream 13, agentRun 14  │
│  ✅ tsc --noEmit:      0 errors                       │
└──────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | `/chatpage`에서 WS 추론 토큰 스트림을 화면에 띄울 때, 일부 LLM이 chunk의 `content`를 content block 리스트로 내려주는 경우 `[object Object]`로 표시되던 치명적 출력 결함 (Agent / General Chat 양쪽) |
| **Solution** | domain 순수 함수 `coerce_message_text()` 도입 — 백엔드 스트리밍 매핑 2곳(`_map_chat_stream`, `_map_token`)에서 chunk content를 항상 평탄화 문자열로 정규화. 프론트 2개 hook에 `typeof === 'string'` 가드를 추가해 2차 안전망 구축 |
| **Function/UX Effect** | content block 기반 모델(reasoning/tool-call 동반)에서도 추론 토큰이 깨지지 않고 사람이 읽는 텍스트로 자연스럽게 스트리밍. text 없는 block(tool_use 단독)은 잡음 없이 스킵 |
| **Core Value** | 사용자가 보는 핵심 출력(스트리밍 답변)의 **신뢰성 회복**. `[object Object]`는 "제품이 깨졌다"는 즉각적 인상을 주는 결함 — 근본 수정 + 안전망 이중화로 재발 방지까지 확보 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [fix-chat-reasoning-object-render.plan.md](../01-plan/features/fix-chat-reasoning-object-render.plan.md) | ✅ Finalized |
| Design | (생략 — Plan §4에 구현 코드 명시되어 단일 fix 범위로 design skip) | ⏭️ Skipped |
| Check | [fix-chat-reasoning-object-render.analysis.md](../03-analysis/fix-chat-reasoning-object-render.analysis.md) | ✅ Complete |
| Act | Current document | ✅ Complete |

---

## 3. PDCA Cycle Summary

### 3.1 Plan Phase (2026-06-07)

**Document**: `docs/01-plan/features/fix-chat-reasoning-object-render.plan.md`

**Root Cause Identified**:
- LangChain `on_chat_model_stream` chunk의 `.content`는 모델/구성에 따라 `str` 또는 content block 리스트(`[{"type":"text","text":"..."}]`)
- 백엔드 `run_agent_use_case._map_chat_stream`(agent) / `general_chat/use_case._map_token`(chat)이 `getattr(chunk_obj, "content")`를 정규화 없이 WS payload `chunk`에 그대로 적재
- 프론트 `useChatStream`/`useAgentRunStream`이 `s.tokens + msg.data.chunk` 문자열 결합 → list면 `"[object Object]"` 생성 → `MessageBubble`이 그대로 렌더
- STEP_REASONING(추론 요약) 경로는 이미 문자열 보장이라 원인 아님 (확정)

**Scope Decision**:
- ✅ 백엔드 공용 정규화 헬퍼 (근본 수정)
- ✅ 2개 매핑 함수에 헬퍼 적용 (빈 문자열 스킵 가드 보존)
- ✅ 프론트 2개 hook string 가드 (2차 안전망)
- ✅ 백엔드/프론트 회귀 테스트
- ⏭️ WS payload pydantic 강제 검증, non-text block 가시화는 후속 분리

### 3.2 Design Phase

**Status**: Skipped — Plan §4에 헬퍼·적용 코드가 구체적으로 명시되어 별도 design 문서 불필요.

### 3.3 Do Phase (Implementation)

**TDD Cycle**:

1. **RED**: `tests/domain/llm/test_message_content.py` 작성 → `ModuleNotFoundError: src.domain.llm.message_content` 로 실패 확인
2. **GREEN**: `src/domain/llm/message_content.py::coerce_message_text()` 구현 → 10/10 PASS
3. 백엔드 매핑 2곳에 헬퍼 적용 + 회귀 테스트 추가 (agent 2, general chat 2) → PASS
4. 프론트 2개 hook string 가드 + 회귀 테스트 1개씩 → PASS
5. **VERIFY**: 백엔드 import 정상 로드, 프론트 `tsc --noEmit` 무에러

**Files Changed**:

| File | Change Type |
|------|-------------|
| `src/domain/llm/message_content.py` | Added — `coerce_message_text()` 순수 함수 |
| `src/application/agent_builder/run_agent_use_case.py` | Modified — `_map_chat_stream` 정규화 적용 + import |
| `src/application/general_chat/use_case.py` | Modified — `_map_token` 정규화 적용 + import |
| `idt_front/src/hooks/useChatStream.ts` | Modified — `chat_token` string 가드 |
| `idt_front/src/hooks/useAgentRunStream.ts` | Modified — `agent_token` string 가드 |
| `tests/domain/llm/test_message_content.py` | Added — 헬퍼 단위 10개 |
| `tests/application/agent_builder/test_run_agent_use_case_stream.py` | Added — list-content 회귀 2개 |
| `tests/application/general_chat/test_use_case.py` | Added — `TestChatTokenContentNormalization` 2개 |
| `idt_front/src/hooks/useChatStream.test.ts` | Added — `[object Object]` 미발생 회귀 1개 |
| `idt_front/src/hooks/useAgentRunStream.test.ts` | Added — `[object Object]` 미발생 회귀 1개 |

### 3.4 Check Phase (Gap Analysis)

**Document**: `docs/03-analysis/fix-chat-reasoning-object-render.analysis.md`

**Match Rate: 100%**

| Category | Score |
|----------|:-----:|
| Plan §3 Scope Coverage (5 items) | 100% |
| Plan §4 Solution Semantic Match | 100% |
| Plan §5 Test Cases Coverage | 100% |
| Plan §6 호환성 보존 | 100% |

**Gap 발견 사항**:
- 🔴 Missing: 없음
- 🟡 Minor Deviation: 헬퍼 위치를 Plan 제시(application 하위)가 아닌 `src/domain/llm/message_content.py`(domain 순수 함수)로 배치 — 두 application use_case 공유·레이어 규칙 부합 측면의 개선이라 Gap 아님

### 3.5 Act Phase

**Status**: 불필요 — Match Rate 100%로 90% 임계 초과. 추가 iteration 없이 Report 직행.

---

## 4. Technical Details

### 4.1 Bug Reproduction (Before Fix)

```python
# on_chat_model_stream chunk (content block 모델)
chunk.content = [{"type": "text", "text": "안"}, {"type": "text", "text": "녕"}]

# 백엔드 매핑 — 정규화 없이 그대로 적재
chunk_text = getattr(chunk_obj, "content", None)   # ← list
return {"chunk": chunk_text}                         # WS payload에 list 적재

# 프론트
tokens = s.tokens + msg.data.chunk                   # "" + [list] → "[object Object]"
```

### 4.2 Fix Implementation (After Fix)

```python
# src/domain/llm/message_content.py
def coerce_message_text(content: object) -> str:
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

```python
# 백엔드 적용 (양쪽 매핑 동일 패턴)
chunk_text = coerce_message_text(getattr(chunk_obj, "content", None))
if not chunk_text:        # 빈 문자열 → 기존 스킵 가드 보존
    return None
```

```ts
// 프론트 2차 안전망 (useChatStream / useAgentRunStream)
const chunk = typeof msg.data.chunk === 'string' ? msg.data.chunk : '';
setState((s) => ({ ...s, tokens: s.tokens + chunk }));
```

### 4.3 Why "백엔드 정규화 + 프론트 가드" 이중화

| 대안 | 장점 | 단점 | 선정 |
|------|------|------|------|
| (A) 프론트만 가드 | 빠름 | 백엔드 계약 위반(list 전송) 그대로 — payload 오염, 다른 소비자도 위험 | ❌ |
| (B) 백엔드만 정규화 | 근본 수정 | 계약 재위반 시 재발 방지 없음 | ❌ |
| **(C) 백엔드 정규화 + 프론트 가드** | 근본 원인 제거 + 재발 방지 안전망. 도메인 순수 함수로 재사용 | 코드 2곳 | ✅ |

---

## 5. Out-of-Scope / Future Work

### 5.1 후속 과제 (Plan §8)
- **WS payload 스키마 강제 검증**: 도메인 WSMessage/payload pydantic에서 `chunk: str` 강제 → 백엔드 단계에서 list 전송 조기 차단
- **non-text block 가시화**: tool_use 등은 현재 토큰 표시에서 제외. 추론 가시화 강화 필요 시 STEP_REASONING 경로로 별도 노출 검토

### 5.2 수동 검증 (권장)
로컬 dev 서버에서 content block 기반 모델(예: Anthropic)로 `/chatpage` 스트리밍 시 추론 토큰이 정상 텍스트로 표시되는지 최종 육안 확인 (자동 테스트로 동등 검증 완료).

---

## 6. Lessons Learned

| 항목 | 내용 |
|------|------|
| **LLM content 다형성** | `message.content`는 provider/구성에 따라 `str` 또는 content block `list`. WS·DB·UI로 흐르는 경계에서는 항상 문자열로 정규화하는 단일 지점을 두는 것이 안전 |
| **계약 위반의 책임 분리** | 1차 원인은 백엔드의 타입 계약(`chunk: str`) 위반, 2차는 프론트 무방비. 근본 수정(백엔드) + 방어(프론트) 이중화가 재발 방지에 효과적 |
| **도메인 순수 함수 배치** | LLM 메시지 형태 정규화는 외부 의존 없는 순수 규칙 → domain 배치가 레이어 규칙 부합 + application 양쪽 재사용. Plan의 위치 제안보다 더 적절 |
| **Windows 테스트 환경** | 백엔드 pytest 교차 실행 시 이벤트 루프 teardown 산발 ERROR → 격리 실행으로 검증. 프론트 vitest는 `--no-isolate --pool=threads`로 워커 기동 타임아웃 회피 |

---

## 7. Acceptance Criteria

| Criteria | Result |
|----------|:------:|
| content가 block list여도 평탄화 문자열로 토큰 발행 (agent) | ✅ `test_content_block_list_is_flattened_to_str` PASS |
| content가 block list여도 평탄화 문자열로 토큰 발행 (general chat) | ✅ `test_content_block_list_flattened` PASS |
| text 없는 block list는 토큰 스킵 | ✅ `..._without_text_skipped` PASS (양쪽) |
| 정상 str chunk 경로 무변경 | ✅ 기존 토큰 테스트 유지 |
| 프론트 비정상 chunk에 `[object Object]` 미발생 | ✅ 두 hook 회귀 테스트 `not.toContain('[object Object]')` PASS |
| 헬퍼 단위 동작 (str/list/non-text/None/기타) | ✅ 10/10 PASS |
| 레이어 규칙 위반 없음 + import 정상 | ✅ domain 순수 함수, import OK |
| 프론트 타입 무에러 | ✅ tsc --noEmit 0 errors |

**Final Status**: ✅ **Completed (100% Match Rate, 0 Regression)**
