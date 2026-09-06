# worker-context-injection Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Completion Date**: 2026-09-03
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | worker-context-injection |
| Start Date | 2026-09-03 |
| End Date | 2026-09-03 |
| Duration | 1일 (단일 세션) |
| Phases | Plan → Design → Do(module-1,2 → module-3) → Check → Act ×2 → Report |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100%                       │
├─────────────────────────────────────────────┤
│  ✅ Complete:     10 / 10 FR                 │
│  ✅ Gap 해소:      3 / 3 (Critical 0)        │
│  ⏳ 판단 대기:     2 관찰사항 (스펙 외)       │
│  ❌ Cancelled:     0                         │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 워커 react agent가 `system_prompt=datetime_block`만 받고 생성되어(`workflow_compiler.py`), 에이전트 시스템 프롬프트·자신의 역할·현재 작업 지시를 모른 채 대화 원문만 보고 도구를 호출했다. 그 결과 스크래핑 MCP 도구에 `https://www.example.com/financial-market-2026-09-03` 같은 실재하지 않는 URL이 전달됐다. |
| **Solution** | ① 전 워커 노드(react·wiki·search·analysis·생성 노드 4종)에 [에이전트 지침 + 역할 + 도구 규범] 정적 주입, ② `SupervisorDecision.task`로 매 라우팅마다 구체적 작업 지시 전달, ③ MCP 도구 실행 직전 플레이스홀더 인자 하드가드 + run step 관측. |
| **Function/UX Effect** | 더미 URL이 MCP 서버에 도달하기 전 100% 차단(`call_tool.assert_not_called()` 검증). 워커 프롬프트에 에이전트 지침·역할 포함률 0% → 100%. 차단 사실이 실행 이력 `output_summary`로 노출돼 운영자가 "왜 결과가 비었나"를 추적 가능. |
| **Core Value** | 컨텍스트 유실로 인한 도구 환각 제거 — supervisor→worker 경계에서 새던 4개 유실 축을 모두 막았다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 워커 system_prompt에 에이전트 프롬프트·역할 포함 100% | ✅ Met | `test_worker_context_injection.py::test_general_worker_receives_agent_prompt_and_role` — `assert AGENT_PROMPT in prompt`, `assert SCRAPE_DESC in prompt` |
| SC-2 | example.com류 더미 URL 호출 0건 | ✅ Met | `test_tool_adapter_guard.py::test_blocks_placeholder_url_without_calling_server` — `mock_session.call_tool.assert_not_called()` |
| SC-3 | TDD 사이클 준수 (테스트 선작성 → 실패 확인 → 구현) | ✅ Met | 전 모듈에서 Red 확인 후 구현 (31→0, 3→0, 10→0, 5→0, 8→0, 2→0, 7→0, 6→0) |
| SC-4 | `/verify-architecture`·`/verify-logging`·`/verify-tdd` 통과 | ✅ Met | 변경분 기준 전항목 통과. 검출 항목은 전부 사전 존재 |
| SC-5 | 기존 회귀 없음 | ✅ Met | 전체 8670 passed / 58 failed. 58건은 baseline과 동일 집합 (`comm -13` 공집합) |

**Success Rate: 5/5 (100%)**

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | Option C — 실용 균형 (domain 정책 분리 + 기존 렌더러 재사용) | ✅ | 신규 2 / 수정 6 파일로 완결. 과설계 없이 레이어 규칙 준수 |
| [Plan] | URL 결정 주체 = MCP 서버 해석 (tool_config 고정 미채택) | ✅ | `tool_config` URL 고정 미구현 — Out of Scope 준수. 단 §O-2 전제 미검증으로 남음 |
| [Plan] | 환각 가드: 소프트 + 하드 + 관측 | ✅ | 프롬프트 규범 + `_arun` 차단 + `logger.warning` + run step `output_summary` 3중 |
| [Plan] | 모든 tool 워커 공통 적용 | ✅ | Act 2회를 거쳐 react·wiki·search·analysis·생성 노드 4종 전부 주입 |
| [Design] | 차단 = 지시성 오류 문자열 (예외 아님) | ✅ | `build_blocked_message` 반환. 워커가 자기 교정 가능 (`test_worker_can_recover_after_block`) |
| [Design] | 프롬프트 전문 주입 + 2000자 상한 절단 | ✅ | `MAX_AGENT_PROMPT_CHARS = 2000`, 초과 시 `…(에이전트 지침 일부 생략)` 표기 |
| [Design] | task는 react agent 워커에만 전달 | ✅ | `_build_worker_input`이 `_wrap_worker` 경로에서만 호출 |
| [Design] | 블록 배치 순서 (datetime → context → 기존 지시) | ✅ | `test_context_block_precedes_toc_block` 통과. 기존 지시 문자열 무변경 |
| [Design] | `localhost`/`127.0.0.1` 차단 목록 제외 | ✅ | 사내 로컬 대상 오탐 방지. §3.2 근거 기록 + `test_returns_false_for_localhost`로 고정 |

**의도적 스펙 축소 1건** — Plan FR-07이 열거한 `localhost`/`127.0.0.1`을 제외했다. 실익보다 오탐 위험이 크다는 판단이며 Design §3.2에 근거를 남기고 테스트로 계약을 고정했다.

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [worker-context-injection.plan.md](../01-plan/features/worker-context-injection.plan.md) | ✅ Finalized (v0.1) |
| Design | [worker-context-injection.design.md](../02-design/features/worker-context-injection.design.md) | ✅ Finalized (v0.2) |
| Check | [worker-context-injection.analysis.md](../03-analysis/worker-context-injection.analysis.md) | ✅ Complete (v0.3, Match Rate 100%) |
| Act | 현재 문서 | ✅ Complete |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|:------:|-------|
| FR-01 | 워커 컨텍스트 블록 렌더러 신설 | ✅ | `render_worker_context_block()` + `include_tool_norm` 파라미터 |
| FR-02 | 모든 tool 워커에 `datetime → context` 순 주입 | ✅ | 빈 값이면 인자 미전달 — 기존 호출 형태 보존 |
| FR-03 | 자체 프롬프트 보유 노드도 블록 수신, 기존 지시 무변경 | ✅ | wiki·search·analysis·생성 노드 4종. Act 2회 소요 |
| FR-04 | `SupervisorDecision.task` 필드 추가 | ✅ | `default=""` — 구조화 출력 누락 시에도 그래프 정상 동작 |
| FR-05 | `worker_task` 상태 전달 + 폴백 | ✅ | 3개 반환 경로에서 초기화. `_build_worker_input`이 무조건 append |
| FR-06 | 소프트 가드 (URL 추측 금지 지침) | ✅ | `_TOOL_USAGE_NORM`, 도구 보유 워커에만 |
| FR-07 | 플레이스홀더 인자 하드가드 | ✅ | 예약 호스트 11종, 정확·서브도메인 일치만 (부분 문자열 오탐 방지) |
| FR-08 | 차단 구조화 로그 | ✅ | `request_id`/`tool_id`/`server`/`tool`/`reason`/`blocked_value` |
| FR-09 | 차단 사유 run step 추적 반영 | ✅ | `BLOCKED_PREFIX` domain 상수 → `_blocked_step_summary()` → `STEP_OUTPUT_SUMMARY_KEY` |
| FR-10 | 플레이스홀더 정책 domain 분리 | ✅ | `domain/mcp/tool_argument_policy.py` — 외부 의존 0 |

**10/10 완료.**

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|:------:|
| 토큰 증가 | 워커 1회당 ≤ 600 tokens | 상한 2000자(≈500 tokens) + 절단 정책으로 보장 | ✅ |
| 회귀 | 기존 테스트 전량 통과 | 8670 passed, 신규 실패 0건 | ✅ |
| 아키텍처 | domain → infrastructure 참조 금지 | 0건. 신규 방향은 application → domain 하나 | ✅ |
| 로깅 | print 없음, 스택 트레이스 보존 | print 0건, `exception=e` 유지 | ✅ |
| 하위호환 | `task` 미제공 시 기존 동작 | 폴백 문구 + `default=""` | ✅ |
| 함수 길이 | 40줄 이하 | `_wrap_worker` 36, `_build_worker_input` 27, `_blocked_step_summary` 27 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|:------:|
| 도메인 정책 | `src/domain/mcp/tool_argument_policy.py` (신규) | ✅ |
| 컨텍스트 렌더러 | `src/application/agent_run/prompt_rendering.py` | ✅ |
| 그래프 배선 | `src/application/agent_builder/workflow_compiler.py` | ✅ |
| supervisor task | `src/application/agent_builder/supervisor_nodes.py` / `supervisor_state.py` | ✅ |
| search 파이프라인 | `src/application/agent_builder/search_pipeline.py` / `src/application/deep_search/workflow.py` | ✅ |
| 생성기 계약 | `document_extractor/composer.py`, `document_generator/generator.py`, `excel_generator/generator.py`, `blueprint/generation_use_case.py` | ✅ |
| MCP 가드 | `src/infrastructure/mcp/tool_adapter.py` | ✅ |
| 테스트 | 신규 6 파일 / 87 케이스 | ✅ |
| PDCA 문서 | `docs/01-plan` · `02-design` · `03-analysis` · `04-report` | ✅ |

**규모**: 신규 2 / 수정 11 파일, +321 / −37줄 (테스트 포함).

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| **O-1** 워커에 `user_context_block` 미전달 | 스펙 위반이 아님(FR-01은 "에이전트 시스템 프롬프트"로 정의). 별도 판단 필요 | Medium | 0.5일 |
| **O-2** MCP 서버 도구 스키마 검증 | Design §12 Open Item #1 — "URL 결정 주체 = MCP 서버" 전제가 미검증 | **High** | 0.5일 (조사) |
| **O-3** `MAX_AGENT_PROMPT_CHARS` 실측 조정 | DB `agents.system_prompt` 길이 분포 미확인 | Low | 0.5일 |

### 4.2 Cancelled/On Hold Items

| Item | Reason | Alternative |
|------|--------|-------------|
| `tool_config` 기반 스크래핑 URL 고정 | Plan §2.2 Out of Scope — "URL 해석은 MCP 서버 책임" 결정 | O-2 조사 결과에 따라 재검토 |
| `localhost`/`127.0.0.1` 차단 | 사내 로컬 대상 스크래핑 오탐 위험 > 실익 | 필요 시 정책 상수에 추가 (1줄) |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Initial | Final | Change |
|--------|--------|---------|-------|--------|
| Design Match Rate | 90% | 94.5% | **100%** | +5.5%p |
| — Structural | — | 100% | 100% | — |
| — Functional | — | 85% | 100% | +15%p |
| — Contract | — | 100% | 100% | — |
| — Runtime | — | 95% | 100% | +5%p |
| 미해소 Gap | 0 | 3 | **0** | −3 |
| 전체 테스트 통과 | 회귀 0 | 8635 | 8670 | +35 |
| 신규 실패 | 0 | 0 | **0** | — |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|:------:|
| 워커가 에이전트 프롬프트·역할 미수신 (유실 축 ①②) | `render_worker_context_block()` 정적 주입 | ✅ |
| supervisor→worker 작업 지시 부재 (유실 축 ③) | `SupervisorDecision.task` + `worker_task` 상태 | ✅ |
| `ensure_user_tail` no-op으로 첫 턴 지시 유실 (유실 축 ④) | `_build_worker_input`이 무조건 append | ✅ |
| 근거 없는 URL이 MCP 서버 도달 | `ToolArgumentPolicy` 하드가드 | ✅ |
| 차단이 실행 이력에 안 보임 | domain 상수 접점 → `output_summary` | ✅ |
| function 노드 컨텍스트 미주입 | 6개 노드에 블록 배선 | ✅ |
| 차단 루프 계약 미고정 | `TestBlockDoesNotLoop` 2건 | ✅ |

### 5.3 설계 단계에서 발견한 결함

Design 작성 중 **Plan에 없던 네 번째 유실 축**을 발견했다.

`ensure_user_tail`은 마지막 메시지가 user면 no-op이다(`message_normalization.py:35-37`). 첫 워커 호출 시 메시지 끝은 사용자 질문이므로, 기존 `"당신의 역할에 해당하는 작업을 수행하세요"` 지시문은 **첫 호출에서 한 번도 전달된 적이 없었다.** task를 `instruction` 인자로만 넘겼다면 이번 수정도 동일하게 무력화됐을 것이다.

→ 지시는 무조건 append하고 `ensure_user_tail`은 본래 역할(prefill 방어)만 맡도록 설계했고, `test_appends_task_when_tail_is_user_message`로 회귀를 고정했다.

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **코드를 먼저 읽고 질문했다.** Plan 착수 전 `workflow_compiler.py`·`supervisor_nodes.py`를 읽어 유실 축 3개를 코드 근거(`file:line`)로 특정한 뒤 질문했다. 덕분에 추측 기반 질문이 아니라 결정이 필요한 4가지만 물을 수 있었다.
- **Design 단계가 실제로 결함을 잡았다.** `ensure_user_tail` no-op(§5.3)은 구현 중에 발견했다면 "왜 안 되지"로 시간을 태웠을 문제다. 설계 문서에 함수 계약을 적어보는 과정에서 드러났다.
- **TDD가 계약 변경을 드러냈다.** 기존 테스트 3건(`test_generic_worker_without_tz_has_no_system_prompt` 등)이 깨진 것은 버그가 아니라 **FR-02가 의도적으로 바꾼 계약**이었다. Red가 없었으면 조용히 지나쳤을 신호다.
- **baseline 대조로 회귀를 증명했다.** "58건 실패"를 그냥 보고하지 않고 `git stash` + `comm -13`으로 신규 실패 0건임을 집합 수준에서 확인했다.

### 6.2 What Needs Improvement (Problem)

- **Gap 분석에 사실 오류가 있었다.** `analysis` 노드를 "블록 미주입"으로 적었으나 실제로는 이미 `workflow.supervisor_prompt`를 받고 있었다(역할만 미주입). 분기 순서만 보고 판단했고 각 팩토리 시그니처를 확인하지 않은 탓이다. → Act 단계에서 정정.
- **`git stash` 중 타임아웃으로 작업분이 갇혔다.** baseline 비교를 위해 stash한 뒤 두 번째 전체 스위트 실행이 10분 타임아웃에 걸려 `stash pop`이 실행되지 않았다. 즉시 복구했지만, **작업분을 stash한 상태에서 장시간 명령을 실행한 것이 잘못**이다.
- **문자열 치환 스크립트가 조용히 실패했다.** `_plan_sheets` 시그니처 변경이 `\n\n` 이스케이프 문제로 적용되지 않아 excel 테스트 14건이 깨졌다. 치환 후 검증 없이 다음 단계로 넘어갔다.
- **Plan의 FR-03 범위가 모호했다.** "document_*"가 4개 노드를 뜻하는지, 프롬프트 훅이 없는 경우 어떻게 할지 명시하지 않아 Act가 2회로 나뉘었다.

### 6.3 What to Try Next (Try)

- **Gap 분석 시 분기 순서가 아니라 시그니처를 확인한다.** "이 노드가 X를 받는가"는 호출부 인자를 직접 봐야 한다.
- **`git stash` 상태에서는 짧은 명령만 실행한다.** 장시간 검증은 stash 없이, 또는 worktree로 분리한다.
- **치환 스크립트에 `assert count == 1`을 붙인다.** 이번에 일부 치환에는 붙였는데 excel `_plan_sheets`에는 빠졌다. 예외 없이 적용한다.
- **Plan의 요구사항에 "훅이 없으면 어떻게 할지"를 명시한다.** 확장 범위 FR은 대상 목록과 함께 불가 시 처리 방침을 적는다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 확장 범위 FR의 적용 대상이 모호 | FR에 "대상 목록 + 불가 시 처리 방침" 명시 |
| Design | 잘 작동함 — 함수 계약 기술 중 결함 발견 | 유지. 계약 기술을 필수 절로 |
| Do | 문자열 치환 스크립트 검증 누락 | 치환 후 즉시 `grep` 확인을 절차화 |
| Check | 분기 순서 기반 추론으로 오판 | 각 소비처의 실제 인자를 확인한 뒤 판정 |
| Act | 잘 작동함 — Check의 오류를 정정 | 유지 |

### 7.2 Tools/Environment

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| 테스트 | 전체 스위트 5~6분 — 반복 실행이 부담 | 변경 영향 범위 기반 선택 실행 규약 정립 |
| 테스트 격리 | `test_run_agent_use_case_observability.py` 5건이 단독 통과·전체 실패 | 별도 이슈로 등록 — 이번 변경과 무관하나 회귀 판정을 흐린다 |
| 사전 존재 실패 | 58건이 상시 실패 상태 | 격리 마킹(`xfail`)하거나 수정해 회귀 신호를 선명하게 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] **O-2 조사** — 문제의 스크래핑 MCP 서버가 노출하는 도구 인자 스키마 확인 (`/verify-mcp-connections`). "URL 결정 주체 = MCP 서버" 전제의 성립 여부를 가른다
- [ ] 재현 시나리오 실환경 검증 — 해당 커스텀 에이전트에 "현재 분기 리포트 작성해주세요" 입력 후 로그에서 `MCP tool call blocked` 발생 여부 확인
- [ ] `/pdca archive worker-context-injection`

### 8.2 Next PDCA Cycle

| Item | Priority | 근거 |
|------|----------|------|
| O-2 후속: MCP 도구 스키마에 맞춘 인자 전달 설계 | High | 설계 전제 미검증 상태 |
| O-1: 워커 `user_context_block` 전달 여부 결정 | Medium | "내 부서 기준으로" 류 요청에서 필요 |
| 테스트 격리 문제 해결 (58건 사전 존재 실패) | Medium | 회귀 판정 신뢰도 |
| O-3: `MAX_AGENT_PROMPT_CHARS` 실측 조정 | Low | 절단 빈도 미측정 |

---

## 9. Changelog

### worker-context-injection (2026-09-03)

**Added:**
- `ToolArgumentPolicy` (domain) — 플레이스홀더 URL 판정, 인자 트리 재귀 순회, 차단 안내 문구, `BLOCKED_PREFIX`/`is_blocked_message`
- `render_worker_context_block()` — 에이전트 지침·역할·도구 목록·사용 규범 블록 (`include_tool_norm` 토글)
- `SupervisorDecision.task` / `SupervisorState.worker_task` — supervisor→worker 작업 지시 채널
- `_build_worker_input()` / `_blocked_step_summary()` / `_tool_names()` (workflow_compiler)
- `worker_context_block` 파라미터 — `create_search_pipeline_node`, `create_deep_search_node`, `DocumentComposer.compose`, `DocumentGenerator.generate`, `ExcelGenerator.generate`, `PresentationGenerationUseCase.generate`
- 테스트 6 파일 / 87 케이스

**Changed:**
- 워커 `system_prompt`가 날짜 블록만 받던 것 → 에이전트 지침·역할·도구 규범 포함
- supervisor 결정 프롬프트에 `task` 작성 지시 추가
- `_wrap_worker`가 `ensure_user_tail`의 `instruction`에만 의존하던 것 → 작업 지시 무조건 append

**Fixed:**
- 워커가 근거 없는 URL을 합성해 MCP 서버로 전송하던 문제
- `ensure_user_tail` no-op으로 첫 워커 호출 시 지시문이 전달되지 않던 문제
- 도구 차단이 실행 이력에 남지 않던 관측 공백

**Breaking:** 없음 — 신규 파라미터는 전부 기본값을 가지며 미배선 호출부는 기존 동작을 유지한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-03 | 완료 보고서 작성 — Match Rate 100%, SC 5/5, Gap 0건 | 배상규 |
