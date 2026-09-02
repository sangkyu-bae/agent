# fix-mcp-tool-call-not-reaching-server Completion Report

> **Status**: Complete (SC-01 최종 확인만 사용자 실행 대기)
>
> **Project**: sangplusbot / idt (FastAPI + LangGraph, Thin DDD)
> **Author**: 배상규
> **Completion Date**: 2026-09-02
> **PDCA Cycle**: Plan → Design → Do(module 1~3) → Check → Act

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | fix-mcp-tool-call-not-reaching-server |
| Start Date | 2026-09-02 |
| End Date | 2026-09-02 |
| Duration | 1 세션 (Plan → Report) |
| 트리거 | "실제 에이전트에서 `mcp_081c6fe7-…` 도구 호출 시 MCP 서버로 요청이 안 들어온다" |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Design Match Rate: 84.4% → 96.4%           │
├─────────────────────────────────────────────┤
│  ✅ 완료:      FR 7건 중 7건                 │
│  ✅ Gap 해소:  3 / 3 (Critical 1 포함)       │
│  ⏳ 대기:      SC-01 실서버 E2E (사용자 실행) │
│  ❌ 취소:      0                             │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | 워커에 MCP 서버를 붙였는데 도구 호출이 서버에 도달하지 않고, 실패가 조용해 원인 추적이 불가능했다 |
| **Solution** | 계측을 수정보다 앞세워 차단 지점을 실측으로 확정(D1) → 레거시 서버 단위 ID가 서버 도구 **전체**를 바인딩하도록 변경 + 도구명 64자 정합 + 배선 회귀 가드 |
| **Function/UX Effect** | 대상 워커가 바인딩하는 도구 **1개 → 3개** (`scrape_url` 외에 `scrape_urls`·`extract_structured` 사용 가능). 실패 시 로그 8종으로 ①생성/②등록/③실행 중 차단 지점 즉시 판별 |
| **Core Value** | "붙였는데 조용히 아무 일도 안 일어남"이 "어디서 왜 끊겼는지 로그 한 줄로 보임"으로 바뀌었다 |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-01 | 지정 도구의 요청이 MCP 서버에 실제 수신 | ⚠️ Partial | 바인딩·연결 실측 완료(Scrap MCP `list_tools` 3개 수신, 520ms). **에이전트 실행을 통한 `call_tool` 수신은 사용자 실행 필요** |
| SC-02 | 차단 지점을 로그로 특정 가능 | ✅ Met | §4 로그 8종 전건 구현. `exposed_name_len`·`requested_tool`·`server_level`·`fallback`·`bound_tools` |
| SC-03 | FR-03/04/05/06에 테스트 존재·통과 | ✅ Met | 신규 26건 (policy 8 / factory 17 / compiler 4 / adapter 4 / registry 2 / wiring 6, 중복 제외) |
| SC-04 | 기존 MCP 테스트 회귀 없음 | ✅ Met | 전체 스위트 3회 측정 — 실패 **58건 불변**, 통과 8570(변경 전) → 8578(module 1~3) → **8583**(Gap 수정 후). 실패 파일 분포 동일 |
| SC-05 | 코드 주석으로 설계 역추적 가능 | ✅ Met | `# Design Ref: §N` 주석 6개 파일 |

**Success Rate: 4/5 Met + 1 Partial (80% 완전 충족)**

---

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | tool_id 두 형식 모두 지원 (마이그레이션 없음) | ✅ | 레거시 에이전트 무중단. 카탈로그가 발급하는 신규 형식도 정상 동작 |
| [Plan] | inputSchema 노출은 별도 사이클 | ✅ | 범위 유지. Design §6.3에 한계로 명시 — 다음 사이클 후보 1순위 |
| [Plan] | **계측을 수정의 선행 게이트로** | ✅ | **가장 큰 성과.** 실측이 D1을 확정하고 D2를 강등시켜 추정 수정을 막았다 |
| [Design] | Option C 실용 균형 (신규 프로덕션 모듈 0) | ⚠️ 부분 | 프로덕션 신규 1개(`domain/mcp/exceptions.py`) — Gap G-01 수정에 필요했고 17줄 예외 정의뿐 |
| [Design] | 도구명 규칙은 domain policy에 | ✅ | `hashlib`(표준)만 추가, 레이어 위반 없음 |
| [Design] | 실패는 워커 단위 격리, 배선 오류는 예외 | ⚠️→✅ | 초안 구현이 배선 오류까지 삼켜 Gap G-01 발생 → `McpWiringError`로 수정 |
| [Design v0.2] | E6: 첫-도구 폴백 → **서버 도구 전체 바인딩** | ✅ | module-1 실측 후 사용자 승인 하에 변경. 이것이 실제 증상 수정 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [fix-mcp-tool-call-not-reaching-server.plan.md](../01-plan/features/fix-mcp-tool-call-not-reaching-server.plan.md) | ✅ v0.1 + §1.2.1 실측 반영 |
| Design | [fix-mcp-tool-call-not-reaching-server.design.md](../02-design/features/fix-mcp-tool-call-not-reaching-server.design.md) | ✅ v0.2 (E6 변경 반영) |
| Check | [fix-mcp-tool-call-not-reaching-server.analysis.md](../03-analysis/fix-mcp-tool-call-not-reaching-server.analysis.md) | ✅ v0.2 (96.4%) |
| Act | 본 문서 | 🔄 작성 |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|:------:|-------|
| FR-01 | 3구간에 `request_id`/`tool_id`/`mcp_tool_name` 로그 | ✅ | 로그 8종, module-1 |
| FR-02 | 차단 구간이 ①/②/③ 중 하나로 확정 | ✅ | **D1 확정** — 실측으로 원인 특정 |
| FR-03 | `mcp:{srv}:{tool}`은 지정 도구에 정확히 바인딩 | ✅ | `create_all_async` |
| FR-04 | 레거시는 첫 도구 폴백 + 경고 | 🔄 대체 | **전체 바인딩으로 대체** — 폴백 자체가 사라져 요구가 무의미해짐 (Design v0.2 §6.3) |
| FR-05 | 노출 도구명 64자 이하 + 서버 내 유일 | ✅ | `build_tool_name`, sha1 접미사 |
| FR-06 | 런타임 ToolFactory 배선을 테스트가 고정 | ✅ | 뮤테이션으로 가드 작동 검증 |
| FR-07 | 도구 생성 실패가 compile 전체를 죽이지 않음 | ✅ | 워커 단위 격리 + 배선오류 예외 |

### 3.2 Non-Functional Requirements

| 항목 | 목표 | 달성 | 상태 |
|------|------|------|:---:|
| 관측성 (LOG-001) | 에러에 스택 트레이스 + `request_id` | 전 경로 `exception=e` 동반 | ✅ |
| 아키텍처 | domain → infrastructure 역참조 없음 | `policy.py`는 `hashlib`만 추가 | ✅ |
| 함수 40줄 | 신규/수정 함수 준수 | 13~36줄 | ✅ |
| 하위호환 | 레거시 tool_id 계속 동작 | `create_async` 유지 + 테스트 | ✅ |
| 테스트 선행 | Red 확인 후 구현 | 4개 모듈 전부 Red→Green 기록 | ✅ |

### 3.3 Deliverables

| 산출물 | 위치 | 상태 |
|--------|------|:---:|
| 도구명 정책 | `src/domain/mcp/policy.py` (`build_tool_name`, 상한 64) | ✅ |
| 배선 예외 | `src/domain/mcp/exceptions.py` (신규, `McpWiringError`) | ✅ |
| 도구 선택 | `src/infrastructure/agent_builder/tool_factory.py` (`create_all_async`) | ✅ |
| 연결·실행 계측 | `src/infrastructure/mcp/tool_registry.py`, `tool_adapter.py` | ✅ |
| 실패 격리 | `src/application/agent_builder/workflow_compiler.py` | ✅ |
| 배선 계약 테스트 | `tests/api/test_runtime_tool_factory_wiring.py` (신규) | ✅ |
| PDCA 문서 4종 | `docs/01-plan` · `02-design` · `03-analysis` · `04-report` | ✅ |

---

## 4. Incomplete Items

### 4.1 다음 사이클로 이월

| 항목 | 사유 | 우선순위 | 예상 |
|------|------|:---:|------|
| **MCP 도구별 `inputSchema` 노출** | Plan 단계에서 범위 분리 결정. 현재 모든 MCP 도구가 공통 `{arguments: dict}` 스키마라 LLM이 인수를 잘못 담을 수 있다 | **High** | 0.5~1일 |
| SC-01 실서버 E2E 확인 | 에이전트 실행이 필요 — 사용자 액션 | High | 10분 |
| `WorkflowCompiler.compile` 455줄 분해 | 기존 위반(약 427줄)이며 이번에 28줄 추가. 범위 밖 | Medium | 0.5일 |
| api 라우터 기존 실패 24건 (`AssembleAuthContextUseCase not initialized`) | MCP 범위 밖의 별개 DI 이슈 | Medium | 미산정 |

### 4.2 취소/보류

| 항목 | 사유 | 대안 |
|------|------|------|
| DB `agent_tool.tool_id` 일괄 마이그레이션 | 실패 시 기존 에이전트 전멸 위험 | 두 형식 동시 지원으로 대체 (Plan §7.2) |
| `McpToolNamePolicy`/`McpToolBinder` 신설 (Option B) | CLAUDE.md §6 "과도한 추상화 금지" | Option C — 기존 policy에 함수 1개 추가 |

---

## 5. Quality Metrics

### 5.1 최종 분석 결과

| 지표 | 목표 | 최종 | 변화 |
|------|:---:|:---:|:---:|
| Design Match Rate | 90% | **96.4%** | 84.4% → 96.4% (+12.0%p) |
| — Structural | — | 100% | 유지 |
| — Functional | — | 91% | 73% → 91% (+18%p) |
| — Contract | — | 100% | 88% → 100% (+12%p) |
| 미해결 Gap | 0 | **0** | 3 → 0 |
| 회귀 | 0 | **0** | 전체 스위트 3회 실패 58건 불변 (8570→8578→8583 통과) |
| 대상 워커 바인딩 도구 수 | — | **3개** | 1개 → 3개 |

### 5.2 해결된 이슈

| 이슈 | 해결 | 결과 |
|------|------|:---:|
| **D1** 레거시 ID가 서버 첫 도구에만 바인딩 | `create_all_async` — 서버 도구 전체 바인딩 | ✅ 실서버 3개 확인 |
| **D2** 도구명 상한 100자 vs OpenAI 64자 | `build_tool_name` — 64자 + sha1 접미사 | ✅ 현 서버명 불변(최장 59자), 충돌 예방 |
| **D3** 배선 회귀를 잡는 테스트 부재 | 배선 계약 테스트 6건 | ✅ 뮤테이션 검증 통과 |
| **G-01** 배선 오류가 격리되어 조용히 넘어감 | `McpWiringError` 전용 예외 + compiler re-raise | ✅ Critical 해소 |
| **G-02** 도구 미발견 에러에 도구명 목록 없음 | `(available: [...])` 추가 | ✅ 진단 1단계 단축 |
| **G-03** ③ 경로 세션 로그의 `request_id` 누락 | `create_session(config, request_id)` | ✅ 로그 체인 연결 |

### 5.3 변경 규모

| 구분 | 수치 |
|------|:---:|
| 프로덕션 수정 파일 | 5 (policy, tool_registry, tool_adapter, tool_factory, workflow_compiler) |
| 프로덕션 신규 파일 | 1 (`domain/mcp/exceptions.py`, 17줄) |
| 테스트 신규/수정 | 5 파일, 신규 26건 |
| 총 diff | 약 +1,318 / −71 (테스트 포함) |

---

## 6. Lessons Learned & Retrospective

### 6.1 Keep — 잘 된 것

- **계측을 수정의 선행 게이트로 둔 것이 이번 사이클의 핵심 성과였다.** 코드 리딩만으로는 결함 후보가 3개였고 각각의 증상 설명력이 갈렸다. 실측 없이 착수했다면 D2(도구명 64자)를 고치고 "증상이 그대로"라는 결과를 맞았을 가능성이 높다 — 실제로 D2는 이 서버에서 **미발생**이었다.
- **DB의 실제 워커 정의를 확인한 것이 결정타였다.** description은 3개 도구를 안내하는데 바인딩은 1개 — 이 불일치가 증상을 완전히 설명했다. 코드만 봤다면 "폴백은 의도된 설계"로 넘어갔을 수 있다.
- **뮤테이션 테스트로 가드의 실효성을 확인했다.** 배선 2줄을 지워 3건이 실패하는 것을 직접 본 뒤에야 "회귀를 잡는다"고 말할 수 있었다.
- 실측 결과가 Design 결정(E6)을 뒤집었고, 사용자 승인 후 문서를 v0.2로 갱신해 근거를 남겼다. 문서가 코드를 따라간 게 아니라 결정 이력이 보존됐다.

### 6.2 Problem — 개선 필요

- **Design §6.2의 "배선 오류는 격리하지 않는다"를 구현에서 놓쳤다(G-01).** `except Exception` 한 줄이 명시적 설계 결정을 무력화했고, 하필 이번 사이클이 없애려던 실패 모드를 재생산할 뻔했다. Design에 쓴 예외 조건을 구현 시 체크리스트로 만들지 않은 게 원인이다.
- **테스트가 Design보다 느슨했다(G-02).** `match="MCP tool not found"`만 확인해 "도구명 목록 포함" 요구를 통과시켰다. Design §8.2에 U7로 명시돼 있었는데도 테스트를 느슨하게 쓰면 Gap 분석 전까지 드러나지 않는다.
- **회귀 판정 범위를 명확히 하지 않고 "회귀 없음"이라고 말했다.** 타겟 스위트 기준이었는데 전체 스위트에는 기존 실패 58건이 있었다. 나중에 전후 비교로 무관함을 확정했지만, 처음부터 범위를 붙여 말했어야 했다.
- 작업트리가 세션 중 두 차례 되돌아가는 현상을 겪었다. Design §11.2에 브랜치 분리를 필수 선행으로 넣었으나 사용자 판단으로 master 진행 — 결과적으로 문제는 없었지만 리스크는 실재했다.

### 6.3 Try — 다음에 시도할 것

- **Design의 "하지 않는다" 조항을 구현 체크리스트로 전환한다.** §6.x의 부정형 결정(“~는 격리하지 않는다”)은 긍정형 요구보다 놓치기 쉽다. Do 단계 시작 시 부정형 조항만 따로 뽑아 확인.
- **에러 메시지 요구는 테스트에서 내용까지 단언한다.** `pytest.raises(match=...)`는 부분 일치라 느슨하다. 메시지에 담겨야 할 값을 `assert x in str(exc.value)`로 명시.
- **회귀 판정은 항상 "전체 스위트 전/후 비교"를 기준선으로 잡는다.** 변경 전 baseline을 먼저 기록하고 시작.
- 다음 사이클(inputSchema)에서는 실제 에이전트 실행 트레이스를 Phase 1 계측 대상에 포함해, LLM이 넘긴 인수를 직접 관측한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA 프로세스

| Phase | 현재 | 개선 제안 |
|-------|------|-----------|
| Plan | 코드 리딩 기반 결함 후보 나열 | **원인 미확정 시 "계측 선행"을 Plan 표준 패턴으로** — 이번에 효과가 입증됨 |
| Design | 부정형 결정이 산문에 섞임 | §6 에러 처리에 "격리 대상 / 비대상" 표를 분리해 구현 체크리스트화 |
| Do | 모듈별 세션 분할이 잘 작동 | module-1(계측·재현)을 독립 세션으로 두는 패턴 유지 — 실측이 후속 범위를 바꿨다 |
| Check | Gap 분석이 실제 Critical을 잡아냄 | 유지. 단 **테스트 자체의 느슨함**도 점검 항목에 추가 |

### 7.2 도구/환경

| 영역 | 개선 제안 | 기대 효과 |
|------|-----------|-----------|
| 테스트 | 전체 스위트 baseline을 `.bkit`에 스냅샷 저장 | 회귀 판정이 즉답 가능해짐 (이번엔 4분 재실행 필요) |
| 기존 실패 | parser 21 / retriever 7 / api DI 24건을 별도 이슈로 등록 | 58건 노이즈가 신규 회귀를 가린다 |
| MCP 진단 | `/verify-mcp-connections`에 서버별 **도구명 목록·길이**를 출력 추가 | D1/D2류 문제를 등록 시점에 조기 발견 |
| 리팩터링 | `WorkflowCompiler.compile` 455줄 분해 사이클 | 규칙 위반 해소 + 이후 변경 안전성 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-02 | 완료 보고 — Match Rate 96.4%, Gap 3건 전건 해소, 이월 4건 | 배상규 |
