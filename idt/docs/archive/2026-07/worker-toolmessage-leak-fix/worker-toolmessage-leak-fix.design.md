# Worker ToolMessage Leak Fix Design Document

> **Summary**: 도구 워커 트레이스 유출 수정의 구현 설계 — `_wrap_worker`가 react agent 결과의 마지막 메시지 content로 **새 `AIMessage(name=worker_id)`를 재생성해 1건만 반환**(D1, `_wrap_sub_agent` 규약 정렬) + `final_answer_node` conversation 필터에 tool 타입 제외 2차 방어(D2) + token_delta 신규 산출분 교정(D3). 멀티턴 히스토리 재구성 경로는 role/content dict 전용으로 실측 확정되어 유입 없음(D4)
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-29
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/worker-toolmessage-leak-fix.plan.md`

---

## 1. Design Overview

수정 대상은 `workflow_compiler.py` 단일 파일의 2개 지점뿐이다. 그래프 구조·라우팅·메시지 규약
판정 로직(`search_pipeline.py`)·supervisor 노드는 무변경.

```
_wrap_worker (workflow_compiler.py:971-1000)          ← D1·D3: 최종 답변 단일 반환 + token 교정
        │ 반환 messages가 add_messages 리듀서로 state 누적
        ▼
SupervisorState.messages                               (이후 tool 계열 메시지 유입 원천 차단)
        │
final_answer_node (workflow_compiler.py:591-677)       ← D2: conversation 필터 tool 제외 (방어선)
```

**영향 범위 실측 (2026-07-29)**:

- ToolMessage를 소비하는 코드는 `agent_builder` 전체에 **없음** (grep 실측 — general_chat만
  자체 처리 보유, 별도 경로). 트레이스 제거로 잃는 소비자 없음.
- `_wrap_worker` 반환값을 단언하는 기존 테스트는 `test_workflow_compiler.py`
  `TestWrapWorker.test_wrap_worker_updates_state`(TC-18, 583-600행) 1건 —
  `result["messages"] == [mock_ai_msg]` **identity 단언이라 D1로 갱신 필수** (§5.2).
- 입력 측 단언 `test_tc10_wrap_worker_not_assistant_last`(839-851행)는
  `ensure_user_tail` 경유 입력만 검사 — 무회귀.
- 멀티턴 히스토리: `run_agent_use_case.py:910-937` `_build_messages`가
  `{"role", "content"}` dict만 생성(assistant/user, 요약 경로 포함) →
  **ToolMessage는 런을 넘어 잔존하지 않음** (D4 근거).

---

## 2. D1 — `_wrap_worker` 최종 답변 재생성 반환

### 2.1 결정

Plan §6.2에서 유보한 추출 방식 중 **"마지막 메시지 content 추출 → 새 AIMessage 재생성"**을
선택한다 (`_wrap_sub_agent` 1033-1039행과 동일 패턴).

| 대안 | 기각/채택 근거 |
|------|---------------|
| 마지막 메시지 객체 그대로 반환 | 기각 — langgraph가 name을 찍어주는 것에 의존(버전 결합), tool_calls 잔존 가능성, 테스트 mock과 결합 |
| 마지막 AIMessage 역탐색 | 기각 — react agent는 tool 호출 없는 모델 응답으로만 종료하므로 마지막 메시지가 곧 최종 AIMessage. 역탐색은 불필요한 일반화 |
| **content 추출 + AIMessage 재생성 (채택)** | name=worker_id 보장(langgraph 무관), tool_calls 필드 원천 제거, `_wrap_sub_agent`와 규약·코드 형태 통일 |

### 2.2 코드 변경 (workflow_compiler.py `_wrap_worker`)

```python
async def wrapped(state: SupervisorState) -> dict:
    result = await worker_agent.ainvoke(
        {"messages": ensure_user_tail(state["messages"], instruction=...)}  # 기존 유지
    )
    result_messages = result.get("messages", [])

    # 워커 규약: 산출물은 최종 AIMessage(name=worker_id) 1건.
    # react agent 내부 트레이스(tool_calls·ToolMessage)를 state로 유출하면
    # final_answer_node 필터가 짝을 깨 고아 tool 메시지가 됨 (OpenAI 400).
    answer_content = ""
    if result_messages:
        last = result_messages[-1]
        answer_content = last.content if hasattr(last, "content") else str(last)

    answer_msg = AIMessage(content=answer_content, name=worker_id)
    token_delta = len(answer_content) // 4 if isinstance(answer_content, str) else 0

    return {
        "messages": [answer_msg],
        "last_worker_id": worker_id,
        "token_usage": state["token_usage"] + token_delta,
    }
```

- `AIMessage` import는 모듈 상단 langchain_core에서 (함수 내 지역 import 지양 —
  `_reply`/`_wrap_sub_agent`의 지역 import는 이번 범위에서 건드리지 않음).
- 빈 결과(`messages: []`) → `AIMessage(content="", name=worker_id)` —
  `_wrap_sub_agent`와 동일한 graceful 동작 (FR-02 커버, 별도 fallback 문구 없음).
- content가 block list인 경우(비-str): 그대로 전달하되 token_delta는 0 —
  기존 `len(list)//4`도 부정확했으므로 보수적 0이 더 정직 (스트리밍 정규화는
  llm-content-list 계열 별도 관심사, 범위 외).

---

## 3. D2 — `final_answer_node` tool 타입 제외 (2차 방어)

### 3.1 결정

Plan §6.2에서 유보한 판정 기준 중 **"단순 tool 타입 제외"**를 선택한다.

- 고아 여부 검사(선행 tool_calls 존재 확인)는 기각: final_answer의 컨텍스트는 워커 블록
  (`[수집된 검색 결과]`/`[워커 작업 결과]`)이 이미 요약 제공하므로, 짝이 있는 tool 메시지도
  이 노드의 LLM 입력에는 **불필요**. 단순 제외가 안전하고 결정적.
- 헬퍼는 `workflow_compiler.py` 모듈 레벨 `_is_tool_message`로 둔다 —
  `search_pipeline.py`(메시지 규약 단일 출처)는 무변경 목표 유지(Plan §2.2),
  이 판정은 "워커 규약"이 아니라 final_answer의 입력 위생이므로 소비처에 둔다.

### 3.2 코드 변경

```python
def _is_tool_message(msg) -> bool:
    """tool 역할 메시지 판정 — final_answer LLM 입력에서 제외 (고아 tool 400 방어)."""
    if isinstance(msg, dict):
        return msg.get("role") == "tool"
    return getattr(msg, "type", "") == "tool"

# final_answer_node 내 (602-604행 교체):
conversation_messages = [
    m for m in messages
    if not _is_worker_output(m) and not _is_tool_message(m)
]
```

- D1이 유출을 원천 차단하므로 정상 경로에서 이 필터는 no-op이다.
  방어 대상: 이번 결함 이전에 생성돼 체크포인트/세션에 남은 오염 state(있다면),
  향후 규약 이탈 워커.

---

## 4. D3·D4 — 부수 결정

### 4.1 D3: token_delta 교정 (D1에 내포)

- 기존: react agent 결과 **전체**(입력 히스토리 포함) 재합산 → 과대계상.
- 변경: 최종 답변 content 기준 (§2.2 코드에 포함).
- `token_limit` 초과 판정(supervisor 라우팅)이 늦어지는 방향의 변화 — 과대계상의 **정상화**이며,
  한도 동작 자체는 `test_agent_iteration_limit.py`로 무회귀 확인.

### 4.2 D4: 멀티턴 히스토리 — 유입 없음 확정 (조사 종결)

- `_build_messages`(run_agent_use_case.py:910-937): DB `ConversationMessage`를
  `{"role": msg.role.value, "content": msg.content}` dict로만 재구성. 요약 경로
  (`_build_summarized_context`)·스냅샷 주입도 동일 형태.
- 결론: ToolMessage 유출은 **단일 런의 state 내부에 한정** — D2는 런 내 방어선으로 충분하며
  히스토리 정화 마이그레이션 등 추가 조치 불필요.

### 4.3 무변경 결정 (검토 후 기각)

| 후보 | 기각 근거 |
|------|----------|
| `_analyze_context`에도 tool 제외 추가 | 현재도 tool_calls 짝을 유지한 채 전달되어 유효 형식이고, D1 이후엔 tool 메시지 자체가 없음. 변경 반경 최소화 |
| `_is_worker_output` 판정 확장(tool 포함) | search_pipeline은 "워커 산출물" 판정의 단일 출처 — tool 메시지는 워커 산출물이 아니므로 의미 오염. 소비처 필터(D2)가 올바른 위치 |
| supervisor 결정 노드 입력 방어 | supervisor는 messages를 LLM에 직접 전달하지 않고 자체 프롬프트 조립 — 영향 없음 (기존 구조 유지) |

---

## 5. Test Design

### 5.1 신규 테스트 (`tests/application/agent_builder/test_worker_trace_leak.py`)

| ID | 시나리오 | 단언 |
|----|----------|------|
| TC-01 | react agent가 `[Human, AIMessage(tool_calls, name=w), ToolMessage, AIMessage(최종답, name=w)]` 반환 | 반환 messages == 1건, type=="ai", name==worker_id, content==최종답, tool_calls 부재 (FR-01) |
| TC-02 | 도구 호출 없는 직답 `[Human, AIMessage(직답)]` | 동일 규약 1건 반환 (FR-02) |
| TC-03 | TC-01 상태에서 token_usage 델타 | `len(최종답)//4` — 입력 히스토리·중간 트레이스 미합산 (FR-04) |
| TC-04 | react agent가 `messages: []` 반환 | `AIMessage(content="", name=worker_id)` 1건 — 예외 없음 |
| TC-05 | state.messages에 고아 ToolMessage 포함 상태로 final_answer_node 실행 (mock llm) | `llm.ainvoke` 인자에 tool 타입/role 메시지 부재 (FR-03) |
| TC-06 | TC-05에서 dict 형태 `{"role": "tool", ...}` 혼입 | 동일하게 제외 (dict/객체 양형 커버) |

- TC-01/03은 수정 전 **Red 확인** 필수 (현행 코드는 트레이스 전체 반환이므로 실패해야 정상).
- TC-05의 mock llm은 `AsyncMock(return_value=AIMessage(...))` — 기존
  `test_final_answer_node.py`의 조립 패턴 재사용.

### 5.2 기존 테스트 갱신

| 파일 | 갱신 내용 |
|------|----------|
| `test_workflow_compiler.py` TC-18 (`test_wrap_worker_updates_state`) | `result["messages"] == [mock_ai_msg]` identity 단언 → 재생성 규약 단언(1건·name=="worker_0"·content 동일)으로 교체 |
| `test_workflow_compiler.py` TC-10 | 무변경 (입력 측 검사) |
| `test_workflow_compiler_wiki_toc.py` 등 워커 생성부 테스트 | 무변경 예상 (compile/생성 검사) — 격리 실행으로 확인 |

### 5.3 회귀 스위트

```
pytest tests/application/agent_builder/ (격리 실행 — Windows 이벤트 루프 관례)
+ verify-architecture, verify-tdd
```

---

## 6. Implementation Order

```
1. TC-01~04 작성 → Red 확인 → _wrap_worker 수정 (D1+D3) → Green
2. TC-05~06 작성 → Red 확인 → _is_tool_message + final_answer 필터 (D2) → Green
3. TC-18 갱신 → agent_builder 전체 격리 실행 무회귀
4. E2E 수동 (FR-06): 위키 질의 → run 완주, GET /agents/runs/{run_id} step +
   LangSmith에서 react agent 내부 트레이스 관측 유지 확인
```

---

## 7. 주의사항 / 영향 범위

- **API 계약·DB·프론트 무변경** — 백엔드 단일 파일 + 테스트.
- 워커 최종 답변의 형식이 바뀌는 것이 아니라 **state에 남는 메시지 수**가 줄어드는 변경 —
  final_answer 블록 조립(`[워커 작업 결과]`)은 동일한 `AIMessage(name)` content를 소비하므로
  답변 품질 경로 불변.
- LangSmith 관측: 도구 호출 상세는 react agent 서브 run tree에 그대로 남음 —
  state 유출 제거는 관측 손실이 아님 (E2E에서 실측 확인 항목).
- 이 수정 전에 실행 중이던 세션의 오염 state는 D2가 흡수 — 별도 데이터 정리 불필요 (D4).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-29 | Initial draft — 추출 방식(재생성)·방어 기준(단순 제외)·히스토리 경로(유입 없음) 확정 | 배상규 |
