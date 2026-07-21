# agent-eval-gate — Design vs Implementation Gap Analysis

> **Feature**: agent-eval-gate
> **Design**: `docs/02-design/features/agent-eval-gate.design.md`
> **Date**: 2026-07-20
> **Phase**: Check (Gap Analysis)

---

## Match Rate: **97%** — Critical 0 · Major 0 · Minor 5 (38 design items)

```
✅ Match:            33 items (87%)
⚠️ Partial/Added:     4 items (10%)
🔵 Changed(의도):     1 item  (3%)
❌ Not implemented:   0 items (0%)
```

Architecture Compliance **100%** · Convention **~98%**

---

## Gap Summary Table

| # | 항목 | 유형 | 심각도 | 설계 | 구현 |
|---|------|------|--------|------|------|
| G1 | 피드백 반영 방식 | 🔵 Changed(의도) | Minor | 낙관적 업데이트 + 실패 롤백 (FR-06) | 서버 왕복 후 `setQueryData` 캐시 갱신, `isPending` disabled로 중복 방지 (`MessageFeedback.tsx:15` 주석에 대체 명시) |
| G2 | ANSWER_COMPLETED `assistant_message_id` 명시 테스트 | ⚠️ Partial | Minor | payload 노출 검증 | 튜플 반환만 간접 검증(`test_memory_injection.py:181` mock `(1,2)`), payload assert 없음 → **본 Check에서 보강 완료** |
| G3 | UC 테스트 파일 구성 | ⚠️ 상이 | Minor | `test_submit_feedback.py`+`test_agent_eval_stats.py` | `test_use_cases.py` 단일 파일 병합(케이스 동일) |
| G4 | `DeleteFeedbackUseCase` | 🟡 Added | Minor | §3-3 UC 목록 미열거 | 구현됨 — §3-4 DELETE 엔드포인트와 정합 |
| G5 | 취소 토글 comment 가드 | 🟡 Added | Minor | "같은 rating 재클릭 시 삭제" | `comment is None`일 때만 취소, 코멘트 동반 시 갱신(additive) |

**Missing Features (Design O / Impl X): 없음** — 설계 필수 요소 전부 구현.

---

## 항목별 매핑 (요약)

- **결정 4건 (§1)**: ① message_id 키 ② 취소=삭제 토글 ③ 신규 eval 라우터 ④ ANSWER_COMPLETED additive — 전부 ✅ (④는 chart-edit 경로까지 커버)
- **DB V052 (§3-1)**: SQL + SQLAlchemy 모델(sqlite variant) 컬럼·UNIQUE·INDEX·InnoDB 완전 일치 ✅
- **Domain (§3-2)**: Rating / MessageFeedback / EvalPolicy(COMMENT_MAX·validate_comment·satisfaction 0건 None) / Repo interface 5메서드 ✅, 외부 의존 0
- **Application (§3-3)**: Submit/Get/AgentEvalStats UC + api_schemas ✅, DeleteFeedbackUseCase 추가(G4)
- **Interfaces (§3-4)**: feedback 3종(401 / 404 은닉 / 422) + admin 2종(require_role), config `eval_recent_negative_limit=20`, main DI 배선 + include_router ✅
- **general_chat 통합**: `_persist_messages` → `(user_message_id, assistant_message_id)` 튜플 + `_message_id_of` 안전 추출(실패 None, FR-07), 스트림 payload 2곳 ✅
- **Frontend 계약**: endpoints·queryKeys·types(messageFeedback / chat.feedbackMessageId / websocket.assistant_message_id)·service·hooks 4종·useChatStream ✅
- **Frontend UI**: MessageBubble feedbackId 결정 로직, ChatPage assistantMessageId→feedbackMessageId, AdminDashboard AgentSatisfactionPanel(만족도 % + 최근 부정) ✅
- **Test Plan (§4)**: policies·repository·use_cases·eval_router·MessageFeedback.test·AgentSatisfactionPanel.test 존재 ✅

---

## 의도적 스코프 외 (Gap 아님)

- E2E 수동 검증 (Qdrant/ES 기동 시 일괄)
- V052 마이그레이션 배포
- agent(비 general-chat) 경로 평가 연동 (`ChatPage:165` "후속" 명시, `assistantMessageId: null`)
- 대화 메모리 정책 무관

---

## Clean Architecture / Convention

CLAUDE.md 금지 규칙 위반 0 — domain 순수, repository `flush()`만(commit 없음, SearchHistory 경량 패턴), 라우터 비즈니스 로직 없음, FE presentation→hook→service 계층 준수. queryKey 팩토리·엔드포인트 상수화·BE↔FE 계약 동기화(up/down·satisfaction null·message_id) 일치.

---

## 권장 조치

| # | 조치 | 상태 |
|---|------|------|
| 1 | ANSWER_COMPLETED payload `assistant_message_id` 명시 검증 테스트 추가 (G2) | ✅ 본 Check에서 완료 |
| 2 | design.md §3-3 UC 목록에 `DeleteFeedbackUseCase` 추가 (G4) | 문서 정합(선택) |
| 3 | design.md §3-5/FR-06 낙관적+롤백 → 서버 왕복 캐시 갱신 반영 (G1) | 문서 정합(선택) |
| 4 | design.md §4 Test Plan 파일명 `test_use_cases.py` 단일로 갱신 (G3) | 문서 정합(선택) |
| 5 | design.md §1 결정 ② 취소 조건에 `comment is None` 가드 반영 (G5) | 문서 정합(선택) |

---

## 결론

**Match 97% ≥ 90% → `/pdca report agent-eval-gate` 진행 가능.**
Critical/Major gap 없음, 미구현 항목 없음. 잔여는 전부 Minor(문서-구현 문구 정합 4건). G2 테스트 보강은 본 Check 단계에서 완료.
