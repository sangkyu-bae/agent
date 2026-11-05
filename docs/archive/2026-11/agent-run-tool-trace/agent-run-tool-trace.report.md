# agent-run-tool-trace Completion Report

> **Summary**: 에이전트 답변 아래에 그 실행의 추론과 도구 호출(MCP 포함)을 시간 순서로 접어 두고, 호출별 입력·결과를 펼쳐 볼 수 있게 했다. 세션을 다시 열어도 같은 내역이 복원된다.
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Period**: 2026-11-03 ~ 2026-11-04
> **Branch**: `feature/agent-run-tool-trace` — PR #89 머지(2026-11-04), 2026-11-05 아카이브
> **Status**: Completed (Match Rate 97.5%)

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| 기능 | 답변별 도구 실행 내역(드릴다운)과 세션 재진입 복원 |
| 출발점 | 사용자 요청: "도구(MCP 포함)로 가져오는 값이 순서대로 보이지 않아 실제로 가져오는지 알 수 없다" |
| 범위 | 백엔드 표시 정책·세션 API·실시간 payload, 프론트 접이식 내역·드릴다운 |
| 데이터 | 새 테이블·컬럼·마이그레이션 없음. 기존 `ai_tool_call`·`ai_run_step`만 읽는다 |

### 1.2 Results Summary

| 항목 | 결과 |
|------|------|
| Match Rate | 97.5% (구조 100 · 기능 97 · 계약 100 · 런타임 95) |
| Critical·Important 갭 | 0건 |
| Minor 갭 | 6건 중 4건 수정, 2건 유지(도달 불가) |
| 회귀 | 백엔드 실패 53건 = master 53건, 프론트 실패 9건 = master 9건 (목록 동일) |
| 실런 | 실 LLM·실 MCP(`list_inquiries`) WS 1회, 실시간 payload와 세션 API 응답 동일 |
| 화면 확인 | 실시간·재진입·드릴다운·원문 토글 확인. 375·768 폭은 미확인 |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | 도구 입력·결과는 WS로 전송되고 DB에도 저장되지만 화면에 표시되지 않았다. 하단 패널은 스트리밍 중에만 도구 이름과 소요 시간을 보여 주고 답변이 끝나면 사라졌다. |
| **Solution** | 실행 기록을 시간 순서의 내역으로 조립하는 도메인 정책 1개를 두고, 답변 완료 payload(`tool_trace`)와 세션 API가 같은 서비스를 지나게 했다. 근거 칩(PR #86)과 같은 구조를 따르고 카탈로그 이름 조회와 메시지·런 연결만 공유했다. |
| **Function/UX Effect** | 답변 아래 "도구 실행 내역 (N)"을 펼치면 판단 → 도구 → 판단 순서가 보이고, 도구를 펼치면 입력(키: 값)과 결과(정리된 JSON·텍스트), 원문, 잘림 표시, 실패 사유를 볼 수 있다. MCP 도구는 UUID 대신 카탈로그 이름으로 보인다. |
| **Core Value** | 에이전트 소유자(P2)가 채팅 화면에서 도구 연결이 실제로 값을 가져오는지 확인할 수 있다. 관리자 런 상세 화면을 열지 않아도 된다. |

## 1.4 Success Criteria Final Status

| 기준 (Plan §4) | 상태 | 근거 |
|------|:----:|------|
| FR-01~FR-16 구현 | ✅ | 14건 충족, 2건 의도적 조정(FR-13 원문=래퍼 제거 문자열, FR-14 승인 대기→"승인 후 실행" 배지). Design v0.2 §10에 기록 |
| 정책 단위 테스트 | ✅ | `tests/domain/agent_run/test_tool_trace_policy.py` 44건 |
| 실시간·재진입 동일성 테스트 | ✅ | `test_tool_trace_live_session_parity.py` + 실런 `identical=True` |
| 실 LLM·실 MCP 1회 실런 | ✅ | 2026-11-03, `list_inquiries` |
| 세션 재진입 화면 확인 | ✅ | 기존 세션 재진입 시 내역 복원 확인 |
| 회귀 0건 (FAILED diff) | ✅ | 백엔드·프론트 모두 master와 실패 목록 동일 |
| 신규 백엔드 커버리지 80% 이상 | ✅ | 99% |
| 신규 컴포넌트 커버리지 60% 이상 | ⚠️ | 미측정(`@vitest/coverage-v8` 미설치). 컴포넌트 테스트 13건으로 대체 |
| lint·tsc | ✅ | 신규 오류 0 |
| 라우터 TestClient 실요청 | ✅ | `tests/api/test_session_tool_traces_api.py` |

**Success Rate**: 9/10 충족, 1건 미측정.

## 1.5 Decision Record Summary

| 단계 | 결정 | 따랐는가 | 결과 |
|------|------|:-------:|------|
| Plan | 답변별 접이식(근거 칩 다음), 기본 접힘 | ✅ | 2026-05 raw JSON 제거 결정의 가독성 문제를 피하면서 값을 보여 줌 |
| Plan | 정리 표시 + 원문 토글 | ✅ | 원문은 래퍼를 벗긴 문자열(저장 dump는 의미 없음) |
| Plan | 본인 세션·전체 도구(승인·action·실패 포함) | ✅ | "가져왔는지" 판단에 실패 호출까지 필요 |
| Plan | 재진입 복원, 추론 혼합, 하단 패널 유지, 평면+워커 라벨 | ✅ | 모두 구현 |
| Design | 설계안 C: 근거 칩 구조 모방 | ✅ | 실시간과 재진입이 같은 서비스를 지나 구조적으로 일치 |
| Design | 정렬은 step_index 기준 | ✅ | DATETIME 초 단위라 시각만으로는 순서가 안 섬(실데이터 D9) |
| Design | supervisor 요약만 추론 | ✅ | 다른 노드 요약은 내부 메모(실데이터 D5) |
| Do | 연속된 판단 줄은 저장 그대로 | ✅ | 실제 판단 횟수 보존 |
| Check | `STARTED` 기록은 `incomplete`로 구분 | ✅ | 실패로 단정하지 않음(실데이터 발생 0건) |

---

## 2. Related Documents

| 단계 | 문서 |
|------|------|
| Plan | `docs/01-plan/features/agent-run-tool-trace.plan.md` |
| Design | `docs/02-design/features/agent-run-tool-trace.design.md` (v0.2) |
| Analysis | `docs/03-analysis/agent-run-tool-trace.analysis.md` (v0.2) |
| 선행 | `docs/archive/2026-05/agent-chat-reasoning-display/`, `agent-run-source-citations` (PR #86) |

## 3. Completed Items

### 3.1 Functional Requirements

| ID | 내용 | 상태 |
|----|------|:----:|
| FR-01 | 정책 1곳, 실시간·재진입 공유 | ✅ |
| FR-02 | 추론·도구 시간 순서 혼합 | ✅ |
| FR-03 | 사람이 읽는 도구 이름, UUID 비노출 | ✅ |
| FR-04 | 승인·action·실패 포함, MCP 오류 본문은 실패 | ✅ |
| FR-05 | `unwrap_tool_summary` 재사용 | ✅ |
| FR-06 | 잘림 표시 | ✅ |
| FR-07 | 서브에이전트 워커 라벨 | ✅ |
| FR-08 | 세션 API, 인증, 타인 세션 빈 200 | ✅ |
| FR-09 | user 메시지당 마지막 런 | ✅ |
| FR-10 | 실패 흡수 + warning | ✅ |
| FR-11 | 실시간 경로 (`ANSWER_COMPLETED.tool_trace`, 기존 preview 유지) | ✅ |
| FR-12 | 접힌 헤더, 도구 0건이면 미표시 | ✅ |
| FR-13 | 키: 값·정리된 JSON·원문 토글·텍스트 렌더 | ✅ (원문 정의 조정) |
| FR-14 | 아이콘+텍스트 상태 | ✅ (승인 대기→"승인 후 실행", `incomplete` 추가) |
| FR-15 | 하단 패널 유지 | ✅ |
| FR-16 | 메시지 id 병합 | ✅ |

### 3.2 Non-Functional Requirements

| 항목 | 결과 |
|------|------|
| 세션 API 쿼리 수 고정 | 메시지 1 + 런 1 + 도구 호출 1 + step 1 + 카탈로그 1 (테스트 단언) |
| 타인 세션 0건 | 사용자·에이전트 이중 필터, 테스트 단언 |
| 텍스트 렌더 | 신규 컴포넌트에 `dangerouslySetInnerHTML`·마크다운 렌더러 없음, `<script>` 텍스트 표시 테스트 |
| additive 계약 | 새 응답 타입·optional 키만 추가, 기존 소비자 무변경 |
| 접근성 | `button` + `aria-expanded`, 키보드 조작 테스트 |

### 3.3 Deliverables

| 영역 | 산출물 |
|------|--------|
| 도메인 | `tool_trace_policy.py`, `RunToolTraceReaderPort`, `find_steps_by_runs` |
| 애플리케이션 | `ToolCatalogLookup`(근거 서비스에서 추출), `RunToolTraceService`, `SessionAnswerRunsResolver`(근거 유스케이스에서 추출), `GetSessionToolTracesUseCase` |
| 인프라·인터페이스 | `SessionScopedRunToolTraceReader`, 응답 스키마 4종, 라우트, DI, config `agent_run_tool_trace_max_items=50` |
| 실행 경로 | `RunAgentUseCase._attach_tool_trace` (일반·강등 완료), `include_tool_trace`(기본 False, WS만 True) |
| 프론트 | `types/toolTrace.ts`, `utils/toolTraceFormat.ts`, `utils/sessionToolTraces.ts`, `ToolTraceList`·`ToolTraceEntry`, 스트림 훅·세션 병합·메시지 배치 |
| 문서 | Plan, Design v0.2, Analysis v0.2, 본 보고서 |

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| 항목 | 이유 | 처리 |
|------|------|------|
| 375·768 폭 화면 확인 | Chrome 창 최대화로 크기 조정 불가, 이후 메모리 부족으로 worktree 서버 중단 | 머지 전 또는 머지 후 5173에서 확인 |
| 프론트 신규 파일 커버리지 측정 | `@vitest/coverage-v8` 미설치(설치 시 `package.json` 변경) | 커버리지 도구 도입 시 측정 |
| 스트리밍 중 supervisor 라우팅 JSON 노출 | 이번 변경과 무관한 기존 동작 | 별도 소형 사이클 후보 |
| 하단 "추론 진행" 패널의 UUID 런타임 이름 | 기존 동작. 이번 `ToolCatalogLookup`을 재사용하면 해결 가능 | 별도 소형 사이클 후보 |
| 거의 같은 판단 줄 2회 연속 | supervisor가 종료 판단을 두 번 내리는 기존 동작 | 관찰 지속 |

### 4.2 Cancelled/On Hold Items

| 항목 | 이유 |
|------|------|
| G-02 헤더 N에 잘린 도구 포함 | 상한 50, 실데이터 최대 15라 도달 불가 |
| G-03 상한 절단 후 추론만 남는 경우 | 화면에 영향 없음 |
| 승인 대기(미실행) 호출 표시 | 실행 전이라 `ai_tool_call` 행이 없음. 승인 기능 쪽 과제 |

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 항목 | 값 |
|------|----|
| Match Rate | 97.5% |
| 백엔드 신규 모듈 커버리지 | 99% (307 statements, 1 miss) |
| 신규 테스트 | 백엔드 약 90건, 프론트 약 40건 |
| 백엔드 전체 | 11311 passed, 실패 53 = master |
| 프론트 전체 | 1662건 중 실패 9 = master |

### 5.2 Resolved Issues

| ID | 내용 | 해결 |
|----|------|------|
| G-01 | `STARTED` 기록이 "실패"로 보임 | `incomplete` 상태 추가, "완료 기록 없음" 표시 |
| G-04 | 바뀌는 내용이 없는데 원문 토글 노출 | 입력이 있거나 성공 결과가 JSON일 때만 표시 |
| G-05 | 원문 정의가 Plan과 다름 | Design v0.2 §10에 기록 |
| G-06 | 설계 표기와 클래스명 불일치 | Design v0.2 수정 |
| Do 중 | 세션 근거 유스케이스 추출 시 기존 테스트가 빈 목록 호출을 고정 | 동작을 그대로 유지해 기존 테스트 무수정 통과 |

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- 실DB 표본을 Design 단계에서 먼저 확인해 규칙을 정했다. dump 래퍼, `{"arguments": …}` 래퍼, 성공으로 기록된 MCP 오류 본문, supervisor 요약만 자연어라는 사실이 그대로 규칙 R-01~R-06이 됐다.
- 근거 칩의 구조를 따라 실시간과 재진입이 같은 서비스를 지나게 해서, 두 화면 일치를 테스트 1개와 실런 1회로 확인할 수 있었다.
- 공유 코드를 추출할 때 기존 테스트를 고치지 않는 것을 기준으로 삼아 근거 칩 회귀를 막았다.
- gap-detector에 결론을 주지 않고 문서·코드만 넘겨, 독립된 시각으로 갭 6건을 받았다. 미확인 2건은 실측으로 닫았다.

### 6.2 What Needs Improvement (Problem)

- 화면 확인 환경 준비에 시간이 들었다. 포트 8001의 IPv6를 Docker가 점유해 CORS 오류로 보였고, 로그인 계정 이메일 3개가 끝 글자만 달라 다른 사용자로 로그인됐다.
- 개발 토큰 주입은 권한 확인에 막혀 사용자 허용이 필요했다.
- gap-detector가 턴 한도에 걸려 보고서를 쓰지 못했고, 쓰기 도구도 없었다.

### 6.3 What to Try Next (Try)

- worktree 화면 확인용 실행 스크립트(127.0.0.1 바인딩, CORS 래퍼, Vite 환경변수)를 고정해 두고 재사용한다.
- 화면 확인 전에 로그인 계정을 `/auth/me`로 먼저 확인한다.
- gap-detector에는 확인 범위를 더 좁혀 주고, 보고서는 응답 본문으로 받는다.

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

- Design 단계 실데이터 확인(D1~D9 표)은 다른 "표시" 기능에도 기본 절차로 둘 만하다.
- Do 모듈 경계에 실런 1회를 두는 방식(module-3 완료 조건)이 fake 테스트가 못 잡는 문제를 확인하는 데 유효했다.

### 7.2 Tools/Environment

- 프론트에 `@vitest/coverage-v8`이 없어 커버리지 기준(60%)을 측정할 수 없다. 도입 여부를 정해야 한다.
- 앱 CORS 허용 목록이 5173으로 고정돼 있어 worktree 화면 확인 때마다 우회가 필요하다.

## 8. Next Steps

### 8.1 Immediate

1. 커밋·PR (`feature/agent-run-tool-trace`)
2. 375·768 폭 화면 확인
3. 머지 후 `/pdca archive agent-run-tool-trace`, worktree 정리

### 8.2 Next PDCA Cycle

| 후보 | 내용 |
|------|------|
| 하단 패널 도구 이름 | `ToolCatalogLookup`으로 UUID 런타임 이름을 표시 이름으로 |
| 스트리밍 중 라우팅 JSON 노출 | supervisor 토큰을 스트림에서 제외 |

## 9. Changelog

### v1.0.0 (2026-11-04)

**Added:**
- 답변별 "도구 실행 내역" 접이식 목록과 호출별 입력·결과 드릴다운, 원문 토글
- `GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/tool-traces`
- `agent_answer_completed.data.tool_trace` (WS, optional)
- 도구 상태 `success` / `failed` / `incomplete`
- config `agent_run_tool_trace_max_items` (기본 50)

**Changed:**
- 근거 서비스의 카탈로그 이름 조회를 `ToolCatalogLookup`으로, 세션 메시지·런 연결을 `SessionAnswerRunsResolver`로 추출 (동작 무변경)

**Fixed:**
- 없음

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-04 | 완료 보고서 작성 | 배상규 |
