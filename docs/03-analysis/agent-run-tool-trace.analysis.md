# agent-run-tool-trace Analysis Report

> **Summary**: 설계 대비 구현 일치율 97.5%(런타임 포함). Critical·Important 갭 0건, Minor 6건 중 4건 수정(G-01·G-04·G-05·G-06), 2건 유지(G-02·G-03, 도달 불가). 375·768 폭 화면 확인만 미완료.
>
> **Project**: sangplusbot (Agent Builder)
> **Date**: 2026-11-04
> **Plan**: [agent-run-tool-trace.plan.md](../01-plan/features/agent-run-tool-trace.plan.md)
> **Design**: [agent-run-tool-trace.design.md](../02-design/features/agent-run-tool-trace.design.md)
> **Branch**: `feature/agent-run-tool-trace` (worktree `wt/agent-run-tool-trace`, 미커밋)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 도구 입력·결과는 WS로 전송되고 DB에도 저장되지만 화면에 표시되지 않는다. 사용자는 도구가 값을 실제로 가져왔는지 알 수 없다. |
| **WHO** | P2 KB 운영자·에이전트 소유자(주), P1 여신 심사역·P4 일반 사용자(보조). |
| **RISK** | 도구 결과에 포함된 개인정보·민감정보 노출, 타인 세션 열람, 2026-05에 raw JSON 노출을 제거한 결정과 같은 가독성 문제 재발, 실시간과 재진입 표시 불일치. |
| **SUCCESS** | 실시간과 재진입의 내역 순서·항목 일치, MCP 포함 실런 표시, 타인 세션 0건 노출, 답변 흐름 비차단, 기존 경로 회귀 0건. |
| **SCOPE** | M1 표시 정책 → M2 세션 도구 내역 API → M3 실시간 경로 → M4 프론트 접이식 내역·드릴다운 |

---

## Strategic Alignment Check

### 문제 해결 여부

사용자의 원래 질문은 "도구(MCP 포함)로 가져오는 값이 순서대로 보이지 않아 실제로 가져오는지 모르겠다"였다. 구현 후 채팅 답변 아래에서 추론 → 도구 → 추론 순서와 각 도구의 입력·결과를 볼 수 있고, 세션을 다시 열어도 같은 내역이 나온다. 실 MCP 호출(`list_inquiries`)로 화면에서 확인했다. 문제는 해결됐다.

### Success Criteria Status (Plan §4)

| 기준 | 상태 | 근거 |
|------|:----:|------|
| FR-01~FR-16 구현 | ✅ (2건 의도적 조정) | §2.2. FR-13 원문 토글은 래퍼를 벗긴 문자열을 보여 준다(G-05), FR-14 "승인 대기"는 "승인 후 실행" 배지로 대체(Design §10) |
| 정책 단위 테스트 (정렬·이름·오류 본문·래퍼·잘림·워커) | ✅ | `tests/domain/agent_run/test_tool_trace_policy.py` 43건 |
| 실시간·재진입 동일성 테스트 | ✅ | `tests/application/agent_run/test_tool_trace_live_session_parity.py` + 실런 `identical=True` |
| 실 LLM·실 MCP 1회 실런 | ✅ | 에이전트 `6cdf4932`, `list_inquiries` (2026-11-03, WS TestClient) |
| 세션 재진입 화면 확인 | ✅ | 화면에서 기존 세션 재진입 시 "도구 실행 내역 (1)" 복원 확인 |
| 백엔드·프론트 회귀 0건 (FAILED diff) | ✅ | 백엔드 53건 = master 53건, 프론트 9건 = master 9건(목록 동일) |
| 신규 백엔드 커버리지 80% 이상 | ✅ | 신규 6개 모듈 99% (307 statements, 1 miss) |
| 신규 컴포넌트 커버리지 60% 이상 | ⚠️ 미측정 | `@vitest/coverage-v8` 미설치. 컴포넌트 테스트 11건·유틸 19건으로 대체 |
| lint·tsc | ✅ | 변경 파일 lint 6건 = master 6건, `tsc -p tsconfig.app.json` 209건 = master 209건 |
| 라우터는 TestClient 실요청 | ✅ | `tests/api/test_session_tool_traces_api.py` + 실제 앱 openapi 등록 확인 |

### Decision Record Verification

| 결정 | 따랐는가 | 결과 |
|------|:-------:|------|
| [Plan] 답변별 접이식, 근거 칩 다음 | ✅ | `MessageBubble.tsx` |
| [Plan] 정리 표시 + 원문 토글 | ✅ | `ToolTraceEntry.tsx`, `toolTraceFormat.ts` |
| [Plan] 요청 사용자 본인 세션·전체 도구 | ✅ | `SessionAnswerRunsResolver` 소유 필터, 정책은 승인·action·실패를 거르지 않음 |
| [Plan] 재진입 복원 | ✅ | 세션 API + `useAgentSessionMessages` 3방향 병합 |
| [Plan] 추론 혼합 / 하단 패널 유지 / 평면+워커 라벨 | ✅ | R-01·R-08, `ToolPreviewPanel` 무변경 |
| [Design] 설계안 C (근거 칩 구조 모방, 카탈로그 조회 공유) | ✅ | `ToolCatalogLookup` 추출 후 근거 테스트 무수정 통과 |
| [Do] 연속된 판단 줄은 저장 그대로 표시 | ✅ | 병합하지 않음 |

---

## 1. Analysis Overview

- 정적 분석: gap-detector(설계 문서와 코드만 제공, 결론 비공개). 파일:라인 근거 포함.
- 런타임: pytest·vitest 전체, 실 LLM·MCP WS 실런, 브라우저 화면 확인.
- 범위: 백엔드 16개 파일, 프론트 13개 파일 (Design §11.1).

## 2. Gap Analysis

### 2.1 API Endpoints

| Endpoint | Design | 구현 | 상태 |
|---|---|---|:-:|
| `GET /api/v1/conversations/agents/{a}/sessions/{s}/tool-traces` | §4.2 | `agent_run_router.py` `get_session_tool_traces` | ✅ |
| WS `agent_answer_completed.data.tool_trace` | §4.3 | `run_agent_use_case.py` `_attach_tool_trace` (일반·강등 2곳) | ✅ |

### 2.2 Functional Depth

| 항목 | 결과 |
|---|---|
| Design 규칙 R-01~R-10 | 10/10 |
| Plan FR-01~FR-16 | 14 Met + 2 Partial(의도적 조정) |
| Page UI Checklist §5.4 | 15/15 |

### 2.3 API Contract (3-way)

18개 필드의 이름·필수 여부·None/false 생략 규칙, wire 값(reasoning/tool, success/failed, internal/mcp)이 정책 `to_payload` ↔ REST 스키마 ↔ `types/toolTrace.ts`에서 일치한다.

gap-detector가 미확인으로 남긴 "REST `exclude_none`이 `input` 안의 `null`까지 지우는가"는 실측으로 확인했다. 지우지 않는다(WS·REST 모두 `{"opt": null, "nested": {"k": null}}`). 동일성 유지.

### 2.7 Runtime Verification

| 레벨 | 내용 | 결과 |
|---|---|:-:|
| L1 | 본인 200·타인 빈 200·미인증 401·도구 0건 빈 목록·저장소 실패 빈 200·쿼리 수 고정 | 6/6 (TestClient) + 실서버 401 확인 |
| L2 | 헤더 펼침·도구 행 드릴다운·원문 토글·실패 항목·HTML 텍스트 렌더·키보드 | 컴포넌트 테스트 11/11, 화면에서 펼침·드릴다운·토글 확인 |
| L3 | MCP 에이전트 질문 → 내역 → 재진입, UUID 라벨 없음 | 실런 `identical=True`, 화면 실시간·재진입 확인. **375·768 폭 미확인** |

### 2.8 Match Rate

| 축 | 점수 |
|---|:-:|
| Structural | 100% |
| Functional | 97% |
| Contract | 100% |
| Runtime | 95% (모바일 폭 화면 미확인) |
| **Overall** | **97.5%** = 100×0.15 + 97×0.25 + 100×0.25 + 95×0.35 |

## 3. 갭 목록

Critical·Important 0건 (확신도 80% 이상 기준).

| ID | 심각도 | 내용 | 근거 | 처리 (v0.2) |
|---|---|---|---|---|
| G-01 | Minor (확신 70%) | 도구 기록이 `STARTED`로 남으면(종료 갱신 실패·취소) "실패"와 일반 문구로 보인다 | `usage_callback.py:270-276`, `tool_trace_policy.py:192` | ✅ 수정 — `ToolTraceStatus.INCOMPLETE`(wire `incomplete`) 추가, 화면은 "완료 기록 없음"과 결과 미표시. 테스트 2건 |
| G-02 | Minor | 헤더 N은 상한 안에 남은 도구만 센다. 잘린 도구는 "외 N건"에만 반영 | `ToolTraceList.tsx:18` | 유지 — 상한 50, 실데이터 최대 15라 도달 불가 |
| G-03 | Minor | 상한 절단 후 추론만 남으면 WS에 키는 실리지만 화면은 숨김 | 정책 `:165-166` | 유지 — 무해 |
| G-04 | Minor | 실패 항목·입력 없음에서도 "원문 보기" 버튼이 보이지만 바뀌는 것이 없다 | `ToolTraceEntry.tsx:130` | ✅ 수정 — 입력이 있거나 성공 결과가 JSON일 때만 토글 표시. 테스트 1건 |
| G-05 | Minor (문서) | Plan FR-13은 "저장된 문자열"을, 코드·Design §5.4는 래퍼를 벗긴 문자열을 원문으로 보여 준다 | `ToolTraceEntry.tsx:81` | ✅ Design v0.2 §10 알려진 한계에 추가 |
| G-06 | Minor (문서) | Design §9.4는 함수 `resolve_session_answer_runs`, 코드는 클래스 `SessionAnswerRunsResolver` | `session_answer_runs.py:22` | ✅ Design v0.2 표기 수정 |

## 4. 이번 변경과 무관한 관찰 (화면 확인 중 발견)

- 스트리밍 중 supervisor 라우팅 JSON이 토큰으로 노출된다.
- 하단 "추론 진행" 패널이 UUID 런타임 도구 이름을 표시한다.
- 끝에 거의 같은 supervisor 판단이 2줄 연속 나온다(종료 판단 2회).

후속 소형 사이클 후보로 이월한다 (`conventions/explicit-gap-carryover.md`).

## 5. Test Coverage

| 영역 | 결과 |
|---|---|
| 백엔드 신규 6개 모듈 | 99% (`run_tool_trace.py` 97%, 나머지 100%) |
| 프론트 신규 파일 | 미측정 (`@vitest/coverage-v8` 미설치) |
| 신규 테스트 수 | 백엔드: 정책 43·조회 7·서비스 8·연결 7·유스케이스 4·API 6·리더 3·실행 10·동일성 1·저장소 2. 프론트: 유틸 19·컴포넌트 11·훅 6·페이지 1·말풍선 2 |

## 6. Clean Architecture

도메인 정책은 DB·LangChain·application을 import하지 않는다(AST 테스트로 고정). 레이어 배치는 Design §9.4 13행 모두 일치.

## 9. Recommended Actions

1. G-04: 원문 토글을 바뀔 내용이 있을 때만 표시 (프론트 1파일).
2. G-01: `STARTED` 기록은 "완료 기록 없음"으로 구분 (정책 1곳 + 프론트 문구).
3. G-05·G-06: Design 문서 수정.
4. 375·768 폭 화면 확인 (메모리 여유가 있을 때 worktree 서버 재기동 후).

## 10. Design Document Updates Needed

- §9.4·§2.1: `resolve_session_answer_runs` → `SessionAnswerRunsResolver` (G-06)
- §10 알려진 한계: 원문 보기는 래퍼를 벗긴 문자열 (G-05)

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-11-04 | 초안 — gap-detector 정적 분석 + 런타임 검증 통합 |
| 0.2 | 2026-11-04 | Minor 4건 수정 반영. 관련 테스트 백엔드 428건·프론트 282건 통과, lint·tsc 신규 0 |
