# agent-run-feedback-wiring Completion Report

> **Status**: Complete (코드 미커밋, 브라우저 실런 일부 미실행)
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 기준 커밋 1baf6d1 (master, PR #83 머지 후)
> **Author**: 배상규 + Claude
> **Completion Date**: 2026-11-03
> **PDCA Cycle**: #1 (Plan → Design → Do → Check 89.7% → Act-1 → 90.9%)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | agent-run-feedback-wiring. 에이전트 실행 답변에 평가(좋아요/싫어요) 버튼 연결 |
| Start Date | 2026-11-02 (Plan·Design·Do·Check) |
| End Date | 2026-11-03 (Act-1, Report) |
| Duration | 약 2일 (달력 기준). 규모 S, Do는 단일 세션 |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────────────┐
│  Match Rate (런타임 포함): 90.9% (목표 90%)            │
│  Match Rate (정적 참고):   97.2%                       │
├──────────────────────────────────────────────────────┤
│  FR 충족:              10 / 10                        │
│  Plan 성공 기준 충족:   6 / 10                         │
│  Plan 성공 기준 부분:   2 / 10                         │
│  Plan 성공 기준 미실행: 1 / 10  (브라우저 히스토리 재진입) │
│  Plan 성공 기준 미측정: 1 / 10  (커버리지)               │
│  Check Important 해소:  1 / 1 (G-I1)                  │
└──────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 답변 완료 이벤트가 저장된 메시지 id를 버려서, 에이전트 채팅 화면은 답변에 평가 버튼을 붙일 수 없었다. 평가 데이터는 General Chat에서만 쌓였다. |
| **Solution** | `_save_assistant_message`가 id를 반환하고, payload 조립을 `_answer_payload` 1곳으로 모았다. 키 `assistant_message_id`를 WS와 REST에 additive로 실었다. 프론트는 훅 필드 1개와 페이지 1줄을 바꿨고, 분기 누락은 AST 계약 테스트가 막는다. |
| **Function/UX Effect** | 4종 턴(정상, 차단, 강등, 승인 대기)이 id를 싣는다. 인프로세스 실런에서 WS로 받은 id 499에 대해 👎+이유 저장(200), 조회(200), 취소(204)가 DB까지 동작했다. persist=False 실행은 키가 없다(REST `/run` id 501 대 null). 브라우저 클릭, 히스토리 재진입, 차단 턴 라이브 확인은 미실행이다. |
| **Core Value** | 새 테이블, 엔드포인트, 컴포넌트 없이 기존 평가·환류 체계를 모든 에이전트로 넓혔다. 마이그레이션 0건, domain·infrastructure 무변경. |

---

## 1.4 Success Criteria Final Status

> Plan §4.1 Definition of Done 7건 + §4.2 Quality Criteria 3건 = 10건.

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | FR-01~FR-10 구현 및 테스트 (TDD) | 충족 | §3.1. FR-10 WS 타입은 Act-1에서 `types/websocket.ts` 필드 추가로 완료 |
| SC-2 | WS 답변 직후 👍/👎, 👎+이유 저장, 재클릭 삭제 | 충족 (인프로세스) | 실 DB 실런 id 499: POST 200, GET 200, DELETE 204, GET rating null. UI 클릭은 `agentFeedback.test.tsx`. 행의 `agent_id` 값은 미검증 |
| SC-3 | prompt-guard 차단 턴에도 평가 버튼 | 부분 | 서버 단위 테스트(`test_prompt_guard_wiring.py`)만. 라이브 WS 실런 미실행 (G-V2) |
| SC-4 | 히스토리 재진입 시 평가 상태 유지 | 미실행 | 숫자 id 폴백 코드만 정적 확인(`MessageBubble.tsx`). 브라우저 확인 미실행 (G-V1) |
| SC-5 | REST `/run` 응답 id, persist=false면 null | 충족 | 실런 id 501 / null. `test_run_agent_feedback_id.py` |
| SC-6 | 전체 회귀 0, verify 스킬 3종 통과 | 부분 | 백엔드 1,491 통과, Vitest 1,519 통과. verify-architecture·logging은 grep 확인만, 스킬 형식 실행 기록 없음 |
| SC-7 | SOT·wiki 어긋남 보고 | 충족 | §4.3. 보고만 하고 수정하지 않음 |
| SC-8 | 신규·수정 코드 커버리지 80% | 미측정 | 측정 기록 없음 |
| SC-9 | ruff·eslint·tsc 신규 오류 0 | 충족 | tsc 209건 = 기준선. ruff 변경 줄 0. 신규 프론트 파일 eslint 0 |
| SC-10 | 마이그레이션 없음 | 충족 | 변경 파일에 migration 없음 |

**Success Rate**: 6/10 met (60%). 부분 2, 미실행 1, 미측정 1. SC-2는 인프로세스 근거이므로 브라우저 확인 후 재판정한다.

## 1.5 Decision Record Summary

> 결정 출처: Plan §7.2, 사용자 결정(Plan 작성 시), Design §12(D-01~D-07), v0.2 정정.

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan §7.2] | id 전달은 ANSWER_COMPLETED additive 키 | 예 | 일반 채팅과 같은 키 이름. 실런에서 WS 키 확인 |
| [Plan §7.2] | 분기 누락 방지는 테스트와 소스 계약 검사 | 예 | AST 계약 테스트(MIN_SITES=3). 사각지대는 G-M5 |
| [Plan §7.2] | None이면 키 생략 | 예 | persist=False에서 키 없음 |
| [사용자] | REST `RunAgentResponse`에도 additive | 예 | 실런 id 501 / null 확인 |
| [사용자] | 차단·강등·승인 대기 턴도 노출 | 예 | 차단·강등은 서버 테스트 확인. 승인 대기는 스트림 테스트 없음 (G-M3) |
| [사용자] | 승인 후 재개 답변은 범위 밖 | 예 | `_resume_graph` 반환값 미사용 |
| [Design D-02] | payload 조립 헬퍼 1곳 | 예 | `_answer_payload` 16줄 |
| [Design D-07] | 프론트는 훅 필드 1개와 페이지 1줄 | 예 (편차 있음) | `websocket.ts` 타입 1줄 추가가 추가로 필요했다. 설계 전제 오류 (G-I1) |

### 1.5.1 Plan·Design 정정 (Check 중 확인)

| Source | Correction | Outcome |
|--------|-----------|---------|
| [Plan v0.2, Design v0.2] | `AgentAnswerCompletedData`에 id 필드가 이미 있다는 전제는 틀렸다. 선언은 일반 채팅 타입 `ChatAnswerCompletedData`에만 있었다 | tsc 신규 오류 2건으로 발견. Act-1에서 필드 추가 |
| [Design v0.2] | §6.1 경고 로그 문구 삭제 (Plan NFR "새 경고 로그 없음"과 일치) | 문서 정정 |
| [Design v0.2] | §8.4 #1 평가 POST 기대값 201을 200으로 정정 | 실런 결과와 일치 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [agent-run-feedback-wiring.plan.md](../01-plan/features/agent-run-feedback-wiring.plan.md) | v0.2 (상태 Draft 유지) |
| Design | [agent-run-feedback-wiring.design.md](../02-design/features/agent-run-feedback-wiring.design.md) | v0.2 |
| Check | [agent-run-feedback-wiring.analysis.md](../03-analysis/agent-run-feedback-wiring.analysis.md) | v0.3 (Match 90.9%) |
| Act | Current document | Complete |

---

## PDCA Cycle Summary

### Plan
- 문서: `docs/01-plan/features/agent-run-feedback-wiring.plan.md` (2026-11-02, v0.2 2026-11-03)
- 목표: 에이전트 실행 답변에도 기존 👍/👎 평가가 동작하게 한다.
- 범위: 백엔드 반환값·payload·REST 필드, 프론트 훅·페이지 연결, 테스트. FR 10건.

### Design
- 문서: `docs/02-design/features/agent-run-feedback-wiring.design.md` (v0.1 2026-11-02, v0.2 2026-11-03)
- 선택: Option C. 공유 헬퍼 `_answer_payload` + AST 계약 테스트.

### Do
- 백엔드: `run_agent_use_case.py`, `schemas.py`
- 프론트: `useAgentRunStream.ts`, `ChatPage/index.tsx`
- 실제 기간: 2026-11-02 단일 세션.

### Check
- 문서: `docs/03-analysis/agent-run-feedback-wiring.analysis.md` (v0.1 → v0.3)
- 1차 (gap-detector): 런타임 포함 89.7%, 정적 95.4%.
- 발견 사항: Critical 0, Important 1 (G-I1), Minor 5 (G-M1~G-M5), 검증 공백 2 (G-V1, G-V2).

### Act
- Act-1 (2026-11-03): G-I1 수정, G-M1 수정, G-M2·G-M4 설계 정정. 재채점 런타임 포함 90.9%, 정적 97.2%. 이터레이션 1회.
- Report (2026-11-03): 본 문서.

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|:------:|-------|
| FR-01 | `_save_assistant_message`가 저장 id를 반환. persist=False면 None | 충족 | `run_agent_use_case.py`. `test_run_agent_feedback_id.py` |
| FR-02 | 정상 완료 payload에 `assistant_message_id` | 충족 | `test_run_agent_use_case_stream.py` (id 42) |
| FR-03 | 차단 분기 payload에 id | 충족 | `test_prompt_guard_wiring.py` |
| FR-04 | 강등 분기 payload에 id | 충족 | `test_agent_iteration_limit.py` |
| FR-05 | 승인 대기 분기 payload에 id | 충족 (정적) | 정상 완료 경로의 `approval_pending` 플래그. 스트림 테스트 없음 (G-M3) |
| FR-06 | REST `RunAgentResponse.assistant_message_id`, `execute()`에서 채움 | 충족 | `schemas.py`. 실런 501 / null |
| FR-07 | 훅 `assistantMessageId` 상태, 부재 시 null | 충족 | `useAgentRunStream.ts`. 훅 테스트 3건 |
| FR-08 | ChatPage 에이전트 뷰가 id를 `feedbackMessageId`로 전달 | 충족 | `ChatPage/index.tsx`. `agentFeedback.test.tsx` 2건 |
| FR-09 | persist=False 실행은 키 없음, 기존 동작 유지 | 충족 | 스트림 테스트. 벤치마크·웹훅 회귀 통과 |
| FR-10 | API 계약 동기화 | 충족 | WS: `types/websocket.ts` 필드 추가(Act-1). REST: 프론트 대응 타입 없음. `types/agent.ts`의 `RunAgentResponse`는 레거시 `{runId}` 계약이라 변경하지 않음 |

**FR 합계: 10 충족.**

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| Compatibility | additive, 회귀 0 | 기존 테스트 무수정 통과 | 충족 |
| Correctness | 4개 분기 id 포함, None이면 키 생략 | 분기 테스트 + AST 계약 | 충족 |
| Architecture | domain 무변경 | application 2파일만 변경. ws_adapter는 패스스루 | 충족 |
| Logging | 새 경고 로그 없음 | 로그 없음 | 충족 |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 백엔드 소스 | `idt/src/application/agent_builder/run_agent_use_case.py`, `schemas.py` | 수정 완료 |
| 백엔드 테스트 | `test_run_agent_feedback_id.py`(신규 8건), `test_answer_payload_contract.py`(신규, AST), 기존 3파일 단언 추가 | 완료 |
| 프론트 소스 | `useAgentRunStream.ts`, `ChatPage/index.tsx`, `types/websocket.ts` | 수정 완료 |
| 프론트 테스트 | `useAgentRunStream.test.ts`(3건 추가), `ChatPage/agentFeedback.test.tsx`(신규 2건) | 완료 |
| 문서 | Plan v0.2, Design v0.2, Analysis v0.3, 본 Report | 완료 |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| 브라우저 히스토리 재진입 확인 (G-V1, SC-4) | 브라우저 실런 미실행 | High | 실런 1회 |
| 차단 턴 WS 라이브 실런 (G-V2, SC-3) | 단위 테스트만 수행 | Medium | 실런 1회 |
| 커버리지 80% 측정 (SC-8) | 측정 기록 없음 | Medium | 소량 |
| verify 스킬 3종 형식 실행 (SC-6) | Do 중 grep 확인만 함 | Medium | 소량 |
| 코드 커밋·PR | 사용자 지시 대기. 이 기능 파일만 분리해 커밋 | High | — |

### 4.2 Minor Gaps (Analysis §9, 미해결)

| ID | 내용 | Priority |
|----|------|----------|
| G-M3 | 승인 대기 스트림 테스트와 강등 분기 persist=False 테스트가 없다. 헬퍼 단위 테스트와 AST가 대신 막는다 | Low |
| G-M5 | AST 계약의 사각지대. 이벤트 타입을 변수로 넘기면 탐지되지 않고, 헬퍼 결과 이름을 재대입해도 통과한다 | Low |

Act-1에서 해소: G-I1(코드), G-M1(코드 1줄), G-M2·G-M4(설계 정정).

### 4.3 SOT·wiki 어긋남 (보고만, 수정하지 않음)

| 문서 | 위치 | 어긋남 |
|------|------|--------|
| `docs/wiki/backend/db/erd-conversation-eval.md` | 각주 | "에이전트 경로는 id를 노출하지 않는다"는 취지의 서술이 남아 있다 |
| `docs/SOURCE-OF-TRUTH.md` | WS payload 표 | `assistant_message_id` 키가 없다 |
| `streaming-message-action-id` 패턴 문서 | 적용 범위 | 일반 채팅 전용으로 적혀 있으면 에이전트 경로 추가 필요 (미확인) |

위키 갱신은 `/wiki update` 명시 호출 때만 한다.

---

## 5. Quality Metrics

### 5.1 Match Rate 변화

| Metric | Check 1차 (gap-detector) | Act-1 후 (재채점) | Target |
|--------|:-----:|:-----:|:-----:|
| Structural | 95 | 100 | — |
| Functional | 95 | 95 | — |
| API Contract | 96 | 98 | — |
| Runtime | 79 | 79 (새 실런 없음) | — |
| **Overall (런타임 포함)** | 89.7 | **90.9** | 90 |
| Overall (정적 참고) | 95.4 | 97.2 | — |
| Critical 결함 | 0 | 0 | 0 |
| Important 결함 | 1 | 0 | 0 |

산식: 런타임 포함 = Structural×0.15 + Functional×0.25 + Contract×0.25 + Runtime×0.35. Act-1 값은 100×0.15 + 95×0.25 + 98×0.25 + 79×0.35 = 90.9. Runtime 79는 Do 실런 근거를 그대로 쓴 값이다. Act-1에서 새 실런은 하지 않았다.

### 5.2 Regression 기록

| 영역 | 결과 | 판정 |
|------|------|------|
| 백엔드 agent_builder + agent_run + WS/builder 라우터 (Do 시점) | 1,491 passed | 통과 |
| 프론트 Vitest 전체 (Do 시점) | 1,519 passed. 상시 실패 4파일 제외, 로드 플레이크 13파일은 단독 실행 통과 | 기준선 동일 |
| Act-1 후 재실행 | 백엔드 관련 4파일 69 passed, 프론트 훅·ChatPage 21 passed, tsc 209 | 통과 (전체 스위트 재실행은 미수행) |
| tsc | 209 (Act-1 후) | 기준선 동일. Act-1 전 211에서 복귀 |
| ruff | 변경 줄 0 (파일 내 기존 UP045·UP017 2건) | 충족 |
| eslint | 신규 파일 0 (훅 테스트 파일의 기존 `any` 4건) | 충족 |

### 5.3 Gap Resolution (Act-1, 2026-11-03)

| Gap | 문제 | 수정 | 결과 |
|-----|------|------|------|
| G-I1 | `AgentAnswerCompletedData`에 id 필드가 없어 tsc 오류 2건 (211 vs 기준선 209) | `assistant_message_id?: number` 1줄 추가 | tsc 209 복귀 |
| G-M1 | `execute()`가 id 변수를 초기화하지 않아 향후 분기에서 UnboundLocalError 위험 | `assistant_message_id: int \| None = None` 초기화 | 코드 1줄. 전용 테스트 없음 |
| G-M2 | 설계 §6.1 경고 로그 문구가 Plan NFR과 충돌 | 설계 v0.2에서 문구 삭제 | 문서 정정 |
| G-M4 | 설계 §8.4 #1 POST 기대값 201 (실제 200) | 설계 v0.2 정정 | 문서 정정 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- 공유 헬퍼 1곳과 AST 계약 테스트로 4개 분기를 같은 조립 경로에 묶었다. 현재 누락은 없지만 분기가 추가되어도 테스트가 막는다.
- 인프로세스 실런(TestClient + 실 DB)으로 WS 이벤트에서 평가 저장과 취소까지 한 번에 확인했다. 단위 테스트가 놓치는 키 흐름을 잡았다.
- 일반 채팅과 같은 키 이름을 써서 페이지 변경을 1줄로 줄였다.
- 규모 S에서는 gap-detector가 낸 분석 문서를 메인 세션이 저장하는 방식으로 충분했다.

### 6.2 What Needs Improvement (Problem)

- 설계 전제 "프론트 타입에 이미 선언돼 있다"를 파일을 열어 확인하지 않았다. Check에서 tsc 신규 오류 2건으로 발견했다.
- Vitest는 타입을 검사하지 않는다. 훅 테스트가 모두 통과해도 tsc 오류가 남았다.
- Act-1 후 전체 스위트는 재실행하지 않고 관련 파일만 돌렸다.

### 6.3 What to Try Next (Try)

- 설계가 "기존 코드가 X를 가진다"고 적은 항목은 작성 전에 파일을 열어 `파일:줄`을 기록한다.
- Do의 DoD에 tsc 실행을 넣는다. Vitest 통과만으로 완료 처리하지 않는다.
- 수정 후에는 영향 범위 테스트를 다시 돌리고 Act 기록에 남긴다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 기존 타입 재사용을 가정함 | 재사용 가정은 파일 확인 항목으로 Plan에 넣는다 |
| Design | 정정 시 관련 문장이 일부 남음 | 정정 후 전제 용어를 grep해 본문을 한 번에 고친다 |
| Do | tsc 실행이 DoD에 없었음 | DoD에 tsc 신규 0을 넣는다 |
| Check | 브라우저 항목이 미실행으로 남음 | Plan DoD에 "미실행 시 사유" 칸을 둔다 |

### 7.2 Tools/Environment

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| Testing | 이벤트 계약은 AST 계약과 인프로세스 실런을 함께 쓴다 | 키 누락과 계약 드리프트를 Check 전에 발견 |
| Git | 무관한 미커밋 변경이 많은 워크트리에서는 파일 단위로 커밋한다 | 다른 기능과 섞이는 것을 막음 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 브라우저 히스토리 재진입 확인 (G-V1): 에이전트 답변에 👎, 세션 이동, 재진입 후 상태 확인
- [ ] 차단 문구로 WS 라이브 실런 (G-V2)
- [ ] 커밋·PR (사용자 지시 시): 이 기능 파일만 분리해 커밋
- [ ] `/wiki update` 호출 시 §4.3 어긋남 3건 반영
- [ ] `/pdca archive agent-run-feedback-wiring` (커밋 후)

### 8.2 Follow-up (Minor)

| Item | Gap | Priority |
|------|-----|----------|
| 승인 대기 스트림 테스트, 강등 분기 persist=False 테스트 추가 | G-M3 | Low |
| AST 계약 사각지대 보완 | G-M5 | Low |
| 커버리지 80% 측정 | SC-8 | Medium |

### 8.3 Next PDCA Cycle

| Item | Priority | Note |
|------|----------|------|
| 승인 후 재개 답변의 평가 | Medium | 승인함 UI 변경이 필요해 별도 사이클 (Plan §2.2) |
| 과거 turn_index 중복 행 데이터 보정 | Low | #1 범위에서 리넘버링하지 않기로 결정 |

---

## 9. Changelog

### v1.0.0 (2026-11-03)

**Added:**
- 에이전트 WS `agent_answer_completed`와 REST `RunAgentResponse`에 `assistant_message_id` (additive, 없으면 생략)
- `_answer_payload` 헬퍼와 AST 계약 테스트

**Changed:**
- `_save_assistant_message`가 저장 id를 반환
- `useAgentRunStream`에 `assistantMessageId` 상태 추가
- `ChatPage` 에이전트 뷰가 id를 평가 버튼에 전달
- `types/websocket.ts` `AgentAnswerCompletedData`에 필드 추가

**Fixed (Act-1):**
- `execute()` 의 id 변수 미초기화 (G-M1)
- 에이전트 이벤트 타입 누락으로 생긴 tsc 신규 오류 2건 (G-I1)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-03 | Completion report (Match 90.9%, 브라우저 실런 미실행) | 배상규 + Claude |
