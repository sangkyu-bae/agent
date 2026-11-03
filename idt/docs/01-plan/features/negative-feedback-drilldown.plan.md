# negative-feedback-drilldown Planning Document

> **Summary**: 관리자가 대시보드의 최근 👎 항목을 열어 질문·답변·검색 근거를 확인하고 해당 실행의 런 상세로 이동하게 한다.
>
> **Project**: sangplusbot — idt (백엔드) + idt_front (프론트)
> **Version**: 기준 커밋 1baf6d1 (master, PR #83 머지 후)
> **Author**: 배상규 + Claude
> **Date**: 2026-11-02
> **Status**: Draft
> **원천**: `docs/proposals/2026-10-15.md` 후보 #8 (§2-8). 제안서의 전제 3건을 실측으로 정정했다(§1.2).

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **문제** | 관리자 대시보드의 최근 부정 피드백은 에이전트 id와 👎 이유만 보여 준다. 어떤 질문에 어떤 답을 했고 그 실행이 무엇을 했는지 볼 수 없어서 "어디서 틀리는지"를 판단할 수 없다. |
| **해결** | 관리자 전용 `GET /api/v1/admin/eval/negative/{message_id}/drilldown`을 추가한다. 평가된 답변에서 질문을 복원해 질문·답변·런·검색 근거를 한 응답으로 돌려주고, 대시보드는 이를 모달로 표시한다. |
| **기능·UX 효과** | 👎 항목을 누르면 모달에서 질문, 답변, 이유, 재작성 쿼리별 근거를 확인하고 런 상세나 LangSmith로 이동한다. 검색을 쓰지 않은 실행은 오류가 아니라 "검색을 사용하지 않은 실행"으로 표시한다. |
| **핵심 가치** | 그동안 쌓기만 하던 👎 데이터를 관리자가 원인 확인에 쓸 수 있게 된다. 로드맵 Phase 2의 검증 목표 "어디서 틀리는지가 데이터로 보이는가"를 관리자 화면에서 처음 확인할 수 있다. |

---

## Context Anchor

> Design·Do 문서로 전파해 세션 간 맥락을 유지한다.

| Key | Value |
|-----|-------|
| **WHY** | 👎 데이터는 쌓이지만 관리자가 질문·답변·실행 근거를 열어 볼 화면이 없어 원인을 판단할 수 없다. |
| **WHO** | P3 관리자(부서·시스템) — 👎 원인을 확인하고 위키 draft 승인 여부를 판단하는 사람. P2 에이전트 소유자는 관리자 권한이 있을 때만 해당한다. |
| **RISK** | 대화 원문을 관리자 화면에 처음 표시한다(런 상세 API는 이미 반환 중). 👎가 있는 답변으로만 조회를 제한하고 조회 기록을 남긴다. 평가 id(assistant)와 런 연결 id(user)가 달라 질문 복원을 빠뜨리면 200 빈 결과로 조용히 실패한다. |
| **SUCCESS** | 로컬 실데이터 👎 2건 모두 질문·답변·런 링크가 표시된다. 👎가 없는 메시지는 404, 비관리자는 403이다. 응답에 사용자 id가 없다. 기존 pytest/Vitest 회귀 0. |
| **SCOPE** | 신규 조회 UseCase·엔드포인트 1개, 프론트 타입·서비스·훅·모달, 패널 항목 버튼화, 테스트. 필터·페이지네이션, 전용 화면, 스키마 변경, `retrievals` 동작 변경은 제외한다. |

---

## 1. Overview

### 1.1 Purpose

관리자가 낮은 평가를 받은 답변의 질문, 답변 원문, 실행 근거를 한곳에서 확인해 오답 원인을 판단할 수 있게 한다.

### 1.2 Background

로드맵 Phase 2 항목 "admin dashboard에 피드백 통계·低평가 답변 드릴다운" 중 통계와 목록은 `agent-eval-gate`(2026-07)에서 구현됐고 드릴다운이 남아 있다. 시나리오 S4는 관리자가 출처를 열어 검증하는 흐름을 전제한다.

**제안서 전제와 실측 차이** (2026-11-02, 로컬 DB 읽기 전용 조회)

| 제안서 전제 | 실측 | 계획 반영 |
|------------|------|----------|
| `recent-negative`의 항목으로 `GET /conversations/messages/{id}/retrievals`를 호출하면 된다 | 피드백 `message_id`는 **assistant** 메시지이고 `ai_run.user_message_id`는 **user** 메시지다. 👎 2건을 그대로 조인하면 런 0건이고 API는 200 빈 `runs`를 돌려준다. 질문을 복원해 조인하면 2건 모두 런 1건씩 찾는다 | 백엔드에서 질문을 복원한다 |
| 크기 S: 프론트 패널 1·상수 1 | 프론트에 `retrievals` 소비자가 없고 질문·답변을 표시하는 관리자 화면도 없다. `GET /agents/runs/{id}`가 step 요약으로 질문·답변을 반환하지만 화면은 표시하지 않는다 | 백엔드 UseCase·엔드포인트와 프론트 타입·서비스·훅이 추가된다 |
| General Chat 데이터로 즉시 동작하고 에이전트 경로 데이터는 #2 이후 채워진다 | 현재 👎 2건은 모두 에이전트 답변이다(히스토리 재조회의 숫자 id로 평가된 것으로 보이며 확정은 `agent-run-feedback-wiring` 실런 범위). `turn_index`가 질문과 같은 과거 결함 행이며 코멘트가 없다 | `EvalPolicy.find_question`의 같은 turn 폴백이 필수다. #2는 선행 조건이 아니다 |

**추가 실측**

- 👎 2건의 런은 `data_analysis_worker` 경로로 `ai_retrieval_source`가 0건, `ai_run_step`이 7건이다. 도구 호출 기록도 0건이다. 근거 0건은 결함이 아니라 정상 상태일 수 있다.
- 검색 근거가 있는 런은 전체 238건 중 34건이다. 마지막 기록은 2026-10-03이다.
- `user_message_id`당 런이 2건 이상인 경우는 현재 0건이지만, 기존 API 계약은 복수 런을 허용하므로 목록으로 다룬다.
- 전체 평가는 3건(👎 2, 👍 1)뿐이다. 실데이터 검증 표본이 작다.

**코드 근거**

- `idt/src/application/eval/use_cases.py` `_find_question()` + `EvalPolicy.find_question()` — 질문 복원 규칙. turn-1 우선, 같은 turn 폴백, 모호하면 None
- `idt/src/application/agent_run/use_cases/get_message_retrievals_use_case.py` — `find_runs_by_user_message` + `_group_by_query`. `is_admin`이면 소유 검증을 통과한다
- `idt/src/api/routes/eval_router.py` `recent_negative()` — `require_role("admin")` 선례
- `idt_front/src/pages/AdminDashboardPage/components/AgentSatisfactionPanel.tsx` — 항목에 링크와 버튼이 없다
- `idt_front/src/pages/JobsPage/ApprovalDetailDrawer.tsx` — 공통 `Modal` 기반 상세 패턴

### 1.3 Related Documents

- 제안서: `docs/proposals/2026-10-15.md` §2-8
- 비전: `idt/docs/architecture/growing-agent-vision.md` Phase 2
- 시나리오: `docs/USER-SCENARIOS.md` P3, S4
- 위키: `erd-conversation-eval`(turn_index 복합 키, 소프트 참조), `erd-agent-run`(`user_message_id` 소프트 참조), `data-exists-exposure-missing`, `additive-contract-extension`, `false-green-quality-gates`, `tsx-authoring-pitfalls`, `admin-screens`
- 관련 사이클: `agent-run-feedback-wiring`(Plan 단계, 독립 진행 가능), 아카이브 `agent-run-turn-index-fix`, `retrieval-observability`

---

## 2. Scope

### 2.1 In Scope

- [ ] 드릴다운 조회 UseCase — 👎 존재 확인 → 답변 조회 → 질문 복원 → 런·근거 조회
- [ ] `GET /api/v1/admin/eval/negative/{message_id}/drilldown` (admin 전용) + 응답 스키마 + `main.py` DI
- [ ] 조회 감사 로그(관리자 id, message_id, 본문 미포함)
- [ ] 프론트 타입·엔드포인트 상수·쿼리 키·서비스·훅
- [ ] `NegativeDrilldownModal` 신규 — 질문, 답변, 이유, 런별 근거, 런 상세·LangSmith 링크, 로딩·오류·빈 상태
- [ ] `AgentSatisfactionPanel` 항목을 키보드로 조작 가능한 버튼으로 변경
- [ ] 백엔드·프론트 테스트, 로컬 실데이터 실런 확인

### 2.2 Out of Scope

- 부정 피드백 필터·검색·페이지네이션, 전용 화면 (현행 최근 20건 유지)
- `GET /conversations/messages/{id}/retrievals` 동작 변경
- `recent-negative` 응답 변경
- `message_feedback`·`ai_run` 스키마 변경 (마이그레이션 0)
- 패널의 에이전트 UUID를 이름으로 표시하는 변경
- 고평가(👍) 드릴다운, 위키 draft 승격 연결
- `SubmitFeedbackUseCase` 소유자 검증 추가 (§5 참고, 기존 동작 유지)
- 런 상세 페이지의 `user_id` 표시 변경 (§5 참고)
- 에이전트 경로 평가 버튼 (`agent-run-feedback-wiring` 범위)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 | 상태 |
|----|---------|---------|------|
| FR-01 | `GET /api/v1/admin/eval/negative/{message_id}/drilldown`은 `require_role("admin")`으로 보호한다. 미인증 401, 비관리자 403 | High | Pending |
| FR-02 | 해당 `message_id`에 `rating=down` 피드백이 없거나 assistant 메시지가 아니면 404를 반환한다. 임의 메시지 열람을 막는 조회 조건이다 | High | Pending |
| FR-03 | 질문은 기존 `EvalPolicy.find_question`으로 복원한다. 규칙을 복제하지 않는다. 같은 `turn_index` 과거 행도 복원돼야 한다 | High | Pending |
| FR-04 | 런과 근거는 복원한 **질문 메시지 id**로 조회한다. 그룹핑은 기존 `retrievals`와 같은 규칙(run → search_query, rank_index 순)을 쓴다 | High | Pending |
| FR-05 | 응답은 `message_id`, `agent_id`, `question`, `answer`, `runs[]`를 포함한다. `runs[]`는 `run_id`, `langsmith_run_url`, `groups[]`다. 필드명은 `MessageRetrievalsResponse`와 맞춘다 | High | Pending |
| FR-06 | 응답에 사용자 id(세션 소유자·평가자)와 `session_id`를 포함하지 않는다 | High | Pending |
| FR-07 | 질문을 복원하지 못하면 200으로 `question=null`, `runs=[]`를 돌려주고 답변은 그대로 싣는다 | Medium | Pending |
| FR-08 | 피드백은 있으나 원본 메시지가 삭제됐으면 404를 반환한다. 소프트 참조 고아 행이다 | Medium | Pending |
| FR-09 | 조회 성공 시 관리자 id와 message_id를 INFO 로그로 남긴다. 질문·답변 본문은 로그에 쓰지 않는다 | High | Pending |
| FR-10 | 패널의 부정 피드백 항목은 버튼이며 클릭 시 모달을 연다. 모달은 열린 항목만 조회한다 | High | Pending |
| FR-11 | 모달은 질문, 답변, 👎 이유(없으면 "코멘트 없음")를 표시한다. 답변은 기존 `MarkdownRenderer`로 렌더링한다 | High | Pending |
| FR-12 | 런이 있으면 런별로 재작성 쿼리 그룹과 문서를 표시하고 `/admin/agent-runs/{run_id}` 링크를 둔다. `langsmith_run_url`이 있으면 새 탭 링크를 둔다 | High | Pending |
| FR-13 | 표시 상태를 구분한다: 런은 있으나 근거 0건 → "이 실행은 문서 검색을 사용하지 않았습니다", 런 없음 → "연결된 실행 기록이 없습니다", 질문 복원 실패 → "질문을 찾지 못했습니다" | High | Pending |
| FR-14 | 404·오류 시 모달에 안내를 표시하고 대시보드는 유지한다 | Medium | Pending |
| FR-15 | API 계약 동기화: 백엔드 스키마를 `types/messageFeedback.ts`에 반영한다. 근거 타입은 `types/agentRunAdmin.ts`와 맞춘다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| 분류 | 기준 | 측정 방법 |
|------|------|----------|
| 보안 | 관리자 전용, 👎 있는 메시지로 한정, 사용자 id 비노출 | 라우터 401·403·404 테스트, 응답 키 집합 동등 비교 테스트 |
| 성능 | 목록 응답에 영향 없음, 모달을 열 때 1회 호출 | 목록 코드 무수정 확인, 훅 `enabled` 테스트 |
| 호환성 | 기존 API·위젯 동작 무변경 | 기존 eval·retrievals 테스트 무수정 통과, `FAILED` 목록 diff |
| 접근성 | 항목 키보드 조작 가능, 색상 외 텍스트 병행 | RTL `getByRole('button')` + 키보드 테스트 |
| 아키텍처 | Thin DDD 유지, 로직은 UseCase·Policy에, 라우터는 위임만 | verify-architecture, verify-logging |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-15 구현 및 TDD 테스트 통과
- [ ] 실런(`TestClient` 인프로세스): 로컬 👎 메시지 284·267 응답에 질문, 답변, 런 1건이 나오고 `groups=[]`이다
- [ ] 실런: 👍 또는 평가 없는 메시지는 404, 비관리자 토큰은 403
- [ ] 브라우저 실런: 대시보드 → 항목 클릭 → 모달 표시 → 런 상세 이동, 콘솔 오류 0
- [ ] 근거가 있는 경로 확인: 근거 있는 런에 임시 👎를 넣어 그룹 표시를 확인한 뒤 해당 행을 삭제한다. 실데이터 👎에 근거 있는 런이 없기 때문이다
- [ ] 회귀 0: pytest·Vitest `FAILED` 목록이 기준선과 동일
- [ ] SOT·위키 어긋남 보고 (`SOURCE-OF-TRUTH.md` API 표, `admin-screens` — 수정은 사용자 호출 시에만)

### 4.2 Quality Criteria

- [ ] 신규 코드 테스트 커버리지 80% 이상
- [ ] ruff·eslint·tsc 신규 오류 0 (기준선 목록 diff, `tsc -b` 포함)
- [ ] MSW 핸들러가 실제 서비스 URL·응답 형태와 일치
- [ ] 마이그레이션 없음

---

## 5. Risks and Mitigation

| 위험 | 영향 | 가능성 | 완화 |
|------|------|-------|------|
| 대화 원문을 관리자 화면에 처음 표시 — 런 상세 API는 step의 `input_summary`·`output_summary`로 이미 반환 중이다(실데이터 2건 측정) | High | High | 사용자 결정(전문 노출, 평가자 비노출). FR-02로 👎 답변에 한정, FR-06으로 식별자 제외, FR-09로 조회 기록. 로그는 운영 로그이며 별도 감사 테이블은 만들지 않는다. 런 상세 API 응답은 범위 밖이다 |
| 평가자 비노출이 런 상세에서 뚫림 — `AgentRunDetailPage`가 `run.user_id`를 표시한다 | Medium | High | 드릴다운 응답에는 없지만 링크로 이동하면 세션 소유자 id가 보인다. 기존 관리자 화면 동작이라 이번 범위에서 바꾸지 않는다. 필요하면 후속 사이클로 처리한다 |
| 질문 복원 누락 시 200 빈 결과로 조용히 실패 | High | Medium | assistant id로 조회하면 런이 안 나오는 회귀 테스트, 질문 id로 조회하는 호출 인자 단언, 실런 2건 확인 |
| 과거 같은 turn 행에서 다른 질문으로 잘못 복원 | Medium | Low | 실데이터 2건은 질문이 답변 바로 앞 id(283/284, 266/267)임을 확인. 모호하면 None(FR-07). 규칙 변경 없음 |
| `recent-negative`·피드백의 소유자 미검증 — `SubmitFeedbackUseCase`는 메시지 존재만 확인하므로 다른 사용자도 평가 가능. 같은 message_id에 👎가 여러 건일 수 있다 | Low | Low | 드릴다운은 메시지 단위라 동작한다. 모달의 이유는 목록에서 받은 값을 쓴다. 패널 `key={message_id}` 중복 가능성은 Design에서 확인. 소유자 검증은 범위 밖 |
| 근거 0건을 결함으로 오해 | Medium | High | FR-13의 상태 문구로 구분 |
| DI·세션 — UseCase가 eval, conversation, agent_run 저장소를 함께 쓴다 | Medium | Medium | 한 요청 한 세션 규칙 준수. Design에서 기존 `_message_retrievals_f` 조립을 확인해 같은 세션을 주입한다 |
| MSW·픽스처가 실제 응답과 어긋나 거짓 초록 | Medium | Medium | Do 마지막에 실런을 DoD로 둔다 |
| 평가 데이터 3건으로 표본이 작다 | Low | High | 근거 표시 경로는 임시 행으로 검증한다. 운영 데이터 검증은 `agent-run-feedback-wiring` 이후 E2E 이월 목록에 둔다 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| 리소스 | 유형 | 변경 내용 |
|--------|------|----------|
| `MessageFeedbackRepositoryInterface` + 구현체 | 포트·저장소 | 메시지의 down 존재 조회 메서드 추가 |
| 드릴다운 UseCase (신규) | application | 조회 조합 |
| `eval_router.py` | API | 엔드포인트와 DI 플레이스홀더 추가 |
| `interfaces/schemas/eval_drilldown_response.py` (신규) | 스키마 | 응답 모델 추가. application이 interfaces의 기존 DTO를 import할 수 없어 위치를 정했다 |
| `main.py` | DI | override 1건 추가 |
| `AgentSatisfactionPanel.tsx` | 프론트 컴포넌트 | 항목 버튼화, 모달 연결 |
| `NegativeDrilldownModal.tsx` (신규) | 프론트 컴포넌트 | 모달 |
| `types/messageFeedback.ts`, `constants/api.ts`, `lib/queryKeys.ts`, `services/messageFeedbackService.ts`, `hooks/useMessageFeedback.ts` | 프론트 계약 | 추가만 |

### 6.2 Current Consumers

| 리소스 | 동작 | 코드 경로 | 영향 |
|--------|------|----------|------|
| `MessageFeedbackRepositoryInterface` | CALL | `SubmitFeedbackUseCase`, `GetFeedbackUseCase`, `DeleteFeedbackUseCase`, `AgentEvalStatsUseCase` | None — 메서드 추가만. 테스트 더블은 Design에서 확인 |
| `EvalPolicy.find_question` | CALL | `SubmitFeedbackUseCase._find_question` | None — 재사용만. 조회+정책 묶음 공유 방식은 Design에서 결정 |
| `find_runs_by_user_message`, `find_retrievals` | READ | `GetMessageRetrievalsUseCase` | None — 읽기만 |
| `_group_by_query` | CALL | `GetMessageRetrievalsUseCase` | Needs verification — 재사용 방식(UseCase 위임 또는 함수 공유)은 Design에서 결정 |
| `AgentSatisfactionPanel` | RENDER | `AdminDashboardPage`, `AgentSatisfactionPanel.test.tsx` | Needs verification — 기존 3개 테스트는 텍스트 단언이라 통과 예상 |
| `RecentNegativeItem` | READ | 패널 | None — 무변경 |
| `/admin/agent-runs/:runId` | NAVIGATE | 대시보드 표, 런 목록, 사용량 화면 | None — 링크 추가만 |

### 6.3 Verification

- [ ] 위 소비자 전부 기존 테스트 무수정 통과
- [ ] 기존 엔드포인트 인증·권한 변경 없음
- [ ] 기존 응답 필드 추가·제거 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| 수준 | 선택 |
|------|:----:|
| Enterprise (Thin DDD, 기존 구조 유지) | ☑ |

### 7.2 Key Architectural Decisions

| 결정 | 선택지 | 선택 | 근거 |
|------|--------|------|------|
| API 형태 | 상세 엔드포인트 신설 / 목록 필드 추가 / `retrievals` 변경 | 상세 엔드포인트 신설 | 사용자 결정. 목록 20건 조회 비용과 기존 공개 API 의미 변경을 피한다 |
| 대화 노출 | 전문·평가자 비노출 / 미리보기 / 비노출 | 전문·평가자 비노출 | 사용자 결정. 원문 없이는 오답 판단이 불가능하다 |
| 화면 형태 | 모달 / 인라인 펼침 / 별도 페이지 | 모달 | 사용자 결정. 대시보드 맥락을 유지하고 공통 `Modal` 패턴을 재사용한다 |
| 조회 범위 제한 | 👎 메시지만 / 모든 메시지 | 👎 메시지만 | 노출 목적을 코드로 제한한다 (Claude 판단) |
| 고아 피드백 | 404 / 200 + 플래그 | 404 | 표시할 내용이 없고 모달 오류 상태로 충분하다 (Claude 판단) |
| 질문 복원 실패 | 404 / 200 + `question=null` | 200 | 답변은 볼 수 있으므로 쓸 수 있는 결과가 존재한다. `degradation-vs-failure-boundary` 기준 (Claude 판단) |
| 감사 기록 | 구조화 로그 / 감사 테이블 | 구조화 로그 | 스키마 변경 없이 추적 가능하다. 감사 테이블은 범위 초과 (Claude 판단) |

### 7.3 Clean Architecture Approach

```
interfaces  eval_router → 위임 + admin 가드, api_schemas 응답 변환
application 드릴다운 UseCase → 조회 순서 제어
domain      EvalPolicy.find_question 재사용, 포트 메서드 추가
infra       MessageFeedbackRepository 조회 구현

front       Panel(버튼) → Modal → useNegativeDrilldown → service → API
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md`, `idt_front/CLAUDE.md`, `idt/docs/rules/*`
- [x] ruff, eslint, `tsconfig` 설정
- [x] additive 계약 확장 관례

### 8.2 Conventions to Define/Verify

| 분류 | 현재 상태 | 확인 사항 | 우선순위 |
|------|----------|----------|:-------:|
| 상수 위치 | 존재 | 컴포넌트 파일 런타임 상수 export 금지, `as const`는 `src/types/` | High |
| 프론트 토큰 | 존재 | 신규 모달은 토큰·`components/ui` 키트 사용, `zinc-400` 금지. 패널 기존 스타일은 변경 범위만 손댄다 | Medium |
| 에러 처리 | 존재 | `ApiError` 인터셉터 기준으로 404 판정(`err.status`) | Medium |
| 라우터 테스트 | 존재 | `app.routes` 순회 금지, TestClient 실요청 | Medium |

### 8.3 Environment Variables Needed

없음. 기존 `eval_recent_negative_limit`만 유지한다.

---

## 9. Next Steps

1. `/pdca design negative-feedback-drilldown` — UseCase 조립 방식(`GetMessageRetrievalsUseCase` 위임 또는 함수 공유), 세션 주입, 질문 복원 공유 방식, 모달 구성
2. Do: 백엔드(저장소 → UseCase → 라우터·DI) → 프론트(계약 → 훅 → 모달 → 패널) → 실런
3. Check → Report → Archive

---

## Version History

| 버전 | 날짜 | 변경 | 작성자 |
|------|------|------|--------|
| 0.1 | 2026-11-02 | 초안 — 제안서 #8 기반, 로컬 DB 실측으로 전제 3건 정정, 사용자 결정 4건 반영 | 배상규 + Claude |
| 0.2 | 2026-11-02 | Design 조사 반영 — "대화 원문 첫 노출 경로" 판단 정정(런 상세 API가 이미 반환), FR-02에 assistant 조건 추가, FR-11 렌더러 확정, 응답 스키마 위치 변경 | 배상규 + Claude |
