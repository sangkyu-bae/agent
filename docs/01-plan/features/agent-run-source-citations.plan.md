# agent-run-source-citations Planning Document

> **Summary**: 에이전트 답변 아래에 그 실행에서 조회한 문서·웹·위키·MCP 근거를 칩으로 표시하고, 세션을 다시 열어도 복원한다.
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-02
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 실행의 내부 문서·웹 검색 근거는 `ai_retrieval_source`에, MCP 호출 결과 요약은 `ai_tool_call`에 저장되지만 답변 이벤트와 화면에 전달되지 않는다. 사용자는 에이전트 답변의 근거를 확인할 수 없다. |
| **Solution** | 실행 기록에서 근거 목록을 조립하는 단일 정책을 만들고, `ANSWER_COMPLETED`의 additive `sources`와 인증된 세션 근거 API로 전달한다. 프론트는 기존 `SourceCitation`을 종류별 칩과 발췌 패널로 확장한다. |
| **Function/UX Effect** | 답변 완료 시 문서·웹·위키·MCP 근거 칩이 표시되고, 칩에서 발췌를 읽거나 원본 링크로 이동할 수 있다. 세션을 다시 열어도 같은 칩이 표시된다. 근거가 없으면 칩 영역을 표시하지 않는다. |
| **Core Value** | P1·P4가 "출처를 신뢰할 수 있는 답"을 직접 확인할 수 있게 하여 S2의 "근거 배지 → 원문 대조" 흐름을 주 경로인 에이전트 실행에서 완성한다. |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | 근거는 저장되지만 에이전트 답변에 표시되지 않아 사용자가 답변을 원문과 대조할 수 없다. |
| **WHO** | P1 여신 심사역, P4 일반 사용자(최종 사용자). P2 에이전트 소유자는 답변 품질 확인에 활용한다. |
| **RISK** | MCP 결과의 근거 판별 오류와 민감정보 노출, 공유 에이전트에서 KB 권한이 없는 사용자에게 청크 발췌 노출, 검색 근거를 "실제 인용"으로 오해할 가능성. |
| **SUCCESS** | 실시간과 재진입의 칩 목록 일치, 4종 근거의 실런 표시, 답변 흐름 비차단, 기존 경로 회귀 0건. |
| **SCOPE** | M1 근거 조립 정책 → M2 실시간 경로 → M3 세션 근거 API → M4 프론트 칩·발췌 패널 |

---

## 1. Overview

### 1.1 Purpose

에이전트 답변마다 그 실행이 조회한 근거를 표시한다. 사용자는 답변을 읽는 자리에서 근거의 종류와 출처를 확인하고, 발췌나 원본과 대조할 수 있다.

### 1.2 Background

`docs/proposals/2026-10-15.md` 후보 #6에서 도출되었다. retrieval-observability가 기록과 조회 API까지 구현하고 UI를 이월했다. 코드 대조 결과는 다음과 같다.

| 구간 | 현재 상태 | 근거 |
|------|----------|------|
| 내부 문서·웹 기록 | 저장됨 | `idt/src/application/rag_agent/tools.py:458`, `idt/src/infrastructure/web_search/tavily_tool.py:165` |
| 런↔user 메시지 연결 | 저장됨 | `idt/src/application/agent_builder/run_agent_use_case.py:355-362` |
| 답변 이벤트 | `sources` 없음 | `run_agent_use_case.py:436` |
| 프론트 스트림 상태 | `sources` 없음 | `idt_front/src/hooks/useAgentRunStream.ts:30-41` |
| 프론트 뷰 | `sources: []` 고정 | `idt_front/src/pages/ChatPage/index.tsx:264` |
| 문서 라벨 | `RetrievalDto`에 파일명 없음. routed 기록의 `metadata_json`에도 없음 | `idt/src/interfaces/schemas/agent_run_response.py:27`, `tools.py:389` |
| 위키 | `wiki_read`는 기록 없음 | `idt/src/infrastructure/wiki/wiki_read_tool.py:63` |
| MCP | 결과 요약 1KB가 `ai_tool_call.result_summary`에 저장. 근거로 조회하는 경로 없음 | `idt/src/infrastructure/llm/usage_callback.py:39,322` |
| 문서 칩 | `onClick` 없음. 점수는 무조건 `%` 표시 | `idt_front/src/components/chat/SourceCitation.tsx:34-44` |

제안서와 달라진 판단은 두 가지다.

1. 제안서의 `collected_sources` 재사용을 채택하지 않는다. 에이전트 경로에서 쓰이지 않고 실행 후 읽을 경로도 없으며, 재진입 복원에 사용할 수 없다. 실행 기록을 단일 원천으로 쓴다.
2. 히스토리 복원의 선행 조건에서 #2 `agent-run-feedback-wiring`을 뺀다. 히스토리 API가 이미 메시지 `id`와 `turn_index`를 반환하고, #1 turn index 수정이 완료되었다.

### 1.3 Related Documents

- 제안: `docs/proposals/2026-10-15.md` §2-6
- 시나리오: `docs/USER-SCENARIOS.md` P1, S2
- 위키: `conventions/additive-contract-extension.md`, `conventions/false-green-quality-gates.md`, `backend/patterns/mcp-runtime-tool-shape.md`, `backend/patterns/degradation-vs-failure-boundary.md`, `backend/db/erd-agent-run.md`, `frontend/chat/streaming-message-action-id.md`
- 선행 아카이브: `idt/docs/archive/2026-07/retrieval-observability/`, `docs/archive/2026-10/agent-run-turn-index-fix/`

---

## 2. Scope

### 2.1 In Scope

- [ ] 실행 기록을 표시용 근거 목록으로 변환하는 단일 정책 (M1)
- [ ] 내부 문서, 웹, 위키, MCP 4종 근거 표시 (M1~M4)
- [ ] `ANSWER_COMPLETED` payload의 additive `sources` (M2)
- [ ] 인증된 세션 근거 API (M3)
- [ ] 프론트 타입·스트림·뷰·히스토리 매핑 동기화 (M4)
- [ ] `SourceCitation` 종류별 칩, 문서·MCP 발췌 패널, 웹 링크, 점수 숨김 (M4)

### 2.2 Out of Scope

- 답변에 실제 인용된 근거만 추리는 판정 (검색·조회된 근거를 "참고 문서"로 표시)
- 답변 본문 안의 각주·문장별 인용
- KB 문서 뷰어로 이동
- 새 테이블, 컬럼, 마이그레이션
- 웹훅·백그라운드·스케줄 응답 payload와 `RunAgentResponse` 변경
- 일반 채팅의 `sources` 계약 변경 (칩 표시 개선과 발췌 패널은 공용 컴포넌트를 통해 적용)
- 일반 채팅 세션의 재진입 복원
- `assistant_message_id` 전달과 👍/👎 연결 (#2 범위)
- `messages/{id}/retrievals` 응답 변경 및 `negative-feedback-drilldown` (#8 범위)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 일반 완료 경로와 recursion limit 강등 경로의 `ANSWER_COMPLETED`에 근거가 있을 때만 `sources`를 싣는다. prompt guard 차단 턴에는 싣지 않는다. | High | Pending |
| FR-02 | 근거 조립은 정책 1곳에서 수행하고, 실시간 경로와 히스토리 경로가 같은 정책을 쓴다. | High | Pending |
| FR-03 | 문서는 문서 단위, 웹은 URL 단위, 위키는 문서 id 단위, MCP는 도구 단위로 중복을 제거한다. | High | Pending |
| FR-04 | 총 N건만 표시한다. N은 config로 지정한다. 검색 방식 간 점수를 비교하지 않고, 종류별 조회 순서로 정렬한 뒤 종류를 번갈아 선택해 한 종류가 상한을 독점하지 않게 한다. | High | Pending |
| FR-05 | 문서 라벨은 메타데이터 파일명, `document_metadata.filename`, 조항명, KB 이름, 고정 문구 순으로 폴백한다. 쓰기 경로는 변경하지 않는다. | High | Pending |
| FR-06 | 웹 근거는 제목을 라벨로, `url_full`을 링크로 제공한다. | High | Pending |
| FR-07 | `ai_tool_call`의 성공한 `wiki_read`를 근거로 조립하고 위키 칩은 `/knowledge/{id}`로 이동한다. 열람 실패는 표시하지 않는다. | Medium | Pending |
| FR-08 | MCP는 결과가 있는 호출을 표시하되 카탈로그에 없는 도구, `requires_approval=true`, `category=action`, 실패 호출을 제외한다. `status`가 SUCCESS여도 본문이 오류 문자열이면 실패로 본다. 라벨은 `mcp_tool_name`을 쓰고 UUID를 노출하지 않는다. | High | Pending |
| FR-09 | 인증된 세션 근거 API로 assistant 메시지별 근거를 반환한다. 비인증 메시지 API에는 근거를 싣지 않는다. 세션 단위 일괄 조회로 처리하며 메시지별 조회를 금지한다. | High | Pending |
| FR-10 | user 메시지 1건에 런이 여러 개면 마지막 런의 근거를 쓴다. turn index 수정 전 메시지도 순서 기반 짝짓기로 처리한다. | Medium | Pending |
| FR-11 | 근거 조회·조립이 실패해도 답변과 히스토리는 정상 반환하고 `sources`만 생략한다. 스택 트레이스를 포함한 warning을 남긴다. | High | Pending |
| FR-12 | 근거 조회는 호출자 opt-in(기본 False)으로 켠다. WS 경로만 켜서 웹훅·백그라운드·RAGAS에 쿼리를 추가하지 않는다. | Medium | Pending |
| FR-13 | 프론트 `DocumentSource`에 optional `kind`, `url`을 추가하고 `score`를 optional로 바꾼다. 스트림→뷰→`Message` 경로와 세션 근거 API→`useAgentSessionMessages` 병합 경로를 동기화한다. | High | Pending |
| FR-14 | 칩은 종류를 텍스트로 구분한다. 에이전트 근거는 점수를 표시하지 않고, 일반 채팅 칩의 점수와 위키 동작은 유지한다. | High | Pending |
| FR-15 | 문서·MCP 칩을 클릭하면 저장된 발췌를 펼친다. 발췌는 일반 텍스트로만 렌더링한다. 웹 링크는 http/https만 열고 새 탭은 `noopener`를 적용한다. | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 호환성 | 기존 WS·REST 소비자 무변경, 신규 필드 전부 optional | 기존 테스트 무수정 통과, `sources` 부재 시 UI 테스트 |
| 성능 | 답변당 근거 조회 쿼리는 고정 횟수, 세션 조회는 메시지 수에 비례하지 않음 | 쿼리 수를 단언하는 저장소·유스케이스 테스트 |
| 크기 | 근거당 발췌는 기존 `retrieval_preview_max_bytes` 이내, MCP는 1KB 이내 | 조립 정책 단위 테스트 |
| 보안 | HTML 미해석, 위험한 URL 스킴 차단, MCP 인자 비노출 | 컴포넌트·정책 단위 테스트 |
| 접근성 | 칩은 키보드 조작 가능, 패널 확장 상태를 `aria-expanded`로 전달, 색만으로 종류 구분 금지 | RTL 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] **SC-1**: 같은 답변의 실시간 칩과 재진입 칩의 종류·라벨·순서가 일치한다.
- [ ] **SC-2**: 문서, 웹, 위키, MCP 근거가 각각 실제 실행에서 표시되고, 문서·MCP 발췌와 웹·위키 이동이 동작한다.
- [ ] **SC-3**: `action`·승인 필요 MCP 도구, 실패한 호출, 빈 결과가 칩에 표시되지 않는다.
- [ ] **SC-4**: 근거 조회를 강제로 실패시켜도 답변과 히스토리가 정상 표시된다.
- [ ] **SC-5**: 근거가 없는 답변에는 칩 영역이 표시되지 않고, 과거 런은 폴백 라벨로 표시된다.
- [ ] **SC-6**: 웹훅·백그라운드 경로의 응답이 바뀌지 않고 근거 조회 쿼리가 추가되지 않는다.
- [ ] **SC-7**: 일반 채팅 칩의 기존 표시와 위키 이동이 유지된다.
- [ ] 라우터 스키마와 프론트 타입이 동기화되고 Design의 FR 역추적 표가 FR-01~15를 모두 포함한다.

### 4.2 Quality Criteria

- [ ] TDD로 작성하고 신규 모듈 커버리지는 80% 이상이다.
- [ ] 회귀는 작업 전후 정렬된 `FAILED` 목록 diff로 증명한다.
- [ ] 프론트 `tsc -b`, lint, 관련 Vitest가 통과한다. MSW 핸들러는 실제 응답 형태와 일치시킨다.
- [ ] `verify-architecture`, `verify-logging`, `verify-tdd`가 통과한다.
- [ ] 실제 LLM과 MCP 서버 1대를 사용한 실런 스모크를 완료한다. fake만으로 완료 처리하지 않는다.

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 조회만 하고 답변에 쓰지 않은 근거가 "인용"처럼 보인다. | Medium | High | 제목을 "참고 문서"로 유지하고 인용 의미의 표현을 쓰지 않는다. 실제 인용 판정은 후속 후보로 남긴다. |
| 공유 에이전트에서 KB 권한이 없는 사용자에게 청크 발췌가 노출된다. | High | Medium | 사용자 결정: 에이전트 사용 권한을 근거 공개 범위로 보고 실행한 본인에게 표시한다. 인증 API와 본인 세션 조회로 범위를 제한한다. |
| MCP 결과에 민감정보나 원시 JSON이 포함된다. | High | Medium | 1KB로 제한하고 인자를 노출하지 않으며 텍스트로만 렌더링한다. `pii-masking-integration`에서 이 표시 경로 포함 여부를 판단한다. |
| MCP `category`가 전부 미분류여서 근거로 보기 어려운 도구가 표시된다. | Medium | High | 사용자 결정: 제외 방식을 쓰고 관리자가 `category=action`으로 지정해 줄인다. |
| 표준 오류 문자열 외 형식의 MCP 실패가 칩으로 표시된다. | Medium | Medium | `Error executing tool` 패턴만 판별한다. 실측 분포를 Check에서 재확인한다. |
| 상위 N건 절단으로 답변에 쓰인 근거가 칩에서 빠진다. | Low | Medium | 종류를 번갈아 선택해 한 종류의 독점을 막는다. |
| 파일명을 찾지 못해 라벨이 부정확하다. | Low | Medium | `document_metadata`로 보강하고 KB 이름으로 폴백한다. |
| 서브에이전트의 근거가 누락되거나 런 ID가 달라진다. | Medium | Low | 서브에이전트 포함 그래프를 실제 컴파일해 실행하는 테스트와 실런 스모크로 확인한다. |
| 비활성화·삭제된 MCP 도구의 칩이 재진입 때 사라진다. | Low | Low | fail-closed 동작으로 수용한다. |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| 근거 조립 정책 | 신규 코드 | 실행 기록 → 표시용 근거 목록 변환 |
| `AgentRunRepositoryInterface` | Port | 런 묶음의 근거와 도구 호출을 일괄 조회하는 메서드 추가 |
| `DocumentMetadataRepositoryInterface` | Port | 파일명 일괄 조회 메서드 추가 |
| `ANSWER_COMPLETED` payload | WS 계약 | optional `sources` 추가 |
| 세션 근거 API | REST 신규 | 인증된 GET 엔드포인트 추가 |
| `DocumentSource` | 프론트 타입 | `kind`·`url` 추가, `score` optional |
| `SourceCitation` | 공용 컴포넌트 | 종류별 표시와 발췌 패널 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `stream()` | READ | `execute()` → 웹훅·백그라운드·스케줄·RAGAS | opt-in 미사용으로 무변경 |
| `ANSWER_COMPLETED` | READ | `ws_adapter.py` → `useAgentRunStream` | 알 수 없는 필드는 기존 소비자가 무시 |
| `ai_retrieval_source`, `ai_tool_call` | READ | 런 상세, 메시지 근거 조회 | 읽기 추가만 있어 영향 없음 |
| `useAgentSessionMessages` | READ | `ChatPage` | 근거 API 병합 추가. 실패 시 기존 결과 유지 |
| `DocumentSource` | READ | `useChatStream`, `useChat`, `MessageBubble`, `SourceCitation` | `score` optional 전환에 따른 타입 수정 필요 |
| `SourceCitation` | READ | `MessageBubble` | 일반 채팅 표시 회귀 테스트 필요 |
| `RunAgentResponse` | READ | 동기 실행 라우터·웹훅 | 변경 없음 |

### 6.3 Verification

- [ ] All consumers listed above verified to work with the proposed changes
- [ ] No auth/permission changes break existing operations
- [ ] No field additions/removals break existing queries or mutations

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | Complex architectures | ☑ (Thin DDD) |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 근거 원천 | 도구 메모리 / RunContext 수집 / 실행 기록 조회 | 실행 기록 조회 | 서브에이전트까지 포함하고 실시간과 재진입이 같은 결과를 낸다. |
| MCP 원천 | 어댑터에서 신규 기록 / `ai_tool_call` 읽기 | `ai_tool_call` 읽기 | 어댑터 변경과 tracker 주입이 필요 없고 과거 런에도 적용된다. |
| 위키 원천 | `ai_tool_call` 읽기 / `record_retrieval` 추가 | `ai_tool_call` 읽기 | 문서 id와 제목이 이미 저장되어 있고 쓰기 경로 변경이 없다. |
| 히스토리 영속 | 메시지 JSON 컬럼 / 런 조인 | 런 조인 | 마이그레이션이 없고 과거 런도 복원된다. |
| 재진입 전달 | 기존 메시지 API / 인증 전용 API | 인증 전용 API | 기존 메시지 API는 인증이 없어 발췌를 실을 수 없다. |
| 호출 범위 | 전 호출자 / 호출자 opt-in | opt-in | 불필요한 쿼리를 막고 기존 호출자를 유지한다. |
| 프론트 상태 | 별도 쿼리 / 메시지 필드 | `Message.sources` 재사용 | 렌더링 경로를 하나로 유지하고 추가 요청이 없다. |
| 테스트 | - | pytest, Vitest + RTL + MSW | 프로젝트 표준 |

### 7.3 Clean Architecture Approach

```
domain/       근거 항목 VO, 조립 정책, 저장소 포트
application/  RunSourcesService, GetSessionSourcesUseCase, RunAgentUseCase(opt-in)
infrastructure/ 일괄 조회 저장소, 세션 스코프 리더
interfaces/   세션 근거 응답 스키마, 라우터
idt_front/    types → hooks → ChatPage view → SourceCitation
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 3종 코딩 규칙
- [x] `idt/docs/rules/` 세부 규칙
- [x] TypeScript 설정, ESLint 설정

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **근거 kind 값** | 없음 | `document`, `web`, `wiki`, `mcp` wire 값 | High |
| **MCP 표기** | 위키 규칙 존재 | 표시 `mcp_tool_name`, 식별 `mcp:{srv}:{tool}` 준수 | High |
| **에러 처리** | degraded 경계 규칙 존재 | 근거 실패는 degraded, `exception=e` 로깅 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `AGENT_RUN_SOURCES_MAX_ITEMS` | FR-04의 N, 기본값 6 | Server | ☑ |

발췌 길이는 기존 `retrieval_preview_max_bytes`를 재사용하고 새 키를 만들지 않는다.

### 8.4 Pipeline Integration

해당 없음. PDCA 단일 기능 사이클로 진행한다.

---

## 9. Next Steps

1. [x] `/pdca design agent-run-source-citations`로 Design 작성
2. [ ] Design FR 역추적 표 검수
3. [ ] 모듈 단위 구현 (M1 → M2 → M3 → M4)
4. [ ] 실런 스모크와 Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | Initial draft | 배상규 |
| 0.2 | 2026-11-02 | Design 실측 반영: 쓰기 경로 변경 제거, 인증 세션 근거 API로 변경, MCP 실패 재판정, 발췌 노출 결정 | 배상규 |
