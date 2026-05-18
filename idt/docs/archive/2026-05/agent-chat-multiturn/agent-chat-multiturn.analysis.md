# agent-chat-multiturn Gap Analysis Report

> **Feature**: agent-chat-multiturn
> **Design Document**: `docs/02-design/features/agent-chat-multiturn.design.md`
> **Analysis Date**: 2026-05-10
> **Analyzer**: gap-detector Agent

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 90% | [WARN] |
| Architecture Compliance | 100% | [PASS] |
| Convention Compliance | 95% | [PASS] |
| **Overall** | **93%** | **[PASS]** |

---

## File-by-File Comparison

### File 1: `src/application/agent_builder/schemas.py` — 100%

| Design Spec | Implementation | Match |
|-------------|---------------|:-----:|
| `RunAgentRequest.session_id: str \| None = None` | ✅ Present | PASS |
| `RunAgentResponse.session_id: str` | ✅ Present | PASS |
| `RunAgentRequest.query: str = Field(..., min_length=1, max_length=2000)` | ✅ Identical | PASS |
| `RunAgentRequest.user_id: str` | ✅ Identical | PASS |

### File 2: `src/application/agent_builder/run_agent_use_case.py` — 88%

| Design Spec | Implementation | Match |
|-------------|---------------|:-----:|
| 4 new dependencies in `__init__` | ✅ All 4 present with correct types | PASS |
| session_id decision: `request.session_id or uuid4()` | ✅ Matches | PASS |
| Case 1 (no history): user query only | ✅ Matches | PASS |
| Case 2 (≤6 turns): full history + query | ✅ Matches | PASS |
| Case 3 (>6 turns): summary + recent 3 turns + query | ✅ Matches | PASS |
| Session ownership: silent new session on mismatch | ✅ Implicit via user_id filter | PASS |
| Message saving: user+assistant after execution | ⚠️ Conditional on `request.session_id is not None` | **GAP** |

### File 3: `src/api/main.py` — 100%

| Design Spec | Implementation | Match |
|-------------|---------------|:-----:|
| `run_uc_factory` injects `SQLAlchemyConversationMessageRepository` | ✅ Present | PASS |
| `run_uc_factory` injects `SQLAlchemyConversationSummaryRepository` | ✅ Present | PASS |
| `run_uc_factory` injects `LangChainSummarizer(model_name, api_key)` | ✅ Present | PASS |
| `run_uc_factory` injects `SummarizationPolicy()` | ✅ Present | PASS |

### File 4: `tests/application/agent_builder/test_run_agent_use_case.py` — 86%

| Design Test Case | Implementation | Match |
|-----------------|---------------|:-----:|
| TC-01: Backward compat | ✅ `test_backward_compat_no_session_id_single_turn` | PASS |
| TC-02: New session auto-generated | ✅ `test_session_id_auto_generated_when_none` | PASS |
| TC-03: Continue session with history | ✅ `test_history_loaded_when_session_id_provided` + `test_history_injected_into_graph_messages` | PASS |
| TC-04: Summarization at 7 turns | ✅ `test_summarization_triggered_when_exceeds_threshold` | PASS |
| TC-05: Message saving | ✅ `test_messages_saved_after_execution` | PASS |
| TC-06: Session ownership | ❌ **NOT IMPLEMENTED** | MISSING |
| TC-07: Existing tests unbroken | ✅ 4 original tests present with updated constructor | PASS |

---

## Gap Details

### [GAP-1] Message saving condition (Medium Impact)

| | Detail |
|---|--------|
| **Design** | Section 5.2 step 6: "응답 파싱 후 메시지 저장" — 실행 후 무조건 저장 |
| **Implementation** | `if request.session_id is not None` — 클라이언트가 명시 전달한 경우만 저장 |
| **Impact** | 첫 대화 시 session_id=None으로 호출하면 메시지 미저장. 이후 자동 생성된 session_id로 이어서 대화 시 히스토리 없음 |
| **Fix Option A** | 조건 제거: 항상 메시지 저장 (설계 의도 일치) |
| **Fix Option B** | 설계 문서 업데이트: 명시적 session_id 전달 시에만 multi-turn 활성화로 변경 |

### [GAP-2] TC-06 Session ownership test missing

| | Detail |
|---|--------|
| **Design** | Section 9.2 TC-06: "타인 session_id → 빈 히스토리로 새 대화 시작" |
| **Implementation** | 해당 테스트 케이스 없음 |
| **Impact** | Low — 로직은 `find_by_session(user_id)` 필터링으로 암묵적 보장, 테스트만 부재 |
| **Fix** | `find_by_session`이 빈 리스트 반환 시 단일턴 동작 확인 테스트 추가 |

---

## Added Features (Design에 없지만 구현됨)

| Item | Description | Assessment |
|------|-------------|------------|
| `test_no_summarization_within_threshold` | 4턴 대화 시 요약 미발생 확인 | ✅ Good defensive test |
| `test_history_not_loaded_when_no_session_id` | session_id 미전달 시 `find_by_session` 미호출 확인 | ✅ Valuable coverage |

---

## Architecture Compliance (100%)

| Rule | Status |
|------|:------:|
| UseCase → Application Interface (not Infrastructure) | ✅ PASS |
| SummarizationPolicy → Domain layer | ✅ PASS |
| No Infrastructure imports in UseCase | ✅ PASS |
| DI wiring only in main.py | ✅ PASS |

---

## Recommended Actions

1. **[Must Fix] GAP-1**: 메시지 저장 조건 수정 — Option A (조건 제거) 또는 Option B (설계 업데이트) 결정 필요
2. **[Should Fix] GAP-2**: TC-06 세션 소유권 테스트 추가
3. **[Doc Update]**: Design Section 3.2 vs Section 8 모순 해결 (3.2는 403 반환, 8은 새 세션 시작)

---

## Conclusion

**Match Rate: 93%** — 설계와 구현이 전반적으로 잘 일치합니다. 핵심 multi-turn 아키텍처(히스토리 로드/저장, 요약, 세션 관리)가 설계 의도대로 구현되었으며 DDD 레이어 규칙을 준수합니다. 2개 갭(메시지 저장 조건, TC-06 테스트)을 해결하면 100% 일치 달성 가능합니다.
