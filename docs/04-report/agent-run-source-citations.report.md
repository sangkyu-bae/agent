# agent-run-source-citations Completion Report

> **Status**: Complete (화면 확인·일부 실런 시나리오 이월)
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Completion Date**: 2026-11-03
> **PDCA Cycle**: Plan → Design → Do(4 모듈) → Check → Act-1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | agent-run-source-citations |
| Start Date | 2026-11-02 |
| End Date | 2026-11-03 |
| Duration | 2일 |
| 작업 위치 | worktree `wt/run-source-citations`, 브랜치 `feature/agent-run-source-citations` (미커밋) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 93.4% (Check 91.1% → Act-1)     │
├─────────────────────────────────────────────┤
│  ✅ FR 완료:       15 / 15                    │
│  ✅ SC 충족:        6 / 7 (SC-2 부분 충족)    │
│  ⏳ 이월:          화면 확인, L3 실런 5건      │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 실행의 검색 근거와 도구 결과는 DB에 저장되지만 답변과 화면에 전달되지 않아, 사용자가 답변을 원문과 대조할 수 없었다. |
| **Solution** | 실행 기록에서 근거를 조립하는 정책 하나를 만들고, WS 답변 이벤트와 인증된 세션 근거 API가 같은 정책을 쓰게 했다. 쓰기 경로와 DB 스키마는 바꾸지 않았다. |
| **Function/UX Effect** | 실제 실행 3회에서 웹 근거 5건, MCP 근거 1건(같은 도구 3회 호출을 1건으로 합침), 위키 근거 1건이 칩으로 표시됐고, 세션을 다시 열었을 때 같은 칩이 같은 순서로 복원됐다. 문서·도구 칩은 발췌를 펼치고, 웹 칩은 원문을 새 탭으로 연다. |
| **Core Value** | P1·P4가 에이전트 답변 아래에서 근거의 종류와 출처를 바로 확인하고 원문과 대조할 수 있게 됐다 (S2 "근거 배지 → 원문 대조"). |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 실시간·재진입 칩 일치 | ✅ Met | 실런 3회 모두 WS `sources`와 `GET .../sources` 응답이 종류·라벨·순서·URL까지 같음 |
| SC-2 | 4종 근거 표시·발췌·이동 | ⚠️ Partial | 웹·MCP·위키는 실런 확인. 내부 문서는 로컬 Qdrant 실데이터가 없어 과거 DB 기록으로만 확인. 브라우저 화면 확인 미실시 |
| SC-3 | 부작용·실패 MCP 제외 | ✅ Met | 정책 테스트(승인 필요·action·실패·빈 결과·`Error executing tool`), 실 DB 오류 호출 런에서 제외 확인 |
| SC-4 | 조회 실패 시 답변 정상 | ✅ Met | 서비스·리더·유스케이스·API·훅 실패 테스트 |
| SC-5 | 근거 없으면 미표시 | ✅ Met | payload 키 생략, 컴포넌트 빈 목록 미렌더 |
| SC-6 | 웹훅·백그라운드 불변 | ✅ Met | AST 계약 `test_only_ws_route_opts_in`, `execute()` 미전달 |
| SC-7 | 일반 채팅 회귀 없음 | ✅ Met | 기존 `SourceCitation` 테스트 4건 무수정 통과 |

**Success Rate**: 6/7 충족, 1건 부분 충족 (86%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 근거 원천은 실행 기록 (`collected_sources` 미사용) | ✅ | 서브에이전트 기록까지 포함되고 과거 런도 복원됨 |
| [Plan] | 호출자 opt-in (`include_sources`, 기본 False) | ✅ | WS 경로만 조회. 웹훅·백그라운드 응답과 쿼리 수 불변 |
| [Design] | Option C (순수 정책 + 공유 서비스) | ✅ | 두 경로가 같은 코드를 지나 SC-1을 구조로 보장 |
| [Design] | 재진입은 인증 전용 API | ✅ | 기존 비인증 대화 API에는 발췌를 싣지 않음 |
| [Design] | MCP 제외 방식 | ✅ | `category`가 전부 비어 있는 현재 카탈로그에서도 MCP 칩이 표시됨 |
| [Design] | 발췌는 실행한 본인에게 표시 | ✅ | 토큰 사용자 세션만 조회 |
| [Do] | 문서 중복 제거를 파일명 우선으로 변경 | 편차 | 실데이터에서 같은 파일 재업로드로 칩 3~4개가 겹치는 문제를 발견해 수정, Design 갱신 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [agent-run-source-citations.plan.md](../01-plan/features/agent-run-source-citations.plan.md) | ✅ v0.2 |
| Design | [agent-run-source-citations.design.md](../02-design/features/agent-run-source-citations.design.md) | ✅ v0.1 (+문서 중복 제거 갱신) |
| Check | [agent-run-source-citations.analysis.md](../03-analysis/agent-run-source-citations.analysis.md) | ✅ v0.2 |
| Act | 현재 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | `ANSWER_COMPLETED.sources` (정상·승인 대기·강등, 차단 턴 제외) | ✅ | |
| FR-02 | 실시간·재진입 단일 정책 | ✅ | `_make_run_sources_service` 공유 |
| FR-03 | 종류별 중복 제거 | ✅ | 문서는 파일명 우선 (편차 기록) |
| FR-04 | 상한 N, 종류 라운드로빈 | ✅ | `AGENT_RUN_SOURCES_MAX_ITEMS=6` |
| FR-05 | 문서 라벨 폴백 | ✅ | `document_metadata` 일괄 조회 |
| FR-06 | 웹 제목·링크 | ✅ | |
| FR-07 | 위키 근거·이동 | ✅ | `ai_tool_call`에서 조립, 머리글 계약 테스트 |
| FR-08 | MCP 제외 규칙·표시 이름 | ✅ | key는 `mcp:{srv}:{tool}` (Act-1) |
| FR-09 | 인증 세션 근거 API, 일괄 조회 | ✅ | |
| FR-10 | 마지막 런·id 순 짝짓기 | ✅ | turn index 수정 전 데이터 포함 |
| FR-11 | 실패 흡수 | ✅ | 유스케이스 정책 단계 예외까지 (Act-1) |
| FR-12 | 호출자 opt-in | ✅ | |
| FR-13 | 프론트 타입·스트림·병합 | ✅ | |
| FR-14 | 종류 텍스트, 에이전트 근거 점수 숨김 | ✅ | 문서 칩 순번 (Act-1) |
| FR-15 | 발췌 패널·안전한 링크 | ✅ | |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 호환성 | 기존 소비자 무변경 | 기존 테스트 무수정 통과, 신규 필드 전부 optional | ✅ |
| 성능 | 쿼리 횟수 고정 | 런 묶음 조회는 메서드당 쿼리 1회 | ✅ |
| 크기 | 발췌 상한 | 기록 시 상한(500바이트·1KB) 그대로 | ✅ |
| 보안 | HTML 미해석·위험 URL 차단·내부 필드 비노출 | 테스트로 고정 | ✅ |
| 접근성 | 키보드·`aria-expanded`·텍스트 종류 표시 | RTL 테스트 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 근거 정책 | `idt/src/domain/agent_run/source_policy.py` | ✅ |
| 서비스·리더 | `idt/src/application/agent_run/run_sources.py`, `idt/src/infrastructure/agent_run/run_sources_reader.py` | ✅ |
| 세션 근거 API | `get_session_sources_use_case.py`, `agent_run_router.py` | ✅ |
| 프론트 칩·병합 | `SourceCitation.tsx`, `useChat.ts`, `utils/sessionSources.ts`, `utils/safeUrl.ts` | ✅ |
| 테스트 | 백엔드 신규 9파일, 프론트 신규 4파일 | ✅ |
| 문서 | Plan·Design·Analysis·Report | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority |
|------|--------|----------|
| 브라우저 화면 확인 | CORS가 `main.py`에 `localhost:5173`으로 고정되어 있고, 해당 포트를 다른 세션의 개발 서버가 사용 중 | High |
| 내부 문서 실런 (L3-1) | 로컬 Qdrant에 실데이터 없음 | Medium |
| L3-4~8 실런 (MCP 실패, 승인 도구, 서브에이전트, 조회 실패, 웹훅) | 단위·계약 테스트로만 확인 | Medium |
| `.env.example`에 `AGENT_RUN_SOURCES_MAX_ITEMS` 추가 | 세션 정책상 수기 반영 | Low |
| #2 `agent-run-feedback-wiring`과 병합 | master 작업트리에서 미커밋 진행 중. `run_agent_use_case.py`와 프론트 4개 파일 충돌 예상 | High |

### 4.2 범위 밖에서 발견한 기존 문제

| Item | 내용 |
|------|------|
| 대화 이력 API 인증 없음 | `conversation_history_router.py` 전체가 `user_id` 쿼리만으로 대화를 반환한다 |
| `[출처: unknown]` | `rag_agent/tools.py:431`이 저장되지 않는 `source` 키를 읽는다. 저장된 225건 중 `source` 키 0건 |
| MCP 실패가 SUCCESS로 기록 | `MCPToolAdapter`가 `isError`를 보지 않는다. MCP 호출 170건 중 50건 |
| 웹 발췌 품질 | 저장된 앞 500바이트라 일부 페이지는 본문 대신 시세표·메뉴 텍스트가 나온다 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| Design Match Rate | 90% | 93.4% | Check 91.1% → +2.3 |
| Structural / Functional / Contract | - | 100 / 100 / 100% | 97 / 96 / 100 → |
| Runtime | - | 81.3% | 78.9 → |
| Security Issues | 0 Critical | 0 | ✅ |
| 백엔드 회귀 | 0 | 0 (상시 실패 53건 동일) | ✅ |
| 프론트 회귀 | 0 | 0 (Vitest 상시 9건, `tsc` 209, `eslint` 34 동일) | ✅ |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| 같은 파일 재업로드 문서 칩 중복 (실데이터) | 파일명 우선 중복 제거 | ✅ |
| 에이전트 문서 칩 순번 없음 | 순번 배지 | ✅ |
| 닫힌 칩의 `aria-controls` | 열린 칩에만 부여 | ✅ |
| 세션 API 정책 단계 예외 500 | 유스케이스 흡수 | ✅ |
| MCP key 표기 불일치 | 카탈로그 `tool_id` 사용 | ✅ |
| 테스트 누락 3종 | 승인 대기·ChatPage 연결·API 실패 테스트 추가 | ✅ |

---

## 6. Lessons Learned

### 6.1 Keep

- Design 전에 로컬 DB를 직접 조회해 가정을 확인했다. 히스토리 API 무인증, `source` 키 0건, MCP 실패 29%, `category` 전부 비어 있음을 미리 발견해 쓰기 경로 변경을 통째로 없앴다.
- 배선 직후 실제 DB 기록으로 서비스를 돌려, mock 테스트가 놓친 문서 칩 중복을 Do 단계에서 잡았다.
- 진행 중인 다른 작업과 파일이 겹쳐 별도 worktree에서 작업했다. 병합 충돌 지점을 미리 파악해 두었다.

### 6.2 Problem

- gap-detector 에이전트가 턴 한도에 걸려 한 번 멈췄고, 쓰기 권한이 없어 보고서를 파일로 남기지 못했다. 결과를 메시지로 받아 직접 옮겼다.
- 개발 서버 포트와 하드코딩된 CORS 때문에 화면 확인을 못 했다.

### 6.3 Try

- 화면 확인이 필요한 사이클은 Plan 단계에서 사용할 포트와 서버를 정해 둔다.
- gap-detector에게는 처음부터 범위를 좁히고 "메시지로 보고"를 지시한다.

---

## 7. Next Steps

1. 브라우저에서 에이전트 답변 칩·발췌·웹 링크·위키 이동, 세션 재진입을 확인한다.
2. #2 커밋 뒤 이 브랜치를 rebase하고 `_answer_payload` 계약에 맞춰 충돌을 푼다.
3. 커밋·PR 후 `/pdca archive agent-run-source-citations`.
4. 범위 밖 문제 중 대화 이력 API 인증은 별도 사이클로 다룬다.

---

## 8. Changelog

### 2026-11-03

**Added:**
- 에이전트 답변 근거 칩 (문서·위키·웹·도구), 발췌 패널, 웹 원문 링크
- `GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/sources` (인증 필수)
- WS `agent_answer_completed.sources` (optional)
- `AGENT_RUN_SOURCES_MAX_ITEMS` 설정 (기본 6)

**Changed:**
- 일반 채팅 문서 칩도 발췌를 펼친다 (점수 표시 유지)
- `DocumentSource.score`를 optional로 변경, `kind`·`url` 추가

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-03 | Completion report created | 배상규 |
