# Worker ToolMessage Leak Fix Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Completion Date**: 2026-07-31
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | Worker ToolMessage Leak Fix |
| Start Date | 2026-07-29 |
| Completion Date | 2026-07-31 |
| Duration | 3 days |
| Match Rate | 100% (24/24 design items) |
| Iteration Count | 0 (≥90% on first check) |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────────────┐
│  Design Match Rate: 100%                             │
├──────────────────────────────────────────────────────┤
│  ✅ Matched:       24 / 24 items                     │
│  ⏳ Gaps:          0 / 24 items                      │
│  ✅ Tests Passed: 362 (agent_builder)               │
│  ✅ Architecture: 100% compliant                     │
│  ✅ TDD Cycle: 6 RED→GREEN test cases               │
│  ✅ Files Modified: 3                               │
│     - workflow_compiler.py (D1, D2, D3)             │
│     - test_worker_trace_leak.py (TC-01~06, NEW)     │
│     - test_workflow_compiler.py (TC-18 update)      │
└──────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 위키 워커 등 도구를 호출하는 react agent의 내부 트레이스(AIMessage(tool_calls) + ToolMessage + AIMessage(최종답))가 supervisor state로 통째로 유출되고, final_answer_node의 필터가 AIMessage만 제거해서 ToolMessage가 고아로 남아 OpenAI 400 ("messages with role 'tool' must be a response to a preceeding message with 'tool_calls'") 오류로 전체 런이 실패 |
| **Solution** | _wrap_worker가 react agent 결과의 최종 content로 AIMessage(name=worker_id) 1건만 재생성해 반환(D1, _wrap_sub_agent 규약 정렬) + final_answer_node의 conversation 필터에 tool 타입 메시지 2차 방어(D2) + token_delta 신규 산출분 기준으로 교정(D3). 부수적으로 멀티턴 히스토리 재구성 경로 감시(D4) |
| **Function/UX Effect** | 위키 질의("문서 X의 내용은?" 등) 시 워커가 wiki_read/wiki_list 도구를 정상 호출하고 final_answer까지 완주하는 경로 복원. 400 에러 없이 실제 답변 반환. 멀티턴 대화에서도 state 내 고아 tool 메시지가 후속 턴을 오염시키지 않음 |
| **Core Value** | 워커 규약의 단일화 — "워커 산출물은 AIMessage(name=worker_id) 1건"을 모든 워커가 준수(search/analysis/sub_agent/document_extractor는 기존 준수, _wrap_worker만 이탈). supervisor 그래프 메시지 불변식 복원으로 wiki-agentic-navigation 이후 상시화된 도구 호출 경로에서 LLM 프로바이더 제약을 만족 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [worker-toolmessage-leak-fix.plan.md](../01-plan/features/worker-toolmessage-leak-fix.plan.md) | ✅ Finalized |
| Design | [worker-toolmessage-leak-fix.design.md](../02-design/features/worker-toolmessage-leak-fix.design.md) | ✅ Finalized |
| Check | [worker-toolmessage-leak-fix.analysis.md](../03-analysis/worker-toolmessage-leak-fix.analysis.md) | ✅ Complete (100% match) |
| Act | Current document | ✅ Complete |

---

## 3. PDCA Cycle Summary

### 3.1 Plan Phase (2026-07-29)

**Document**: `docs/01-plan/features/worker-toolmessage-leak-fix.plan.md`

**Problem Diagnosis**:
- **Incident**: run_id `ba952a90` 실행 실패. final_answer_node의 llm.ainvoke에서 OpenAI BadRequestError 400
- **Symptom**: `messages.[2].role = 'tool' ... must be a response to a preceeding message with 'tool_calls'`
- **Root Cause Chain** (전 구간 코드 추적 확정):
  1. `_wrap_worker`(workflow_compiler.py:971-1000)가 react agent 결과의 **모든** 메시지(도구 호출 AIMessage + ToolMessage + 최종 답변 AIMessage)를 반환
  2. supervisor state의 `add_messages` 리듀서가 신규 메시지들을 append
  3. langgraph chat_agent_executor.py:676에서 모든 AIMessage에 `name=worker_id` 주입
  4. final_answer_node의 `_is_worker_output` 필터가 type=="ai" and name 조건으로 tool_calls AIMessage는 제거하나 ToolMessage(type=="tool")는 잔류
  5. LLM 입력이 `[system, Human(질문), ToolMessage, ...]` 형태 → OpenAI 400

**Trigger Condition**:
- wiki-agentic-navigation/wiki-folder-summaries로 wiki 워커(`workflow_compiler.py:308-315`) 신설 후 상시화
- 위키 워커는 wiki_list/wiki_read 도구를 반드시 호출하는 구조
- 라우팅이 `route_to_worker_or_final` → `final_answer_node` 경로 강제 → "위키 질의 = 항상 final_answer 경유" 재현 조건화

**Scope In/Out**:
- **In**: S1(_wrap_worker 최종 답변 단일 반환), S2(final_answer 2차 방어), S3(회귀 테스트), S4(E2E 수동)
- **Out**: 타 워커·search/analysis 파이프라인·프론트엔드·DB 무변경

### 3.2 Design Phase (2026-07-29)

**Document**: `docs/02-design/features/worker-toolmessage-leak-fix.design.md`

**D1 — _wrap_worker 최종 답변 재생성**:
```python
# 기존: react agent 결과 messages 전체 반환 (트레이스 유출)
# 변경: 마지막 메시지 content 추출 → 새 AIMessage(name=worker_id) 재생성 1건만 반환
answer_content = ""
if result_messages:
    last = result_messages[-1]
    answer_content = last.content if hasattr(last, "content") else str(last)

answer_msg = AIMessage(content=answer_content, name=worker_id)
```
- `_wrap_sub_agent`(1033-1039행)과 동일 패턴 선택
- langgraph name 주입 무관(직접 지정), tool_calls 필드 원천 제거, mock 테스트 결합 해제

**D2 — final_answer_node tool 타입 필터**:
```python
def _is_tool_message(msg) -> bool:
    """tool 역할 메시지 판정 — final_answer LLM 입력에서 제외."""
    if isinstance(msg, dict):
        return msg.get("role") == "tool"
    return getattr(msg, "type", "") == "tool"

# 필터 적용 (602-604행)
conversation_messages = [
    m for m in messages
    if not _is_worker_output(m) and not _is_tool_message(m)
]
```
- D1이 유출 원천 차단 → D2는 방어선(이전 결함 또는 향후 규약 이탈)
- 고아 여부 검사 기각: final_answer의 context는 워커 블록 요약이 충분하므로 tool 메시지 자체 불필요

**D3 — token_delta 교정**:
- 기존: react agent 결과 전체(입력 히스토리 포함) 재합산 → 과대계상
- 변경: 최종 답변 content 기준 `len(answer_content) // 4`
- 부스트 방향: 과대계상 → 정상화(한도 도달 지연 = 방어선)

**D4 — 멀티턴 히스토리 유입 확정**:
- `_build_messages`(run_agent_use_case.py:910-937)는 DB ConversationMessage를 `{"role": ..., "content": ...}` dict로만 재구성
- ToolMessage는 DB 저장 대상이 아님 → 단일 런 내부에 한정
- 결론: 히스토리 정화 마이그레이션 불필요

**Test Design** (§5.1~5.3):
- TC-01: 도구 호출 트레이스 → AIMessage 1건만, tool_calls 부재 (FR-01)
- TC-02: 직답 워커도 동일 규약 (FR-02)
- TC-03: token_delta는 최종 답변 기준 (FR-04)
- TC-04: 빈 결과 graceful 처리 (FR-02 edge)
- TC-05: 고아 ToolMessage 제외 (FR-03)
- TC-06: dict 형태 tool role도 제외 (FR-03 양형)
- TC-18 갱신: 단언을 identity(mock 객체 직접)에서 규약(1건·name·content) 재생성으로 교체

### 3.3 Do Phase (Implementation — 2026-07-30~31)

**Files Modified**:

1. **src/application/agent_builder/workflow_compiler.py**
   - Line 4: `AIMessage` import 확인 (기존 langchain_core)
   - Lines 982-1020: `_wrap_worker` 전체 재작성
     - D1: 최종 content 추출 + AIMessage 재생성
     - D3: token_delta 신규 산출분 기준
   - Lines 102-106: `_is_tool_message` 신규 헬퍼 추가
   - Lines 612-615: `final_answer_node` conversation 필터 (D2 적용)

2. **tests/application/agent_builder/test_worker_trace_leak.py** (신규 파일)
   - TestWrapWorkerNoTraceLeak 클래스: TC-01~04 (D1+D3 검증)
   - TestFinalAnswerToolDefense 클래스: TC-05~06 (D2 검증)
   - 모두 async/mock 패턴, RED 선행 확인 후 GREEN

3. **tests/application/agent_builder/test_workflow_compiler.py**
   - Line 583-605: TC-18 갱신 (`test_wrap_worker_updates_state`)
     - 기존: `result["messages"] == [mock_ai_msg]` identity
     - 변경: `len(result["messages"]) == 1` + `out.name == "worker_0"` + `out.content == mock_ai_msg.content` (재생성 규약)

**Code Quality**:
- `_wrap_worker` 함수 길이: 37줄 (40줄 규칙 준수)
- if 중첩: 1단계 (2단계 규칙 준수)
- 하드코딩 없음, 명시적 타입

### 3.4 Check Phase (Gap Analysis — 2026-07-31)

**Document**: `docs/03-analysis/worker-toolmessage-leak-fix.analysis.md`

**Match Rate: 100% (24/24)**
- Design 결정 (D1~D4·§4.3 기각·§7): 16 items → 16 matched
- Test 설계 (TC-01~06, TC-18 갱신): 8 items → 8 matched

**FR Fulfillment**:
| FR | Coverage | Evidence |
|:--:|:--------:|:---------|
| FR-01 | ✅ | 구현 + TC-01 (tool_calls 유출 부재) |
| FR-02 | ✅ | TC-02·TC-04 (직답·빈 결과 graceful) |
| FR-03 | ✅ | D2 필터 + TC-05/06 (tool role 제외) |
| FR-04 | ✅ | TC-03 (토큰 계산 신규 산출분 기준) |
| FR-05 | ✅ | 코드 무변경 실측 (search/analysis/sub_agent) |
| FR-06 | ⏸️ | E2E 수동 이월 (Qdrant/ES 기동 시 위키 질의) |

**Gap List**: 0건

**회귀 검증** (Windows 이벤트 루프 flakiness 고려):
- `pytest tests/application/agent_builder/` 격리 실행
- **결과**: 362 passed, ERROR 111건 (기존 WinError 10014 teardown 산발, 수정 전 코드와 동일)

---

## 4. Root Cause Chain (상세)

**계층별 분석**:

1. **워커 생성부** (`workflow_compiler.py:308-315`, wiki 워커):
   - wiki_list/wiki_read 도구 번들로 구성
   - 리듀서가 react agent 이전·이후 상태를 관리하지 않고 `_wrap_worker`에 위임

2. **_wrap_worker 반환** (`workflow_compiler.py:971-1000`, 수정 전):
   - `worker_agent.ainvoke(...)` 결과의 `messages` 전체를 `add_messages` 리듀서로 반환
   - 도구 호출 워커라면: `[AIMessage(tool_calls), ToolMessage, AIMessage(최종답)]` 3종 모두 포함

3. **langgraph 이름 주입** (chat_agent_executor.py:676, langgraph 라이브러리):
   - react agent 생성 시 자동으로 모든 AIMessage에 `name=worker_id` 주입
   - tool_calls 있는 중간 AIMessage도 name 획득 → name 기반 필터가 오작동

4. **final_answer_node 필터** (`workflow_compiler.py:602-604`, 수정 전):
   - `_is_worker_output(m)`: type=="ai" and name
   - 결과: tool_calls AIMessage만 제거, ToolMessage(type=="tool")는 통과
   - 상태: `[User, ToolMessage, AIMessage(최종답), ...]`

5. **LLM 호출** (workflow_compiler.py:617, openai.ChatCompletion):
   - 입력 메시지 배열: `[system, User, ToolMessage, ...]`
   - OpenAI 검증: tool role 앞에 tool_calls assistant 필수
   - **결과**: BadRequestError 400

**메시지 불변식 위반**:
```
정상(search 워커):  [AIMessage(name, 검색결과), ...]
정상(sub_agent):   [AIMessage(name, 답변), ...]
버그(tool 워커):   [AIMessage(tool_calls, name), ToolMessage, AIMessage(name, 최종답)]
                    ↑ 필터 후 → ToolMessage 고아 ↑
```

---

## 5. Key Lessons Learned

### 5.1 Architectural Insights

**1. 워커 규약은 단일 메시지 1건이어야 한다**
- 검색·분석·sub_agent·문서 추출기: 모두 `AIMessage(name=worker_id)` 1건 반환
- _wrap_worker 이탈 → LLM 입력 형식 깨짐
- **교훈**: 워커 계층은 state 조립 규칙이 아니라 **메시지 규약**을 보장해야 함. 내부 트레이스는 LangSmith 수준에서만 관측 (state 유출 = 후속 노드 계약 위반)

**2. `add_messages` 리듀서는 산출분만 누적한다**
- 리듀서가 모든 신규 메시지를 append하는 것이 기본 동작
- 워커 wrapper는 **이미 요약·필터된 최종 산출물만 반환**해야 내부 상태가 유출되지 않음
- **교훈**: 리듀서에 반환하는 messages는 "새로 생성한 산출분만" — 입력 히스토리나 중간 결과를 섞으면 후속 노드의 규약 검증이 깨짐

**3. LLM 프로바이더 제약은 구조적으로 강제해야 한다**
- "tool role 메시지는 반드시 tool_calls 앞에"는 단순 지시가 아니라 OpenAI 파서의 하드 제약
- 필터("고아 tool 메시지 제외")는 방어선이지만, 근본은 **소스(워커 반환 규약)에서 원천 차단**
- **교훈**: 프로바이더 계약 위반은 필터로 완전히 막기 어렵다. 데이터 생성 지점에서 규약을 보장하는 것이 안정성

### 5.2 Testing Discipline

**1. Red 단계가 재현을 확인한다**
- TC-01~04 작성 후 수정 전 코드로 실행 → 모두 실패 확인
- 이 단계 생략 시 "수정 코드가 실제로 문제를 해결했는가"를 검증 불가
- **교훈**: TDD Red 단계는 "테스트가 정상인가" 검증이 주 목적

**2. mock 바운더리 명확화**
- TC-01 mock_ai_msg는 identity 검사 금지, 규약 검사만 수행
- 워커 레이어는 내부 langgraph 동작(name 주입)에 의존하지 않도록 설계
- **교훈**: 외부 라이브러리 동작에 의존하는 mock 단언은 깨지기 쉽다. 계약 검사로 피벗

### 5.3 Observation Integrity

**LangSmith 관측은 state 유출과 무관하다**:
- react agent 내부 도구 호출 트레이스는 서브 run tree에 남음 (LangSmith에서 full 관측)
- state 정제로 관측성을 잃지 않음 (D1 설계 검증 항목)
- **교훈**: 상태 정화와 관측성은 직교(orthogonal). 불필요한 데이터는 제거해도 관측은 계속 가능

---

## 6. Results & Metrics

### 6.1 Code Changes

| File | Type | Lines Added | Lines Removed | Net |
|------|:----:|:-----------:|:-------------:|:---:|
| workflow_compiler.py | Modified | 28 | 28 | 0 |
| test_worker_trace_leak.py | New | 182 | - | +182 |
| test_workflow_compiler.py | Modified | 4 | 1 | +3 |
| **Total** | - | **214** | **29** | **+185** |

### 6.2 Test Coverage

| Category | Count | Status |
|----------|:-----:|:------:|
| 신규 테스트 (TC-01~06) | 6 | ✅ All Green |
| 기존 테스트 갱신 (TC-18) | 1 | ✅ Green |
| 회귀 검증 (`test_workflow_compiler*.py`) | 362 | ✅ Passed |
| Windows 이벤트 루프 산발 (기존) | 111 | 🔄 Unrelated |

### 6.3 Design Compliance

| Aspect | Target | Achieved | Status |
|--------|:------:|:--------:|:------:|
| Match Rate | ≥ 90% | 100% (24/24) | ✅ |
| Code Size | `_wrap_worker` ≤ 40줄 | 37줄 | ✅ |
| Nesting | if ≤ 1단계 | 1단계 | ✅ |
| Imports | 하드코딩 무 | ✅ | ✅ |

---

## 7. Known Limitations (Post-Implementation Notes)

이러한 항목들은 Gap이 아닌 "정리 후보"로, 설계 명세에 없으며 범위 밖입니다:

1. **TC-01의 tool_calls 단언은 사실상 항진**
   - 재생성 AIMessage는 항상 `tool_calls=[]` (또는 부재)
   - 실질 방어는 `len(out) == 1` 단언이 담당
   - 범위: 설계 TC 목록 미포함

2. **final_answer_node 응답 token_delta 미보호** (사전 존재)
   - 682행: `str` 가드 없이 block-list content 처리
   - 이번 D3은 답변 레벨만 적용
   - 범위: 설계 D3·TC 미포함, 향후 llm-content-list-fix 대상

3. **test_worker_trace_leak.py의 _make_compiler() vs test_workflow_compiler.py 동명 함수**
   - 서로 다른 시그니처(반환값 튜플 vs 단일 객체)
   - 기능상 문제 없음, 코드 리뷰 시 주의 항목

4. **content가 block list일 때 token_delta = 0**
   - 설계 TC 목록에 없음 (요구사항 아님)
   - 구현은 보수적 0 처리, 테스트 무 → 별도 이후 명확화 가능

---

## 8. Deferred Items (FR-06 E2E)

### 8.1 Manual E2E Verification

**Requirement**: FR-06 — 위키 워커 도구 호출 완주

**Scenario**:
```
질의: "[문서 X]의 X에 대해 설명해주세요" (wiki_read 도구 호출 필수)
기대: 400 에러 없이 → final_answer 도달 → 정상 답변
검증: GET /agents/runs/{run_id} step list + LangSmith 관측
```

**Deferred Reason**:
- 로컬 Qdrant/Elasticsearch 기동 필요
- 기존 KB pipeline E2E 체크리스트(2026-07-10 아카이브)에 합류
- V047(현재 버전) 배포 후 일괄 수동 검증 예정

**Status**: ⏸️ Pending (Qdrant/ES 기동 시 실행)

---

## 9. Impact on Dependent Features

### 9.1 Unchanged

- **search_pipeline.py**: `_is_worker_output` 무변경 (메시지 규약 단일 출처 유지)
- **workflow_compiler.py** 타 워커 (`_wrap_sub_agent`, search/analysis 노드): 무변경
- **API 계약**: 백엔드 단일 파일 수정 → 프론트엔드 동기화 불필요
- **DB 스키마**: 마이그레이션 무

### 9.2 Direct Beneficiaries

- **wiki-agentic-navigation** (2026-07-28 머지): wiki 워커 도구 호출 경로 정상화
- **wiki-folder-summaries** (2026-07-28 머지): wiki 워커 활용 기능 활성화
- **supervisor 그래프**: 메시지 불변식 복원 → 향후 워커 확장 시 규약 기준점 제공

---

## 10. Recommendations for Future

### 10.1 Pattern Consolidation

모든 워커가 반드시 준수할 규약을 문서화:
- 도메인 규칙 문서 (`docs/rules/`) 추가 가능: "Worker Message Contract"
- 규약: 산출물은 `AIMessage(name=worker_id, content=...)` 1건
- 내부 트레이스(tool_calls, ToolMessage)는 state로 유출 금지

### 10.2 Linting Rule

AST 기반 정적 검증(향후 verify-architecture 확장):
- `_wrap_worker` 반환값이 list여야 함 확인
- `add_messages` 호출 시 반환 messages 타입 검증 (워커 계층에만 1건 강제 불가, 워닝 수준)

### 10.3 Testing Automation

대형 그래프 테스트 패턴 정립:
- WorkflowCompiler mock 조립을 재사용 가능 fixture로 정의
- node 단위 테스트(이번 TC-05/06 패턴) 공식화
- 프로바이더 제약(tool 메시지 짝 검증) 일반 테스트 헬퍼 제공

---

## 11. Next Steps

### 11.1 Immediate (완료)

- [x] Code review & merge PR
- [x] Verify architecture compliance
- [x] Confirm TDD RED→GREEN cycle

### 11.2 Pre-Deployment (V047)

- [ ] Run full isolation pytest (`tests/application/agent_builder/`)
- [ ] Verify no regression in existing workflows (search/analysis/sub_agent)
- [ ] LangSmith 관측 확인 (react agent 내부 도구 호출 트레이스 유지)

### 11.3 Post-Deployment

- [ ] FR-06 E2E (Qdrant/ES 기동 시): 위키 질의 → run 완주 수동 검증
- [ ] Monitor supervisor decisions for wiki-related queries (첫 일주일)
- [ ] Update worker contract documentation (kb-management 팀과 협의)

---

## 12. Appendix

### 12.1 Commit Messages

```
worker-toolmessage-leak-fix: _wrap_worker 최종 답변 단일 반환 + final_answer 2차 방어

- D1: _wrap_worker가 react agent 최종 content로 AIMessage(name=worker_id) 1건만 반환
      (내부 tool_calls·ToolMessage 유출 차단, token_delta 신규 산출분 기준)
- D2: final_answer_node conversation 필터에 tool 타입 메시지 제외
      (고아 tool 메시지로 인한 OpenAI 400 2차 방어)
- Test: TC-01~06 신규 (worker trace leak 회귀) + TC-18 갱신 (규약 재생성 검증)

Fixes: run_id ba952a90 — "messages with role 'tool' must be a response to preceeding message with 'tool_calls'"
Design Match Rate: 100% (24/24)
Tests: 362 passed (agent_builder)
```

### 12.2 Code Review Checklist

```
☑ workflow_compiler.py 라인 982-1020: _wrap_worker 수정
  ☑ AIMessage import (line 4)
  ☑ answer_content 추출 logic (lines 1003-1007)
  ☑ token_delta 공식 (lines 1010-1012)
  ☑ return dict (lines 1014-1017)

☑ workflow_compiler.py 라인 102-106: _is_tool_message 신규 헬퍼
  ☑ dict role check
  ☑ message type check
  ☑ docstring (고아 방어 목적 명시)

☑ workflow_compiler.py 라인 612-615: final_answer_node 필터 적용
  ☑ _is_worker_output AND NOT _is_tool_message

☑ test_worker_trace_leak.py: 신규 파일
  ☑ 6 async test cases (TC-01~06)
  ☑ mock 조립 패턴 (_make_compiler, _react_agent_returning)
  ☑ 메시지 트레이스 헬퍼 (_trace_messages)

☑ test_workflow_compiler.py TC-18: 갱신
  ☑ identity → 규약 단언 교체
  ☑ len, name, content 검증

☑ 회귀 테스트
  ☑ pytest tests/application/agent_builder/ 격리 실행
  ☑ 362 passed 확인
  ☑ WinError 10014 기존 산발 무관 확인
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-31 | Completion report — D1/D2/D3 구현 + TC-01~06 신규 + TC-18 갱신, 100% match rate, 0 gaps | 배상규 |

