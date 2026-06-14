# Fix Answer Node Multiturn Context — Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Completion Date**: 2026-05-19
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | fix-answer-node-multiturn-context |
| Start Date | 2026-05-19 |
| Completion Date | 2026-05-19 |
| Duration | < 1 day |
| Match Rate | 100% (모든 Plan 요구사항 충족) |
| Iteration Count | 0 (첫 Check에서 ≥90% 달성) |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────────────┐
│  Design Match Rate: 100%                             │
├──────────────────────────────────────────────────────┤
│  ✅ Plan Scope:        2 / 2 items                    │
│  ✅ Code Semantics:    10 / 10 items                  │
│  ✅ Test Cases:        5 / 5 items (5-1~5-4 + bonus)  │
│  ✅ Out-of-Scope 보존: 2 / 2 items                    │
│  🔴 Missing Gap:       0                              │
│  🟡 Added (improvement): 2 (helper, 추가 회귀 테스트) │
│  ✅ Unit Tests:        8 / 8 (answer_node)            │
│  ✅ Regression Tests: 188 / 188 (agent_builder 전체) │
└──────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | `POST /api/v1/agents/{agent_id}/run` 멀티턴 호출 시 `answer_node`가 세션의 첫 user 메시지("안녕")만 LLM에 보내 검색결과(예: 내부문서 조회)와 무관한 답변이 생성되던 치명적 버그 |
| **Solution** | `_create_answer_node()`의 `for ... break` 단일 user 추출 로직 제거 → 전체 대화 messages를 LLM에 그대로 전달하되, search_node가 추가한 검색결과 AIMessage(`name` + content에 "검색결과")는 system prompt의 `[수집된 검색 결과]` 블록과 중복되므로 본체에서 제외 |
| **Function/UX Effect** | 멀티턴 대화에서 follow-up 질문, 지시어("그럼 그건?", "더 자세히"), 이전 컨텍스트 참조가 정상 동작. 검색결과는 항상 최신 사용자 질문 기준으로 답변에 반영 |
| **Core Value** | RAG 기반 내부문서 질의응답의 **대화 일관성 회복**. "AI가 방금 한 말을 기억 못한다"는 치명적 사용자 경험 제거 — 내부 직원 사용 신뢰도 직접 영향 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [fix-answer-node-multiturn-context.plan.md](../01-plan/features/fix-answer-node-multiturn-context.plan.md) | ✅ Finalized |
| Design | (생략 — 단일 함수 fix 범위로 design 단계 skip) | ⏭️ Skipped |
| Check | [fix-answer-node-multiturn-context.analysis.md](../03-analysis/fix-answer-node-multiturn-context.analysis.md) | ✅ Complete |
| Act | Current document | ✅ Complete |

---

## 3. PDCA Cycle Summary

### 3.1 Plan Phase (2026-05-19)

**Document**: `docs/01-plan/features/fix-answer-node-multiturn-context.plan.md`

**Root Cause Identified**:
- `workflow_compiler.py:250-256` 의 `_create_answer_node()` 가 `for msg in state["messages"]: ... break` 로 첫 user 메시지만 추출
- `RunAgentUseCase._build_messages()` 가 멀티턴 시 DB의 전체 history를 빌드해서 보내도, answer_node가 그중 첫 user("안녕")만 LLM에 전달
- 결과: 검색결과는 최신 질문 기준으로 모였지만 LLM에 가는 user 질문은 "안녕" 으로 모순된 입력 → 엉뚱한 답변

**Scope Decision (사용자 결정)**:
- ✅ answer_node 만 우선 수정 (search_node 멀티턴 이슈는 별도 plan으로 분리)
- ✅ 전체 대화 맥락을 LLM에 전달 (follow-up 질문 처리까지 동시 해결)
- ✅ 검색결과 AIMessage는 system prompt와 중복되므로 본체에서 제외
- ✅ 단위 테스트 + 회귀 테스트 작성
- ✅ supervisor FINISH 직접 답변 경로는 정상 동작이므로 보존

### 3.2 Design Phase

**Status**: Skipped — 단일 함수 수정 + Plan §4-1에 구현 코드가 명시되어 별도 design 문서 불필요.

### 3.3 Do Phase (Implementation)

**TDD Cycle**:

1. **RED**: `tests/application/agent_builder/test_answer_node.py` 에 `TestAnswerNodeMultiturn` 클래스 추가
   - TC-A06: 멀티턴 state → 전체 대화 + 최신 user 질문 LLM 전달 검증
   - TC-A07: 첫 user='안녕'만 단독 전달되는 레거시 버그 회귀 방지
   - TC-A08: 검색결과 AIMessage가 LLM messages 본체에서 제외 검증
   - 실행 결과: TC-A06/A07 **FAIL** → 정확히 `user_contents == ['안녕']` 으로 버그 재현

2. **GREEN**: `src/application/agent_builder/workflow_compiler.py::_create_answer_node()` 재작성
   - `_is_search_result()` helper 도입 (DRY)
   - `user_query` 단일 추출 로직 제거
   - `conversation_messages = [msg for msg in ... if not _is_search_result(msg)]`
   - `messages = [{"role": "system", "content": answer_prompt}, *conversation_messages]`
   - answer_prompt 텍스트 갱신: "사용자의 가장 최근 질문에 정확하게 답변하세요... 이전 대화 맥락도 참고하세요"
   - 로깅 필드 추가: `conversation_message_count`

3. **VERIFY**: 
   - `tests/application/agent_builder/test_answer_node.py`: **8/8 PASS**
   - `tests/application/agent_builder/` 전체: **188/188 PASS** (회귀 없음)

**Files Changed**:

| File | Lines | Change Type |
|------|-------|-------------|
| `src/application/agent_builder/workflow_compiler.py` | 233-296 | Modified — `_create_answer_node()` 재작성 |
| `tests/application/agent_builder/test_answer_node.py` | +94 lines (TestAnswerNodeMultiturn 클래스 + helpers) | Added |

### 3.4 Check Phase (Gap Analysis)

**Document**: `docs/03-analysis/fix-answer-node-multiturn-context.analysis.md`

**Match Rate: 100%**

| Category | Score |
|----------|:-----:|
| Plan §3 Scope Coverage | 100% |
| Plan §4-1 Code Semantic Match | 100% |
| Plan §5 Test Cases Coverage | 100% |
| Plan §3 Out-of-Scope Preservation | 100% |

**Gap 발견 사항**:
- 🔴 Missing: 없음
- 🟡 Added (개선): `_is_search_result()` helper 추출 (DRY 개선), TC-A08 독립 회귀 테스트
- 🔵 Changed: 테스트 파일 경로만 응집도 측면에서 더 적절한 `test_answer_node.py` 로 배치 (Plan 명시 경로 `test_workflow_compiler.py` 대신)

### 3.5 Act Phase

**Status**: 불필요 — Match Rate 100% 로 90% 임계 초과. 추가 iteration 없이 Report 단계로 직행.

---

## 4. Technical Details

### 4.1 Bug Reproduction (Before Fix)

```python
# state["messages"] (멀티턴 + search 워커 호출 후)
[
    HumanMessage(content="안녕"),                    # turn 1
    AIMessage(content="안녕하세요!"),                # turn 2
    HumanMessage(content="우리 내부문서에서 X 알려줘"),  # turn 3 (현재)
    AIMessage(content="[research_worker 검색결과]\n...", name="research_worker"),
]

# answer_node 진입 → 첫 user 매치-break
for msg in state["messages"]:
    if role in ("user", "human"):
        user_query = content   # "안녕" ← 버그
        break

# LLM에 전달
[
    {"role": "system", "content": "...[수집된 검색 결과]\n내부문서 X 자료..."},
    {"role": "user",   "content": "안녕"},   # 검색결과와 모순된 질문
]
```

### 4.2 Fix Implementation (After Fix)

```python
def _is_search_result(msg) -> bool:
    if isinstance(msg, dict):
        return False
    name = getattr(msg, "name", None)
    content = getattr(msg, "content", "")
    return bool(name) and "검색결과" in content

async def answer_node(state: SupervisorState) -> dict:
    search_results = [
        getattr(msg, "content", "")
        for msg in state["messages"]
        if _is_search_result(msg)
    ]
    context = "\n\n---\n\n".join(search_results) if search_results else "(검색 결과 없음)"

    conversation_messages = [
        msg for msg in state["messages"] if not _is_search_result(msg)
    ]

    answer_prompt = (
        f"{system_prompt}\n\n"
        f"아래 검색 결과를 바탕으로 사용자의 가장 최근 질문에 정확하게 답변하세요.\n"
        f"검색 결과에 없는 내용은 추측하지 마세요. 이전 대화 맥락도 참고하세요.\n\n"
        f"[수집된 검색 결과]\n{context}"
    )

    messages = [{"role": "system", "content": answer_prompt}, *conversation_messages]
    response = await llm.ainvoke(messages)

    return {
        "messages": [response],
        "last_worker_id": "answer_agent",
        "token_usage": state["token_usage"] + len(response.content) // 4,
    }
```

### 4.3 Why "전체 messages 전달" Approach

| 대안 | 장점 | 단점 | 선정 |
|------|------|------|------|
| (A) 최신 user 1개만 (`reversed(messages)` first match) | 최소 변경 | follow-up 질문("그럼 그건?") 지시어 처리 불가 | ❌ |
| (B) 최신 user + 이전 대화 요약 system | 토큰 절감 | 요약 없는 짧은 대화는 컨텍스트 부족 | ❌ |
| **(C) 전체 messages 전달 (검색결과만 필터)** | 모든 follow-up 시나리오 자연 동작, `_build_summarized_context` 요약 정책이 이미 토큰 폭증 방지 | 토큰 사용량 약간 증가 | ✅ |

사용자가 직접 "전체 대화 맥락을 다 줘야하는거 아니야?" 라고 검증 — 선택 C 확정.

---

## 5. Out-of-Scope / Future Work

### 5.1 별도 Plan 필요한 이슈

**search_node 연속 호출 시 query 추출 오류** (Plan §8 참조):
- `_create_search_node()` 가 `state["messages"][-1]` 로 query 추출
- supervisor 가 search 워커를 2회 이상 연속 호출 시 두 번째 호출 시 마지막 메시지가 직전 검색결과 AIMessage → 검색결과 문자열을 query 로 또 검색하는 형태
- 별도 plan 발행 필요

### 5.2 수동 검증 (사용자 확인 권장)

로컬 dev 서버에서 다음 시나리오로 실제 LLM 응답 품질 확인:
1. POST `/api/v1/agents/{agent_id}/run` 으로 query="안녕" 호출 (session_id 미지정 → 새 세션)
2. 응답 session_id 받아서 동일 session_id 로 query="우리 내부문서에서 ~~~ 알려줘" 호출
3. 답변이 검색결과 기반인지 + "안녕"과 무관한지 확인

---

## 6. Lessons Learned

| 항목 | 내용 |
|------|------|
| **LangGraph 노드의 state 가정** | `state["messages"]` 는 멀티턴 시 DB history 포함이므로 단순 `[0]` 또는 `for ... break` 접근은 항상 멀티턴 버그 위험. 메시지 의미적 식별(role, name, content pattern) 기반 필터링이 안전 |
| **TDD 효과** | RED 단계에서 정확히 `user_contents == ['안녕']` 으로 사용자가 보고한 증상 재현됨 → fix의 근거 명확화. GREEN 후 회귀 0건 확인 |
| **검색결과 식별 휴리스틱의 약점** | `"검색결과" in content` 한국어 고정 문자열 의존. 구조화된 메타데이터(`additional_kwargs["msg_type"] = "search_result"`)로 개선 검토 필요 — 별도 후속 과제 |

---

## 7. Acceptance Criteria

| Criteria | Result |
|----------|:------:|
| 멀티턴 시 answer_node가 최신 user 질문 + 전체 대화 맥락 전달 | ✅ TC-A06 PASS |
| 첫 user 메시지만 단독 전달되지 않음 (회귀 방지) | ✅ TC-A07 PASS |
| 검색결과 AIMessage 가 LLM messages 본체에서 제외 | ✅ TC-A08 PASS |
| 단일 턴 정상 동작 보존 | ✅ TC-A01~A05 PASS |
| 검색 결과 없을 시 fallback + warning 로그 | ✅ TC-A04 PASS + 로그 코드 유지 |
| 기존 188개 agent_builder 테스트 회귀 0건 | ✅ 188/188 PASS |
| Plan §3 "범위 외" 항목 변경 없음 | ✅ search_node, supervisor 변경 없음 확인 |

**Final Status**: ✅ **Completed (100% Match Rate, 0 Regression)**
