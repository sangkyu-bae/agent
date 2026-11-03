# agent-run-feedback-wiring Gap Analysis

> **Summary**: 설계(Design v0.1, Option C)와 구현(idt + idt_front)을 정적으로 대조하고, Do 단계 인프로세스 실런 결과를 런타임 축에 반영했다. 백엔드는 설계와 일치한다. `_save_assistant_message` 가 id 를 반환하고, ANSWER_COMPLETED payload 는 헬퍼 `_answer_payload` 1곳에서 만들며 호출부 3곳(정상+승인 대기, 차단, 강등)이 이를 쓴다. `execute()` 와 `RunAgentResponse` 도 설계대로이고, AST 계약 테스트가 분기 누락을 막는다. 프론트 훅·페이지 연결도 설계대로 동작한다. Important 1건: Plan·Design 은 `AgentAnswerCompletedData` 에 `assistant_message_id` 가 이미 선언돼 있다고 봤지만, 실제로는 일반 채팅 타입 `ChatAnswerCompletedData` 에만 있다. 메인 세션이 tsc 로 확인한 결과 **신규 오류 2건(기준선 209 → 211)** 이다. 런타임 포함 공식 **89.7%**, 정적 공식 **95.4%**.
>
> **Act-1 (2026-11-03)**: G-I1 — `AgentAnswerCompletedData.assistant_message_id?: number` 추가 → tsc 209(기준선 복귀). G-M1 — `execute()` 에 `assistant_message_id: int | None = None` 초기화. 설계 v0.2(§2.3·§5.3·§6.1·§8.4 #1)·Plan v0.2(§1.2·FR-10) 정정. 재채점: Structural 100 · Functional 95 · Contract 98 · Runtime 79 → **런타임 포함 90.9%** (15.0 + 23.75 + 24.5 + 27.65), 정적 97.2%. 남은 검증 공백 G-V1(브라우저 히스토리 재진입)·G-V2(차단 턴 라이브)는 사용자 확인 항목.
>
> **Author**: gap-detector (bkit) 초안 + 메인 세션 tsc 확인
> **Created**: 2026-11-02
> **Status**: Draft
> **Plan**: [agent-run-feedback-wiring.plan.md](../01-plan/features/agent-run-feedback-wiring.plan.md)
> **Design**: [agent-run-feedback-wiring.design.md](../02-design/features/agent-run-feedback-wiring.design.md) (v0.1, Option C)
> **PRD**: 없음

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 경로 답변에 평가 버튼이 없어 환류 데이터가 General Chat 에만 쌓인다. 저장 id 가 이벤트에 실리지 않는 것이 유일한 끊긴 고리다. |
| **WHO** | P1 심사역·P4 일반 행원(배포 에이전트 이용자) — 👎 + 이유를 남기는 사람. P2 에이전트 소유자 — 그 데이터로 메모리·위키를 다듬는 사람. |
| **RISK** | ANSWER_COMPLETED 를 만드는 분기가 4곳(정상·차단·강등·승인 대기)이라 한 곳이라도 빠지면 그 턴만 조용히 평가가 안 보인다. 선행 결함(turn_index 중복)은 #1 로 해소됐지만 과거 중복 행은 남아 있다. |
| **SUCCESS** | 에이전트 채팅에서 답변 완료 직후 👍/👎 가 보이고 클릭이 `message_feedback` 에 그 메시지 id 로 저장된다. 4개 분기 모두 id 포함. persist=False 실행은 필드 없음. 기존 pytest/Vitest 회귀 0. |
| **SCOPE** | 백엔드 UseCase 반환값·payload 2종(WS 이벤트, REST 응답) additive 필드, 프론트 훅·페이지 연결, 테스트. 승인 후 재개 답변의 평가, 평가 UI 변경, 환류 로직 변경은 제외. |

---

## 1. 분석 개요

| 항목 | 값 |
|------|----|
| 분석 대상 | agent-run-feedback-wiring (규모 S) |
| 설계 문서 | `idt/docs/02-design/features/agent-run-feedback-wiring.design.md` (v0.1) |
| 구현 경로 | `idt/src/application/agent_builder/{run_agent_use_case.py,schemas.py}`, `idt/tests/application/agent_builder/*`, `idt_front/src/{hooks/useAgentRunStream.ts,pages/ChatPage/index.tsx,types/websocket.ts}` |
| 분석 방식 | 정적 분석(Read/Grep). 본문을 읽은 범위: UseCase 해당 구간(L168-180, L320-558, L600-700, L1685-1751), 스키마 L285-301, 신규 테스트 2파일 전문, 기존 테스트 3파일 단언부, 훅·페이지·타입·MessageBubble 해당 구간 |
| 런타임 근거 | Do 단계 인프로세스 TestClient 실런(실 DB) 결과 |
| Do 단계 회귀 기록 | 백엔드 신규·확장 테스트 전부 통과. agent_builder + agent_run + WS/builder 라우터 회귀 1,491 통과. 프론트 신규 5건(훅 3, ChatPage 2) 통과. Vitest 전체 1,519 통과, 상시 실패 4파일과 로드 플레이크(단독 재실행 통과) 외 실패 0. ruff 변경 줄 0(파일 내 기존 UP045/UP017 2건). 신규 프론트 파일 eslint 0(훅 테스트 파일 기존 `any` 4건). **tsc: 메인 세션 확인 211건 = 기준선 209 + 신규 2건(G-I1)** |

---

## 2. Strategic Alignment

| 질문 | 판정 | 근거 |
|------|:----:|------|
| WHY(저장 id 를 버려서 끊긴 고리)를 해결하는가 | 충족 | `_save_assistant_message` → `int \| None` 반환(run_agent_use_case.py:1703, 1733-1734). 정상 완료 L431-454, 차단 L628-636, 강등 L684-694 에서 payload 에 실음. 런타임 WS 이벤트 키 `['answer','assistant_message_id','tools_used']`, id=499 |
| 이미 있는 평가 체계 재사용(새 테이블·엔드포인트·컴포넌트 0) | 충족 | 마이그레이션 없음. `MessageBubble.feedbackId()`(MessageBubble.tsx:84-87)와 `MessageFeedback`(L72-73)을 그대로 씀. 평가 API 런타임 POST 200 → GET 200 → DELETE 204 |
| additive 전용(기존 소비자 회귀 0) | 충족 | 키 생략 규칙(L1746-1750). REST 필드 기본 None(schemas.py:300). 회귀 1,491 / Vitest 통과 |
| 일반화 우선 | 충족 | 일반 채팅과 같은 키 이름 `assistant_message_id`. 특정 에이전트용 분기 없음 |
| Thin DDD (domain·infrastructure 무변경) | 충족 | 변경은 application 2파일. `ws_adapter.py:23` 은 패스스루 매핑만 있고 변경 없음 |
| 주요 설계 결정 준수 | 충족(문서 전제 1건 오류) | §8 D-01~D-07. D-01/D-07 의 "프론트 타입 기존 선언 재사용" 전제가 틀림(G-I1) |

전략적 불일치(Critical)는 없다.

---

## 3. 점수

### 3.1 축별 점수

| 축 | 점수 | 상태 | 근거 요약 |
|----|:----:|:----:|-----------|
| Structural | 95% | 양호 | 설계 §11.1의 백엔드 src 2, 테스트 5, 프론트 4 파일이 모두 있다. 조건부 `types/agent.ts` 는 대응 타입이 아니라서 추가하지 않았고 판단은 타당하다. 감점: 설계가 "무변경"이라 한 `types/websocket.ts` 는 실제로 수정이 필요했다(G-I1) |
| Functional | 95% | 양호 | 백엔드 로직 97%(`execute()` 변수 미초기화 G-M1, 일부 분기 테스트 부재 G-M3). §5.4 UI 체크리스트 92.5% |
| API Contract | 96% | 양호 | 8개 계약 중 PASS 6, PARTIAL 2(WS 타입 선언 누락 0.85, 승인 대기 스트림 테스트 부재 0.9). 문서 정정 1(평가 POST 201→200 0.95) |
| Runtime | 79% | 주의 | §8.4 시나리오 5건 중 실행 2, 대체 근거 2, 미실행 1 → 65%. 자동 회귀 100%. 0.6×65 + 0.4×100 |

### 3.2 Match Rate

**런타임 포함 공식 (주 지표)**
```
Overall = Structural×0.15 + Functional×0.25 + Contract×0.25 + Runtime×0.35
        = 95×0.15 + 95×0.25 + 96×0.25 + 79×0.35
        = 14.25 + 23.75 + 24.00 + 27.65 = 89.65
```

**정적 공식 (참고)**
```
Overall = Structural×0.2 + Functional×0.4 + Contract×0.4
        = 95×0.2 + 95×0.4 + 96×0.4
        = 19.0 + 38.0 + 38.4 = 95.4
```

**Overall Match Rate: 89.7%** (런타임 포함). 목표 90%에 0.3%p 모자란다. 원인은 두 가지다. (1) 브라우저 히스토리 재진입과 차단 턴 라이브 실런을 하지 않아 Runtime 축이 낮다. (2) WS 타입 선언이 누락됐다(G-I1).
- G-I1 만 고쳐도 Contract 98.1, Structural 100 → 15.0 + 23.75 + 24.53 + 27.65 = **90.9%**
- 여기에 브라우저 히스토리 재진입(G-V1)까지 통과하면 Runtime 91 → 약 **95%**

---

## 4. Plan 성공 기준

### 4.1 Definition of Done (Plan §4.1)

| 기준 | 판정 | 근거 |
|------|:----:|------|
| FR-01~FR-10 구현 및 테스트 통과(TDD) | 부분 | §4.3 FR 표. FR-10 의 WS 타입 재사용 전제가 틀림(G-I1). 나머지 FR 은 테스트로 충족 |
| 실런: WS 답변 직후 👍/👎 → 👎+이유 → `message_feedback` 행 생성, 재클릭 시 삭제 | 충족(인프로세스) | WS run → id=499 → POST down+comment 200 → GET 200 → DELETE 204 → GET rating null. UI 클릭 경로는 Vitest(agentFeedback.test.tsx:102-110)로만 확인. 행의 `agent_id` 값은 **unverified** |
| 실런: prompt-guard 차단 턴에도 평가 버튼 | 부분 | 서버: test_prompt_guard_wiring.py:166-169 (`guard_blocked`+id 42). 프론트 경로는 정상 턴과 같다. 라이브 실런은 미실행(G-V2) |
| 실런: 히스토리 재진입 시 평가 상태 유지 | 미실행 | 정적으로는 `feedbackId()` 의 숫자 id 폴백(MessageBubble.tsx:86)이 있다. 히스토리 메시지 id 가 숫자 문자열인지는 **unverified**(G-V1) |
| REST `/run` 응답에 `assistant_message_id`, `persist_conversation=false` 면 null | 충족 | schemas.py:300, run_agent_use_case.py:542, 557. 실런 id=501 / null. 단위 test_run_agent_feedback_id.py:98-107 |
| 전체 pytest/Vitest 회귀 0, verify 스킬 3종 | 부분 | 회귀 충족. verify-architecture/logging 은 Do 단계에서 grep 확인(domain 무변경·print 없음), verify-tdd 는 신규 모듈 없음 → 형식 실행은 미기록 |
| SOT·wiki 어긋남 보고 | 충족 | Do 보고: `erd-conversation-eval.md` "에이전트 경로 미노출" 각주, `SOURCE-OF-TRUTH.md` WS payload 표 |

### 4.2 Quality Criteria (Plan §4.2)

| 기준 | 판정 | 근거 |
|------|:----:|------|
| 신규·수정 코드 커버리지 80% | 미측정 | 분기별 테스트는 있다(§5.2) |
| ruff·eslint 신규 0 | 충족 | Do 보고값 |
| tsc 신규 0 | **미충족** | `useAgentRunStream.ts:150` TS2339 ×2 (기준선 209 → 211). G-I1 |
| 마이그레이션 없음 | 충족 | 변경 파일에 migration 없음 |

### 4.3 FR 상태 요약

| FR | 판정 | 근거 |
|----|:----:|------|
| FR-01 | 충족 | run_agent_use_case.py:1703 `-> int \| None`, L1714-1715 persist=False → None, L1733-1734 `_saved_message_id(saved)`. 헬퍼 L173-179(`id.value` 가 int 일 때만). 테스트 test_run_agent_feedback_id.py:48-73 |
| FR-02 | 충족 | L431-436 저장 → L447-454 `_answer_payload(answer, tools_used, message_id, ...)`. 테스트 test_run_agent_use_case_stream.py:237-238 (id 42) |
| FR-03 | 충족 | L628-636 `_answer_payload(BLOCK_NOTICE_KO, [], message_id, guard_blocked=True)`. 테스트 test_prompt_guard_wiring.py:167-169 |
| FR-04 | 충족 | L684-694 `limit_reached=True`. 테스트 test_agent_iteration_limit.py:363-365 |
| FR-05 | 충족(정적) | 정상 완료 payload 에 `approval_pending=bool(approval_id), approval_id=approval_id`(L449). 별도 분기는 없다. 스트림 하네스 테스트는 없고 test_run_agent_feedback_id.py:37-45 + AST 계약으로 커버(G-M3) |
| FR-06 | 충족 | schemas.py:298-300, execute L542·L557. 테스트 L98-107. 실런 501/null |
| FR-07 | 충족(타입 결함) | useAgentRunStream.ts:39, 64, 143-151. 테스트 useAgentRunStream.test.ts:131-165. 타입 선언 누락(G-I1) |
| FR-08 | 충족 | ChatPage/index.tsx:266-268 `assistantMessageId: agentRun.assistantMessageId`, L337 `feedbackMessageId: view.assistantMessageId ?? undefined`. 테스트 agentFeedback.test.tsx:101-121 |
| FR-09 | 충족 | persist=False → None → 키 생략(L1714-1715, L1746). 테스트 test_run_agent_use_case_stream.py:241-256. 벤치마크·웹훅·스케줄은 회귀 스위트 통과 |
| FR-10 | 부분 | REST: 프론트 `types/agent.ts:97-99` `RunAgentResponse { runId }` 는 `agentService.ts:8` `API_ENDPOINTS.AGENT_RUN` 레거시 계약이다. "대응 타입 없음" 판단이 타당하다. WS: "websocket.ts 기존 선언 재사용" 전제가 틀림(G-I1) |

---

## 5. Structural 대조 (설계 §11.1)

### 5.1 백엔드 src

| 설계 파일 | 구현 | 비고 |
|-----------|:----:|------|
| run_agent_use_case.py — `_save_assistant_message` 반환 | 있음 | L1693-1734. 설계 §4.3의 `saved.id` 대신 `_saved_message_id`(L173-179)로 VO `.value` 와 int 여부를 확인한다. 동등 이상 |
| run_agent_use_case.py — `_answer_payload` | 있음 | L1736-1751 staticmethod. 설계 시그니처와 동일 |
| run_agent_use_case.py — 호출 3곳 | 있음 | L447-454, L633-636, L691-694. 설계 참조 주석 L445, L632, L690 |
| run_agent_use_case.py — `execute()` | 있음 | L538-542, L557 |
| 재개 경로 반환값 미사용 | 있음 | L1160 반환값 무시(D-06) |
| schemas.py — `RunAgentResponse.assistant_message_id` | 있음 | L298-300 |

`AgentRunEventType.ANSWER_COMPLETED` 를 만드는 곳은 src 전체에서 run_agent_use_case.py 3곳뿐이다. infrastructure 는 매핑(ws_adapter.py:23)만 한다.

### 5.2 백엔드 테스트

| 설계 §8.2 | 구현 | 비고 |
|-----------|:----:|------|
| #1~#3 `_answer_payload` | 있음 | test_run_agent_feedback_id.py:25-45 |
| #4~#5 `_save_assistant_message` | 있음 | L48-64. 추가로 L66-73(MagicMock·None → None) |
| #6 정상 완료 스트림 | 있음 | test_run_agent_use_case_stream.py:237-238 |
| #7 차단 | 있음 | test_prompt_guard_wiring.py:168-169 |
| #8 강등 | 있음 | test_agent_iteration_limit.py:364-365 |
| #9 승인 대기 | 부분 | 스트림 하네스 테스트 없음. 헬퍼 단위(L37-45) + AST |
| #10 persist=False | 부분 | 정상 분기만(test_run_agent_use_case_stream.py:241-256). 강등 분기 persist=False 테스트 없음 |
| #11 `execute()` | 있음 | test_run_agent_feedback_id.py:76-107 |
| #12 AST 계약 | 있음 | test_answer_payload_contract.py. `MIN_SITES = 3`(L17), 위반 시 줄 번호 출력 |
| #13 기존 회귀 | 있음 | 1,491 통과 |

### 5.3 프론트

| 설계 | 구현 | 비고 |
|------|:----:|------|
| hooks/useAgentRunStream.ts (M) | 있음 | 상태 필드 L37-39, INITIAL_STATE L64, 수신 L143-151. 설계의 `?? null` 대신 `typeof === 'number'` 판정. 더 엄격하다 |
| hooks/useAgentRunStream.test.ts (M) | 있음 | describe 'assistantMessageId' L131-165 |
| pages/ChatPage/index.tsx (M) | 있음 | L266-268. "후속" 주석 제거 확인 |
| pages/ChatPage/agentFeedback.test.tsx (N) | 있음 | 2건(L102, L112) |
| types/agent.ts (M, 조건부) | 미추가(타당) | 레거시 `{ runId }` 계약(types/agent.ts:97-99, agentService.ts:3-8) |
| types/websocket.ts (무변경) | **수정 필요했음** | `AgentAnswerCompletedData`(L62-70)에 필드 없음. 기존 선언은 `ChatAnswerCompletedData`(L145-160, 필드 L159)에만 있다(G-I1) |
| MessageBubble / MessageFeedback / useMessageFeedback (무변경) | 무변경 | `feedbackId()` L84-87, 렌더 조건 L72-73 |

Structural = 95% (websocket.ts 누락 감점)

---

## 6. Functional 대조

### 6.1 §5.4 Page UI Checklist

채점 기준: UI 테스트나 런타임으로 확인 = 1.0, 코드 경로 + 백엔드 단위 테스트 = 0.9, 코드 경로 + 헬퍼 단위만 = 0.85, 미확인 = 0.75

| # | 항목 | 점수 | 근거 |
|---|------|:----:|------|
| 1 | 답변 완료 직후 👍/👎, 스트리밍 중 미노출 | 1.0 | agentFeedback.test.tsx:102-110. `!message.isStreaming` 조건(MessageBubble.tsx:72) |
| 2 | 👎 → 이유 → 전송 → 행 생성, 재클릭 취소 | 1.0 | 컴포넌트 무변경. 런타임 POST 200 / DELETE 204 |
| 3 | 차단 턴 노출 | 0.9 | test_prompt_guard_wiring.py:169. 프론트는 같은 경로 |
| 4 | 강등 답변 노출 | 0.9 | test_agent_iteration_limit.py:365 |
| 5 | 승인 대기 안내 노출 | 0.85 | L449 플래그 + 헬퍼 단위 테스트. 스트림 테스트 없음 |
| 6 | id 없는 응답이면 미노출, 오류 없음 | 1.0 | agentFeedback.test.tsx:112-121, useAgentRunStream.test.ts:144-150 |
| 7 | 히스토리 재진입 시 평가 상태 유지 | 0.75 | 폴백(MessageBubble.tsx:86)만 정적 확인. 실런 없음(G-V1) |
| 8 | 일반 채팅 평가 동작 변화 없음 | 1.0 | 채팅 뷰 `assistantMessageId: chatStream.assistantMessageId`(index.tsx:253) 무변경 |

UI 체크리스트 = 7.4 / 8 = **92.5%**

### 6.2 백엔드 로직 완결성

| 영역 | 판정 | 근거 |
|------|:----:|------|
| persist=False → 저장 0, None | 충족 | L1714-1715 |
| id 미발급·비정수 → 키 생략 | 충족 | L173-179, L1746 |
| 플래그는 truthy 일 때만 | 충족 | L1748-1750. `approval_pending=bool(approval_id)` 로 기존 의미 유지(L449) |
| 3개 생성 지점 모두 헬퍼 경유 | 충족 | AST 계약 + 코드 판독 |
| `execute()` 가 id 를 응답에 싣음 | 충족(결함 1) | L542, L557. 변수 미초기화(G-M1) |
| 저장 실패는 기존대로 전파 | 충족 | `_persist_message` 예외 처리 변경 없음 |
| 함수 40줄 규칙 | 충족 | `_answer_payload` 16줄 |
| 플레이스홀더·TODO | 없음 | |

백엔드 로직 ≈ **97%**. Functional = (92.5 + 97) / 2 ≈ **95%**

---

## 7. API Contract 3-way 대조

| # | 계약 | Design | Server | Client | 판정 |
|---|------|:------:|:------:|:------:|:----:|
| 1 | WS `agent_answer_completed.assistant_message_id`(정상 완료) | §3.4, §4.2 | L447-454. 런타임 키 확인(id=499) | 훅 L149-150 → 상태 → ChatPage L268 → L337. **타입 선언 없음**(websocket.ts:62-70) | PARTIAL 0.85 |
| 2 | 차단 턴 `guard_blocked` + id | §4.2 | L633-636, 테스트 | 정상과 같은 경로 | PASS 1.0 |
| 3 | 강등 `limit_reached` + id | §4.2 | L691-694, 테스트 | 같은 경로 | PASS 1.0 |
| 4 | 승인 대기 `approval_pending/approval_id` + id | §4.2 | L447-451(단위·AST만) | 같은 경로 | PARTIAL 0.9 |
| 5 | persist=False 면 키 없음 | §3.4, §4.2 | L1714-1715, 테스트 L241-256 | 훅이 null 유지(테스트 L144-150) | PASS 1.0 |
| 6 | REST `RunAgentResponse.assistant_message_id: int \| None` | §3.4, §4.2 | schemas.py:300, execute L557. 실런 501 / null | 프론트 대응 타입 없음(레거시 `{runId}`). FR-10 기록 | PASS 1.0 |
| 7 | 평가 API POST/GET/DELETE 무변경 | §4.1, §8.4 #1 | 런타임 POST **200** / GET 200 / DELETE 204 | `MessageFeedback` 무변경 | PASS 0.95 (설계 §8.4 #1 의 "201"은 실제 200 → 문서 정정, G-M4) |
| 8 | `feedbackMessageId` → `feedbackId()` → `MessageFeedback messageId` | §2.1, D-07 | — | index.tsx:337, MessageBubble.tsx:72-73, 84-87 | PASS 1.0 |

Contract = 7.70 / 8 = **96%**

---

## 8. 설계 결정 D-01~D-07 준수

| ID | 결정 | 판정 | 근거 |
|----|------|:----:|------|
| D-01 | ANSWER_COMPLETED additive 키 `assistant_message_id` | 준수(근거 일부 틀림) | 서버 키 이름은 일반 채팅과 같다. "프론트 타입 기존 선언 재사용" 근거는 틀림 — 선언은 `ChatAnswerCompletedData` 에만 있다(G-I1) |
| D-02 | 헬퍼 1곳 + AST 계약 테스트 | 준수 | L1736-1751, test_answer_payload_contract.py. 사각지대는 G-M5 |
| D-03 | None 이면 키 생략 | 준수 | L1746-1747. 프론트도 숫자일 때만 반영(L149-150) |
| D-04 | 차단·강등·승인 대기 턴도 노출 | 준수 | L635, L693, L449 |
| D-05 | REST 에도 additive | 준수 | schemas.py:300, 실런 501/null |
| D-06 | 재개 답변은 범위 밖 | 준수 | L1160 반환값 미사용 |
| D-07 | 프론트는 훅 필드 1개 + 페이지 1줄, MessageBubble 이하 무변경 | 준수 | index.tsx:268 한 줄. 훅 필드 1개. 다만 타입 파일 1줄 추가가 필요했다(G-I1) |

---

## 9. Gap 목록

### Critical

없음. Plan 성공 기준을 위반하는 기능 결함은 찾지 못했다.

### Important

| ID | 파일:라인 | 내용 | 신뢰도 | 설계 근거 | 제안 |
|----|-----------|------|:------:|-----------|------|
| G-I1 | idt_front/src/types/websocket.ts:62-70 / hooks/useAgentRunStream.ts:150 | `AgentAnswerCompletedData` 에 `assistant_message_id` 가 없다. 훅이 `msg.data.assistant_message_id` 를 두 번 읽어 **tsc TS2339 ×2 (211 vs 기준선 209)**. 런타임은 `typeof` 검사로 정상이고 Vitest 는 타입 검사를 하지 않아 놓쳤다. Plan §1.2·FR-10, Design §2.3·§5.3 의 "기존 선언 있음" 전제가 틀림 — 실제 선언은 일반 채팅용 `ChatAnswerCompletedData`(L145-160)에 있다 | 100% (tsc 확인) | Plan §4.2 "tsc 신규 오류 0", FR-10 | `AgentAnswerCompletedData` 에 `assistant_message_id?: number` + JSDoc 추가. tsc 기준선 209 복귀 확인. Plan §1.2·Design §5.3 정정 |

### 검증 공백 (DoD 항목, 코드 결함 아님)

| ID | 항목 | 상태 | 위험 | 제안 |
|----|------|------|------|------|
| G-V1 | 히스토리 재진입 시 평가 상태 유지 (Plan §4.1, Design §8.4 #3) | 미실행 | 히스토리 메시지 `id` 가 숫자 문자열이 아니면 `feedbackId()` 폴백(MessageBubble.tsx:86)이 동작하지 않아 재진입 후 버튼이 사라진다. 답변 완료 후 `agentHistory` 무효화(index.tsx:341-344)가 placeholder 를 서버 메시지로 바꾸는지도 **unverified** | 브라우저 실런 1회. 또는 `useAgentSessionMessages` 매핑의 id 형식 확인 |
| G-V2 | prompt-guard 차단 턴 라이브 실런 (Design §8.4 #2) | 단위 테스트만 | 낮음. 서버 경로는 테스트됐고 프론트 경로는 정상 턴과 같다 | 차단 문구로 WS 실런 1회 |

### Minor / 의도된 편차

| ID | 파일:라인 | 내용 | 신뢰도 | 판정 / 제안 |
|----|-----------|------|:------:|-------------|
| G-M1 | run_agent_use_case.py:524-528, 542, 557 | `execute()` 에서 `assistant_message_id` 를 초기화하지 않고 ANSWER_COMPLETED 분기 안(L542)에서만 대입한다. 지금은 모든 비실패 종료 경로가 ANSWER_COMPLETED 를 내므로 런타임 문제는 없다. 다만 나중에 ANSWER 없이 끝나는 분기가 생기면 L557 에서 `UnboundLocalError` | 95% | L525 옆에 `assistant_message_id: int \| None = None` 추가 |
| G-M2 | Design §6.1 vs Plan §3.2 / run_agent_use_case.py:173-179 | Design §6.1 은 "id 없음 → 경고 로그 1건", Plan NFR 은 "새 경고 로그 없음"이라 서로 어긋난다. 구현은 Plan 을 따라 로그가 없다 | 100% | Design §6.1 정정 |
| G-M3 | tests/application/agent_builder/ | §8.2 #9(승인 대기 스트림 테스트)와 #10(강등 분기 persist=False)이 없다. 헬퍼 단위 테스트와 AST 계약이 대신 막는다 | 100% | 선택 사항 |
| G-M4 | Design §8.4 #1 | 평가 POST 기대 상태를 201 로 적었지만 실제는 200 | 100% | 설계 정정 |
| G-M5 | test_answer_payload_contract.py:57-71 | AST 계약의 사각지대: (a) 이벤트 타입을 변수에 담아 넘기면 탐지되지 않는다. (b) 헬퍼 결과로 대입된 이름이 재대입돼도 통과한다 | 70% | 현재 코드에서는 문제없음 |

### 추가 구현 (설계 X, 구현 O)

| 항목 | 위치 | 판단 |
|------|------|------|
| 모듈 함수 `_saved_message_id` (VO `.value` + int 판정) | run_agent_use_case.py:173-179 | MagicMock 대역·id 미발급 저장소에서 키 오염을 막는다. 타당 |
| 훅의 `typeof === 'number'` 판정 | useAgentRunStream.ts:149-150 | 설계의 `?? null` 보다 엄격하다. 타당 |

---

## 10. 권장 조치

### 즉시 조치 (iterate 후보)
1. G-I1: `AgentAnswerCompletedData` 에 `assistant_message_id?: number` 추가 → tsc 기준선 209 복귀. 예상 Match Rate 90.9%
2. G-M1: `execute()` 에서 `assistant_message_id` 초기화 (1줄)

### Check 단계 실런 (Runtime 축)
3. G-V1: 브라우저에서 에이전트 답변에 👎 → 세션 재진입 → 👎 상태 유지 확인
4. G-V2: prompt-guard 차단 문구로 WS 실런

### 문서 갱신 필요 (수정하지 않고 보고)
- Plan §1.2 배경, FR-10: "AgentAnswerCompletedData 에 이미 선언" → 일반 채팅 타입에만 있었음
- Design §2.3, §5.3: `types/websocket.ts` "무변경" → "필드 1줄 추가". `types/agent.ts` 는 "대응 타입 없음(레거시 `{runId}`)"으로 확정
- Design §6.1: 경고 로그 문구 삭제
- Design §8.4 #1: POST 201 → 200

---

## 11. Runtime Verification

### 11.1 실행됨 (Do 단계, 인프로세스 TestClient + 실 DB)

| # | 시나리오 | 결과 |
|---|----------|------|
| R1 | WS 에이전트 실행 → `agent_answer_completed` | 키 `['answer','assistant_message_id','tools_used']`, id=499 |
| R2 | `POST /api/v1/conversations/messages/499/feedback` (down + comment) → GET → DELETE → GET | 200 → 200 → 204 → rating null |
| R3 | `POST /api/v1/agents/{id}/run` (기본) | `assistant_message_id=501` |
| R4 | 같은 요청 + `persist_conversation=false` | `assistant_message_id=null` |
| R5 | 자동 회귀 | pytest 1,491 통과, Vitest 1,519 통과(상시 실패 4파일 제외) |

### 11.2 미실행 / 남은 계획

**L1: API**

| # | 테스트 | 명령 | 기대 상태 | 기대 응답 |
|---|--------|------|:---------:|-----------|
| 1 | 차단 턴 REST | `curl -s -X POST localhost:8000/api/v1/agents/{id}/run -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"user_id":"7","query":"<차단 규칙 매칭 문구>"}'` | 200 | `.answer == BLOCK_NOTICE_KO`, `.assistant_message_id` 정수 |
| 2 | 평가 행 agent_id | `SELECT message_id, agent_id, rating FROM message_feedback WHERE message_id=499` | — | `agent_id` = 실행한 에이전트 id (**unverified**) |
| 3 | 타입 검사 | `cd idt_front && npx tsc --noEmit -p tsconfig.app.json` | — | 기준선 209 (G-I1 수정 후) |

**L2: UI (Playwright, Vitest 단위로는 통과)**

| # | 페이지 | 동작 | 기대 결과 | 기대 API |
|---|--------|------|-----------|----------|
| 1 | /chatpage (에이전트 선택) | 질문 전송 → 답변 완료 | 말풍선 아래 "좋아요"/"싫어요" 버튼 | WS `agent_answer_completed` |
| 2 | /chatpage | "싫어요" → 이유 칩 → 전송 | 선택 상태 표시 | POST `/conversations/messages/{id}/feedback` |
| 3 | /chatpage | 같은 버튼 재클릭 | 선택 해제 | DELETE 같은 경로 |
| 4 | /chatpage | 차단 문구 전송 | 안내문 아래 평가 버튼 | WS `guard_blocked: true` + id |

**L3: E2E**

| # | 시나리오 | 성공 기준 |
|---|----------|-----------|
| 1 | 에이전트 답변 👎 → 다른 세션 이동 → 원 세션 재진입 (G-V1) | 같은 답변에 👎 상태 유지, `feedbackId()` 숫자 id 폴백 동작 |
| 2 | 벤치마크 실행 (persist=False) | 결과 무변화, payload 에 키 없음 (회귀 테스트로 대체됨) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | gap-detector 분석 초안. 런타임 포함 89.7% / 정적 95.4%. Important 1건(G-I1 WS 타입 선언 누락), 검증 공백 2건, Minor 5건 | gap-detector |
| 0.2 | 2026-11-02 | 메인 세션 tsc 확인(211 vs 209, G-I1 신뢰도 100%), DoD 표 verify·SOT 항목 보정 | 배상규 + Claude |
| 0.3 | 2026-11-03 | Act-1: G-I1·G-M1 수정, 설계·Plan 정정, 재채점 90.9% | 배상규 + Claude |
