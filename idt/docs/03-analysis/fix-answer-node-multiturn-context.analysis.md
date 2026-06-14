# Gap Analysis: fix-answer-node-multiturn-context

> 분석일: 2026-05-19
> 분석 대상: Plan ↔ Implementation/Tests
> Match Rate: **100%**

---

## 1. 분석 개요

| 항목 | 내용 |
|------|------|
| Plan | `docs/01-plan/features/fix-answer-node-multiturn-context.plan.md` |
| Implementation | `src/application/agent_builder/workflow_compiler.py` (lines 233-296) |
| Tests | `tests/application/agent_builder/test_answer_node.py` (TC-A06~A08, lines 151-244) |
| Test Result | 8/8 PASS (단위), 188/188 PASS (agent_builder 전체) |

## 2. 카테고리별 점수

| Category | Score | Status |
|----------|:-----:|:------:|
| Plan §3 Scope Coverage | 100% | ✅ PASS |
| Plan §4-1 Code Semantic Match | 100% | ✅ PASS |
| Plan §5 Test Cases Coverage | 100% | ✅ PASS |
| Plan §3 Out-of-Scope Preservation | 100% | ✅ PASS |
| **Overall Match Rate** | **100%** | **✅ PASS** |

## 3. Plan §3 수정 범위 커버리지

| # | Plan Item | Expected | Actual | Status |
|---|-----------|----------|--------|:------:|
| 1 | `_create_answer_node()` 첫-매치-break 제거 + 전체 messages 전달 + 검색결과 AIMessage 제외 | workflow_compiler.py 수정 | `workflow_compiler.py:233-296` 수정 완료 | ✅ |
| 2 | answer_node 단위 테스트 + 회귀 테스트 | `tests/application/agent_builder/test_workflow_compiler.py` (Plan 명시 경로) | `tests/application/agent_builder/test_answer_node.py`의 `TestAnswerNodeMultiturn` 클래스 (TC-A06~A08) | ✅ Minor Deviation |

Minor deviation: Plan §3은 `test_workflow_compiler.py`로 명시했으나 실제로는 answer_node 전용 단위 테스트 파일에 추가됨. 응집도 관점에서 더 적절한 배치이며 Plan 의도(테스트 추가) 자체는 충족.

## 4. Plan §4-1 코드 의미적 일치도

| 요소 | Plan §4-1 (예시) | 실제 구현 | 동등성 |
|------|-----------------|-----------|:------:|
| 검색결과 식별 조건 | `name and "검색결과" in content` | `_is_search_result()` helper로 추출: `bool(name) and "검색결과" in content` | ✅ |
| 검색결과 컬렉션 | inline for-append | list comprehension via `_is_search_result()` | ✅ |
| 빈 검색결과 fallback | `"(검색 결과 없음)"` + warning log | 동일 (lines 258-262) | ✅ |
| 대화 메시지 빌드 | filter 검색결과 제외 | `[msg for msg in ... if not _is_search_result(msg)]` (line 264-266) | ✅ |
| answer_prompt 문자열 | "...가장 최근 질문에 정확하게 답변하세요..." | 100% 일치 (lines 268-273) | ✅ |
| 최종 messages 구조 | `[system, *conversation_messages]` | 동일 (lines 275-278) | ✅ |
| 로깅 필드 | `search_result_count`, `conversation_message_count` | 동일 (lines 280-284) | ✅ |
| return dict | `messages`, `last_worker_id="answer_agent"`, `token_usage` | 동일 (lines 290-294) | ✅ |
| dict/BaseMessage 혼합 처리 | isinstance 분기 | `_is_search_result()`가 `isinstance(msg, dict)` 처리 | ✅ |
| `user_query` 단일 추출 제거 | 제거 | 코드 내 존재하지 않음 (확인 완료) | ✅ |

추가 개선: `_is_search_result()` helper 추출로 search_results 수집과 conversation_messages 필터에서 중복 제거. Plan 예시 대비 DRY 향상, 의미적 동등.

## 5. Plan §5 테스트 케이스 커버리지

| Plan 테스트 | 의미 | 실제 테스트 | 상태 |
|------------|------|------------|:----:|
| 5-1 | 멀티턴 state → 전체 대화 + 최신 user 질문 전달 + 검색결과 system에만 | `TC-A06 test_passes_full_conversation_with_latest_user_question` | ✅ |
| 5-2 | 첫 user='안녕' 단독 전달 회귀 방지 | `TC-A07 test_first_user_message_alone_is_not_sent` | ✅ |
| 5-3 | 단일 턴 정상 동작 보존 | 기존 `TestAnswerNode` TC-A01·A03이 의미적으로 커버 | ✅ |
| 5-4 | 검색 결과 없는 warning 보존 | `TC-A04 test_no_search_results_uses_fallback` + 코드상 `logger.warning(...)` 유지 (line 259) | ✅ |
| 보너스 | 검색결과 AIMessage가 body에서 제외 | `TC-A08 test_search_result_ai_message_excluded_from_body` | ✅ |

## 6. Plan §3 "범위 외" 항목 보존 확인

| 항목 | 변경 금지 대상 | 실제 상태 | 상태 |
|------|--------------|----------|:----:|
| search_node 연속 호출 query 오추출 | `_create_search_node()` (line 298-330) | `state["messages"][-1]` 로직 그대로 유지 | ✅ 변경 없음 |
| supervisor FINISH 직접 답변 경로 | supervisor_nodes.py · route_to_worker | workflow_compiler.py 라우팅 동일 (line 153-170) | ✅ 변경 없음 |

## 7. Gap 항목

### 🔴 Missing (Plan O, Implementation X)
없음.

### 🟡 Added (Plan X, Implementation O — 개선 사항)
| 항목 | 위치 | 영향도 |
|------|------|--------|
| `_is_search_result()` helper 추출 | `workflow_compiler.py:244-249` | Low — DRY 개선, 의미 동등 |
| TC-A08 (검색결과 body 제외 독립 검증) | `test_answer_node.py:218-244` | Low — 회귀 방지 강화 |

### 🔵 Changed (Plan ≠ Implementation)
| 항목 | Plan | Implementation | 영향도 |
|------|------|----------------|-------|
| 테스트 파일 경로 | `test_workflow_compiler.py` | `test_answer_node.py` | Low — 응집도 측면에서 더 적절 |

## 8. 권장 조치

### Immediate
- 없음. 구현·테스트가 Plan을 100% 충족.

### Pending (Plan §7 구현 순서 잔여)
- 4번 항목: **로컬 dev 서버에서 멀티턴 시나리오 수동 검증** (안녕 → 안녕하세요 → 내부문서 질문). 단위/회귀 테스트는 통과했으나 실제 LLM 응답 품질 확인은 사용자 수동 검증 필요.

### Documentation (선택)
- Plan §3 표의 테스트 파일 경로를 실제 경로로 업데이트하면 후속 추적성 향상.

### Future (별도 Plan)
- Plan §8 미해결 이슈: search_node `state["messages"][-1]` 연속 호출 시 검색결과를 query로 재검색하는 오류는 별도 plan 발행 권장.

## 9. 최종 판정

**Match Rate: 100%** — Plan의 모든 명시 요구사항 (수정 범위, 코드 의미, 테스트 케이스, 범위 외 보존)이 충족됨. Deviation은 모두 코드 품질을 개선하는 방향이며 Plan 의도와 충돌하지 않음.

**Action(반복 개선) 불필요** (Match Rate ≥ 90%). `/pdca report fix-answer-node-multiturn-context` 진행 권장.
