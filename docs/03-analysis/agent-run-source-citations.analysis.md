# agent-run-source-citations Analysis Report

> **Analysis Type**: Gap Analysis (정적 + 런타임)
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Analyst**: 배상규
> **Date**: 2026-11-03
> **Design Doc**: [agent-run-source-citations.design.md](../02-design/features/agent-run-source-citations.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 근거는 저장되지만 에이전트 답변에 표시되지 않아 사용자가 답변을 원문과 대조할 수 없다. |
| **WHO** | P1 여신 심사역, P4 일반 사용자(최종 사용자). P2 에이전트 소유자는 답변 품질 확인에 활용한다. |
| **RISK** | MCP 결과의 근거 판별 오류와 민감정보 노출, 공유 에이전트에서 KB 권한이 없는 사용자에게 청크 발췌 노출, 검색 근거를 "실제 인용"으로 오해할 가능성. |
| **SUCCESS** | 실시간·재진입 칩 일치, 4종 근거의 실런 표시, 답변 흐름 비차단, 기존 경로 회귀 0건. |
| **SCOPE** | M1 근거 조립 정책 → M2 실시간 경로 → M3 세션 근거 API → M4 프론트 칩·발췌 패널 |

---

## Strategic Alignment Check

PRD 문서는 없다. 기준은 `docs/USER-SCENARIOS.md` P1·S2("근거 배지 → 원문 대조")이다.

| 요소 | 기대 | 상태 |
|------|------|:----:|
| 핵심 문제 | 에이전트 답변에 근거 표시 | ✅ 실런 3종에서 칩 표시 |
| 대상 사용자 | 에이전트 사용 본인 | ✅ 인증 API, 본인 세션만 |
| 원문 대조 | 발췌·원본 이동 | ✅ 발췌 패널, 웹 새 탭, 위키 이동 |

### Success Criteria Status

| # | 기준 | 상태 | 근거 |
|---|------|:----:|------|
| SC-1 | 실시간·재진입 칩 일치 | ✅ | 실런 3회(웹 5건, MCP 1건, 위키 1건) 모두 WS 근거와 재진입 API 응답이 종류·라벨·순서·URL까지 동일 |
| SC-2 | 4종 표시·발췌·이동 | ⚠️ | 웹·MCP·위키는 실런 확인. 내부 문서는 로컬 Qdrant 실데이터가 없어 과거 DB 기록으로만 확인. 화면 확인 미실시 |
| SC-3 | 부작용·실패 MCP 제외 | ✅ | 정책 단위 테스트 9건, 실 DB 오류 호출 런에서 제외 확인 |
| SC-4 | 조회 실패 시 답변 정상 | ✅ | 서비스·리더·유스케이스·훅 실패 테스트 (정책 단계 예외만 미흡수 — §2 결함 #3) |
| SC-5 | 근거 없으면 미표시 | ✅ | `run_agent_use_case.py` payload 키 생략, `SourceCitation` 빈 목록 null |
| SC-6 | 웹훅·백그라운드 불변 | ✅ | AST 계약 `test_only_ws_route_opts_in`, `execute()` 미전달 |
| SC-7 | 일반 채팅 회귀 없음 | ✅ | 기존 테스트 4건 무수정 통과, 점수·위키 이동 유지 |

**Success Rate**: 6/7 충족, 1건 부분 충족 (SC-2)

### Decision Record Verification

| Source | Decision | Followed? | 비고 |
|--------|----------|:---------:|------|
| Plan | 실행 기록을 근거 원천으로 사용 | ✅ | 쓰기 경로 변경 0 |
| Design | Option C (정책 + 공유 서비스) | ✅ | 실시간·재진입 모두 `_make_run_sources_service` |
| Design | MCP 제외 방식 | ✅ | |
| Design | 인증 전용 재진입 API | ✅ | 기존 비인증 API 무변경 |
| Design | 발췌는 실행 본인에게 표시 | ✅ | 토큰 사용자로만 조회 |
| Do | 문서 중복 제거를 파일명 우선으로 변경 | 편차(기록됨) | 실데이터에서 재업로드 문서 칩 중복 발견 |

---

## 1. Analysis Overview

- 정적 분석: gap-detector 에이전트(읽기 전용)
- 런타임: 실제 앱·DB·LLM·MCP를 쓰는 인프로세스 WS 실행 3회, 세션 근거 API 실호출
- 대상: worktree `wt/run-source-citations`, 브랜치 `feature/agent-run-source-citations`

---

## 2. Gap Analysis

### 2.1 FR 이행

FR-01~FR-15 전부 구현. 근거 위치는 gap-detector 보고서 §2와 같다. FR-11은 아래 결함 #3의 틈이 있다.

### 2.2 확인된 결함

| # | 심각도 | 위치 | 내용 | Act-1 결과 |
|---|--------|------|------|-----------|
| 1 | Important | `SourceCitation.tsx` | 에이전트 문서 칩에 번호가 없다. Design §5.4 "번호"와 다르다 | 수정 — `Ordinal` 배지 추가, 테스트 "문서 칩에 순번을 표시한다" |
| 2 | Minor | `SourceCitation.tsx` | 닫힌 칩의 `aria-controls`가 DOM에 없는 id를 가리킨다 | 수정 — 열린 칩에만 부여, 패널 존재 단언 테스트 |
| 3 | Minor | `get_session_sources_use_case.py` | `build_for_runs` 예외가 500이 된다 (Design §4.2는 200 `items: []`) | 수정 — try/warning, 유스케이스·API 테스트 |
| 4 | Minor | `source_policy.py` MCP key | `chunk_id`가 런타임 이름이다. Design §3.1은 `mcp:{srv}:{tool}` | 수정 — `McpToolInfo.tool_id`로 key 지정, 실 DB 응답에서 `mcp:6ea2f615-…:list_inquiries` 확인 |
| 5 | Minor | 테스트 | 승인 대기 런, ChatPage 연결(L2-12), API 수준 실패(L1-6) 테스트 없음 | 수정 — 3종 추가 (ChatPage 연결은 기존 코드로 바로 통과) |

### 2.3 API Contract

4/4 PASS — REST 세션 근거 경로·응답·항목 형태, WS `agent_answer_completed.sources`.

### 2.4 Runtime Verification

**L1 (실제 앱·DB)**

| # | Test | 결과 |
|---|------|:----:|
| 1 | 본인 세션 근거 조회 200 | ✅ |
| 2 | 토큰 없음 401 | ✅ |
| 3 | 라우트 OpenAPI 등록 | ✅ |
| 4 | 실시간 근거와 재진입 응답 일치 (3세션) | ✅ |

L1 = 4/4 = 100%

**L2 (브라우저 미실시, RTL로 대체)**: Design §8.3 12개 중 11개 테스트 존재(L2-12 ChatPage 연결 없음) = 92%

**L3 (Design §8.4)**

| # | Scenario | 결과 |
|---|----------|:----:|
| 1 | 문서 + 웹 | ⚠️ 웹만 실런 확인 |
| 2 | 위키 | ✅ |
| 3 | MCP 성공 | ✅ (3회 호출 → 칩 1개) |
| 4 | MCP 실패 제외 | 실런 미실시 (DB 기록·단위 테스트로 확인) |
| 5 | 승인 필요 도구 제외 | 실런 미실시 (단위 테스트) |
| 6 | 서브에이전트 | 실런 미실시 |
| 7 | 조회 실패 주입 | 실런 미실시 (단위 테스트) |
| 8 | 웹훅 불변 | 실런 미실시 (AST 계약) |

L3 = 실런 통과 3/8 = 37.5% (나머지는 단위·계약 테스트로만 확인)

**Runtime** = 100×0.4 + 92×0.3 + 37.5×0.3 = 78.9%

### 2.5 Match Rate Summary

**Check (초기)**

```
Structural:  97%   (Design §11.1 파일 30개 중 29개 확인)
Functional:  96%   (FR 15/15, §5.4 12항목 중 11 충족·1 부분)
Contract:   100%   (4/4)
Runtime:     78.9%
Overall = 97×0.15 + 96×0.25 + 100×0.25 + 78.9×0.35 = 91.1%
```

**Act-1 이후**

```
Structural: 100%   (handlers.ts 변경을 직접 확인)
Functional: 100%   (FR 15/15, §5.4 12/12)
Contract:   100%   (4/4)
Runtime:     81.3% (L1 100, L2 100 — RTL 12/12, L3 37.5 — 실런 3/8)
Overall = 100×0.15 + 100×0.25 + 100×0.25 + 81.3×0.35 = 93.4%
```

남은 차이는 L3 실런 미실시 5건과 브라우저 화면 확인이다 (§4).

---

## 3. 품질·보안

- 회귀(Act-1 이후 재실행): 백엔드 11,122 통과·실패 53건(상시 목록과 동일), 프론트 Vitest 1,535 통과·실패 9건(상시 4파일), `tsc` 209건·`eslint` 34건 기준선과 동일. 초기 Check 때 부하로 실패한 타이밍 테스트 1건은 재실행에서 통과
- 보안: 발췌는 텍스트 노드, URL은 서버·프론트 이중 검사, 내부 필드(`metadata_json`, `arguments_json`) 비노출, 기존 비인증 API 무변경
- 성능: 런 묶음 조회는 메서드당 쿼리 1회 (N+1 없음)

---

## 4. 이월·보류

- 브라우저 화면 확인 (CORS가 `localhost:5173` 고정, 해당 포트는 다른 세션이 사용 중)
- L3-1 내부 문서 실런 (로컬 Qdrant 실데이터 없음), L3-4~8 실런
- `.env.example`에 `AGENT_RUN_SOURCES_MAX_ITEMS` 수기 추가
- MCP 발췌의 PII 마스킹 적용 여부 (`pii-masking-integration`에서 판단)
- 기존 문제(범위 밖): `conversation_history_router.py` 비인증, `tools.py:431` `[출처: unknown]`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-03 | Initial analysis (91.1%) | 배상규 |
| 0.2 | 2026-11-03 | Act-1: 결함 5건 수정, 93.4% | 배상규 |
