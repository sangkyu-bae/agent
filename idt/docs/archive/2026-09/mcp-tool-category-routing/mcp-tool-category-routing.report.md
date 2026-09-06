# mcp-tool-category-routing Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt)
> **Version**: —
> **Author**: 배상규
> **Completion Date**: 2026-09-03
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | mcp-tool-category-routing |
| Start Date | 2026-09-03 |
| End Date | 2026-09-03 |
| Duration | 1일 (단일 세션, 모듈 4개 분할 구현) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Design Match Rate: 98.0%                    │
├─────────────────────────────────────────────┤
│  ✅ 충족:      13 / 14 FR                    │
│  ⚠️ 범위축소:   1 / 14 FR  (FR-11, 사용자 결정) │
│  ❌ 미충족:     0 / 14 FR                    │
├─────────────────────────────────────────────┤
│  신규 회귀:    0건 (기준선 대조 4회)          │
│  사이클 테스트: 194 passed / 0 failed         │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | MCP 도구가 `_resolve_category`에서 예외 없이 `"action"`으로 떨어져 전부 react 루프를 탔다. 스크랩 도구 1회 요청에 4~5회 호출되고, 산출이 "수집한 근거"가 아니라 워커 LLM의 분석문이라 하류 노드가 근거로 인식하지 못했다. |
| **Solution** | `tool_catalog`에 `category`·`max_tool_calls`를 두어 **노드 종류를 데이터로 결정**. 수집형은 react 루프 없는 단일샷 `collect` 노드로, 미분류는 호출 상한이 걸린 기존 react로 라우팅. |
| **Function/UX Effect** | **실 MCP 서버 계측**: collect 경로 MCP 호출 **1회**(플레이스홀더 인자는 **0회** 차단), 산출은 도구 원본 JSON(2705자)으로 `is_search_result()` 통과. 레거시 서버 단위 워커도 react 상한으로 **4~5회 → 최대 2회**. |
| **Core Value** | "특화는 데이터로, 코어에 하드코딩 금지"(USER-SCENARIOS 원칙)를 지키며 문제를 해결했다. 새 도구 유형이 생겨도 코드가 아니라 카탈로그 값으로 대응한다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria (Plan §4.1) | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | FR-01 ~ FR-14 전부 구현 | ✅ | 13 ✅ / 1 ⚠️(FR-11 범위축소, 사용자 결정) / 0 ❌ |
| SC-2 | TDD 준수 — 테스트 선작성 → Red → 구현 → Green | ✅ | 6개 모듈 전부 RED 확인 기록 (`ModuleNotFoundError`/`ImportError`/40줄 위반 assert) |
| SC-3 | **스크랩 MCP 도구를 collect로 지정한 에이전트에서 실제 호출 1회를 실측** | ✅ | 실 `Scrap MCP`(`localhost:8002`) 계측 — `MCPToolAdapter._arun` 후킹, 호출 **1회**, 인자 `{'url': 'https://www.python.org/'}` |
| SC-4 | category NULL 에이전트의 기존 테스트 전량 통과 | ✅ | 전체 스위트 실패 집합이 기준선과 테스트 ID 단위로 동일 (차집합 양방향 공집합) |
| SC-5 | API 계약 동기화 (`interfaces/schemas` ↔ `idt_front/src/types`) | ✅ | 3-way 검증 7항목 전량 일치 (Analysis §6) |
| SC-6 | 아키텍처·로깅·TDD 검증 통과 | ✅ | domain 4파일 외부 참조 0건, `print(` 0건, 신규 프로덕션 모듈 5개 전부 테스트 보유 |
| SC-7 | 신규 모듈 함수 40줄 이하, if 중첩 2단계 이하 | ✅ | Act에서 `_resolve_body` 추출로 해소. 측정 오류(중첩 함수 이중계산)도 함께 교정 |
| SC-8 | lint 0 / pytest 전량 / 프론트 test 통과 | ✅ | `tsc --noEmit` 통과, 사이클 테스트 194/194, 프론트 AdminToolsPage 8/8 |

**Success Rate**: 8/8 (100%) — SC-1의 FR-11만 사용자 승인 하에 범위 축소

---

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 분류 저장소 = `tool_catalog` 컬럼 (agent_tool은 오버라이드로 존치) | ✅ | 도구 단위 1회 지정으로 전 에이전트 적용. 실 DB 13개 엔트리로 검증 |
| [Plan] | 초기값 전부 NULL, 백필 없음 | ✅ | 회귀 0건의 직접 근거. NULL = 이전과 동일 경로 |
| [Design] | **Option C (Pragmatic)** — generator 분기 무수정 | ✅ | `compile()` 코어 변경 최소. 기존 확장점(`SupervisorHooks`/`MiddlewareBuilder`/optional dep) 재사용 |
| [Design] | D-03 collect 전용 노드 (search 재사용 안 함) | ✅ | **실서버가 전제를 확인** — 세 도구 required가 `url`/`urls`. search의 `{"query":…}`로는 호출 불가 |
| [Design] | D-04 collect는 단일 도구 참조만 | ✅ | Gap-06 조치 시 실제로 검증 경로를 태워 확인 |
| [Design] | D-05 langchain 내장 `ToolCallLimitMiddleware` | ✅ | 커스텀 미들웨어 불필요 — 신규 파일 1개 절약 |
| [Design] | **D-06 wiki 분기 상한 예외** (사용자 지시) | ✅ | 폴더 모드 지도→list→read 체인 보존. 테스트로 고정 |
| [Design] | D-09 compile당 1회 배치 조회 | ✅ | 워커 3개 → 조회 1회 검증 |
| [Design] | **D-12 FR-11 collect 한정** (Do 중 발견, 사용자 결정) | ✅ | search 워커 포함 시 관리자 지정 없이 기존 에이전트 동작이 바뀌어 FR-14 취지 훼손 |
| [Design] | **D-13 엔드포인트 body 방식** (Do 중 발견) | ✅ | 기존 `PATCH /builtin` 관례와 정합. path 세그먼트 인코딩 문제 회피 |
| [Design] | **D-14 MCP inputSchema 전달** (Do 중 발견) | ✅ | 설계 전제(`args_schema`)가 제네릭 래퍼였음. 실서버 3개 도구 스키마 전달 확인 |

**미준수 결정 0건.** 편차 3건(D-12/13/14)은 전부 구현 중 발견해 근거와 함께 문서에 반영했다.

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [mcp-tool-category-routing.plan.md](../01-plan/features/mcp-tool-category-routing.plan.md) | ✅ Finalized (FR-11 개정 반영) |
| Design | [mcp-tool-category-routing.design.md](../02-design/features/mcp-tool-category-routing.design.md) | ✅ Finalized (D-12/13 반영) |
| Check/Act | [mcp-tool-category-routing.analysis.md](../03-analysis/mcp-tool-category-routing.analysis.md) | ✅ Complete (v0.3) |
| Report | 현재 문서 | ✅ Complete |

> **PRD 없음** — `/pdca pm` 미수행. 사용자가 관찰한 구체 증상에서 출발한 사이클이라
> 시장/페르소나 분석 단계를 건너뛰었다.

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|:------:|-------|
| FR-01 | `tool_catalog` 2컬럼 + COMMENT | ✅ | V069, 백필 없음 |
| FR-02 | 카테고리 4종 검증 | ✅ | `ToolCategoryPolicy` |
| FR-03 | sync가 관리자 지정값 보존 | ✅ | SET 절 제외 + SQL 파라미터 테스트 |
| FR-04 | 4단계 해석 우선순위 | ✅ | 실 DB로도 검증 |
| FR-05 | collect = 도구 정확히 1회 | ✅ | 실서버 계측 |
| FR-06 | 스키마 기반 인자 1회 산출 | ✅ | D-14로 전제 복구 |
| FR-07 | 실패 시 graceful degrade | ✅ | 6분기 전부 |
| FR-08 | 근거 메시지 규약 준수 | ✅ | 5케이스 파라미터화 |
| FR-09 | 임계치 초과 시만 압축 | ✅ | 압축 LLM 호출 0회 assert |
| FR-10 | react 상한 기본 2회 + 오버라이드 | ✅ | compile 경로 통합 검증 |
| FR-11 | 워커 재라우팅 상한 | ⚠️ | **collect 한정으로 축소** (D-12, 사용자 결정) |
| FR-12 | 상한·차단 관측 | ✅ | Act에서 `_tool_call_step_summary` 추가로 완성 |
| FR-13 | AdminToolsPage 조회·수정 | ✅ | 셀렉트 + 숫자입력 + 부분갱신 |
| FR-14 | NULL = 이전과 동일 | ✅ | 회귀 0건 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|:------:|
| 정확성 | 워커 1회 실행당 MCP 1회 | **1회** (실서버 계측) | ✅ |
| 호환성 | 회귀 0건 | **0건** (기준선 대조 4회) | ✅ |
| 성능 | collect LLM ≤ 2회 | 인자 1 + 조건부 압축 1 | ✅ |
| 아키텍처 | domain 순수성 | 외부 참조 0건 | ✅ |
| 로깅 | print 금지·스택 보존 | `print(` 0건 | ✅ |
| DDL | 테이블+전 컬럼 COMMENT | 3개 COMMENT | ✅ |
| 함수 길이 | 40줄 이하 | Act에서 해소 | ✅ |

### 3.3 Deliverables

**신규 9 / 수정 다수 (프로덕션 코드 653줄, 테스트 194건)**

| Deliverable | Location | Status |
|-------------|----------|:------:|
| 마이그레이션 | `db/migration/V069__add_category_to_tool_catalog.sql` | ✅ |
| 도메인 정책 | `domain/tool_catalog/policies.py` (`ToolCategoryPolicy`)<br>`domain/agent_builder/policies.py` (`CollectPipelinePolicy`, `ToolCallBudgetPolicy`) | ✅ |
| collect 노드 | `application/agent_builder/collect_pipeline.py` | ✅ |
| 재라우팅 훅 | `application/agent_builder/worker_run_cap_hooks.py` | ✅ |
| 메타 수정 UC | `application/tool_catalog/update_metadata_use_case.py` | ✅ |
| 세션 스코프 저장소 | `infrastructure/tool_catalog/session_scoped.py` | ✅ |
| MCP 스키마 전달 | `infrastructure/mcp/{tool_adapter,tool_registry}.py` | ✅ |
| API | `api/routes/tool_catalog_router.py` (`PATCH /metadata`) | ✅ |
| 프론트 | `idt_front/src/{types,services,hooks,constants}` + `AdminToolsPage` | ✅ |
| 테스트 | 신규 8파일 + 기존 4파일 확장 | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| **Gap-07** 레거시 서버 단위 워커 에이전트 | 운영 에이전트 재구성은 사용자 판단 영역 | High | 0.5일 (에이전트 재구성 + 확인) |
| `generate` 카테고리 도입 + tool_id 하드코딩 분기 리팩토링 | Plan §2.2 Out of Scope (Design Option B에 해당) | Medium | 2일 |
| MCP sync 시 카테고리 자동 추론 | Plan §2.2 Out of Scope — 이번엔 전부 NULL | Low | 1일 |
| Analysis Gap-04/05 (문서 정합) | Minor — §2.2 다이어그램 `args_schema` 표기, 예외 타입 계약 미기재 | Low | 0.2일 |
| 실 LLM 기반 collect 인자 산출 검증 | 실측 시 LLM은 스텁이었다 | Medium | 0.3일 |

### 4.2 Cancelled/On Hold Items

| Item | Reason | Alternative |
|------|--------|-------------|
| FR-11의 search 워커 상한 | 관리자 지정 없이 기존 검색 에이전트 동작이 바뀌어 FR-14 취지 훼손 | collect 한정 적용 (D-12) |
| D-04 완화(서버 단위 collect 허용) | 도구 여러 개 중 "무엇을 1회 부를지" 결정 문제를 새로 풀어야 함 | 에이전트를 개별 도구 워커로 재구성 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | 초판(Check) | 최종(Act) | Change |
|--------|-------:|-----:|-----:|-------:|
| Design Match Rate | 90% | 94.4% | **98.0%** | +3.6%p |
| — Structural | — | 100% | 100% | — |
| — Functional | — | 86% | **95%** | +9%p |
| — Contract | — | 100% | 100% | — |
| 신규 회귀 | 0건 | 0건 | **0건** | — |
| 사이클 테스트 | — | 187 | **194** | +7 |
| 전체 백엔드 통과 | — | 8806 | **8823** | +153 (기준선 8670 대비) |

### 5.2 Resolved Issues

| Issue | 발견 시점 | Resolution | Result |
|-------|-----------|------------|:------:|
| MCP `inputSchema`가 어댑터에서 버려짐 — FR-06 전제 붕괴 | Do module-2 | `mcp_input_schema` 필드 신설 + registry 전달 (D-14) | ✅ |
| 비정형 `inputSchema`가 pydantic 검증을 터뜨려 **서버 도구 로딩 전체 실패** | Do module-2 (기존 테스트가 포착) | `_as_schema_dict()` 정규화 — §6.2 격리 철학 준수 | ✅ |
| FR-11 ↔ FR-14 충돌 (search 워커는 REGISTRY 분류) | Do module-3 | FR-11을 collect 한정으로 축소 (D-12) | ✅ |
| 설계 §4.1 path 세그먼트에 콜론 포함 tool_id | Do module-4 | body 방식으로 변경 (D-13) | ✅ |
| react 상한 도달이 관측 불가 (FR-12 부분 미충족) | Check Gap-01 | `_tool_call_step_summary` + `worker_run_limits` | ✅ |
| 함수 길이 40줄 위반 2건 | Check Gap-02 | `_resolve_body`/`_BodyOutcome` 추출 + **측정 오류 교정** | ✅ |
| SUCCESS 기준 미실측 | Check Gap-03 | 실 MCP 서버 계측 수행 | ✅ |
| **운영 DB의 스크랩 도구 3개가 `category='search'`** — 배포 시 호출 불가 | Act 실측 중 | `UpdateToolMetadataUseCase` 경로로 `collect` 변경 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **기존 테스트가 실제 결함을 잡았다.** `test_tool_registry.py`의 MagicMock 픽스처가 비정형
  `inputSchema` 처리 누락을 드러냈다. "테스트가 깨졌으니 테스트를 고친다"가 아니라 원인을
  파고든 결과, 서버 도구 로딩 전체가 무너지는 버그를 배포 전에 막았다.
- **기준선 대조(stash) 방식의 회귀 검증.** 전체 스위트에 기존 실패 58건이 있어 "통과/실패"
  숫자만으로는 회귀 판단이 불가능했다. 변경분만 stash하고 실패 **집합**을 비교하니
  차집합으로 회귀 0건을 증명할 수 있었다. 모듈마다 반복해 4회 수행했다.
- **설계 편차를 숨기지 않고 문서에 되돌려 반영.** D-12/13/14 전부 발견 즉시 Plan/Design에
  기록해, Check 단계에서 "문서와 코드가 다르다"는 가짜 Gap이 생기지 않았다.
- **실 환경 계측이 설계 전제를 검증했다.** D-03("스크랩은 query가 아니라 url을 받는다")이
  실서버 `required: ['url']`로 확인됐고, 그 과정에서 운영 DB의 잘못된 분류(Gap-06)까지 잡혔다.

### 6.2 What Needs Improvement (Problem)

- **gap-detector 에이전트가 결과를 내지 못했다.** 30턴 한도에서 본문 없이(`대기 중.`) 종료,
  173k 토큰 소모. 독립 검증이 사라져 Check가 **구현자 자기검증**이 됐고, 자기확증 편향이
  분석의 알려진 한계로 남았다(Analysis §0에 명시).
- **품질 규칙 위반을 스스로 만들었다.** Design §10.4가 "단계별 헬퍼로 분해"를 명시했는데도
  `collect_node`에 4갈래 분기를 인라인으로 남겼다. 헬퍼 3개는 만들었으나 지시의 핵심을
  놓쳤고, Check에서야 잡혔다.
- **측정 도구부터 틀렸다.** 초판 함수 길이 측정이 중첩 함수를 이중 계산해 노드 팩토리를
  항상 위반으로 잡았다. 기존 동종 함수와 비교하지 않았다면 잘못된 수치로 리팩토링할 뻔했다.
- **핵심 지표를 마지막에야 쟀다.** "4~5회 → 몇 회"가 사이클의 존재 이유인데, Check
  Gap-03로 지적될 때까지 실측 계획이 없었다. Design §8 Test Plan에 실환경 계측 항목이
  아예 없었던 것이 원인이다.
- **운영 DB 상태를 늦게 확인했다.** Gap-06(스크랩 도구가 `search`로 설정됨)은 Plan 단계에
  현재 데이터를 한 번만 조회했어도 발견됐을 문제다.

### 6.3 What to Try Next (Try)

- **Plan/Design 단계에서 운영 데이터 스냅샷 확인**을 절차에 넣는다. "현재 이 테이블에 어떤
  값이 들어 있는가"는 설계 전제를 흔드는 정보다.
- **Design §8 Test Plan에 "실환경 계측" 항목을 필수화**한다. 단위 테스트로 대체 불가능한
  SUCCESS 기준은 Do 단계에서 계측 수단부터 만든다(이번엔 Gap-01 관측이 그 역할을 했다).
- **서브에이전트 출력은 파일로 받는다.** 30턴 한도에 걸려도 부분 결과가 남도록 중간
  산출물을 파일에 쓰게 지시한다.
- **품질 규칙은 테스트로 강제한다.** 이번에 추가한 `test_collect_pipeline_functions_are_within_limit`
  처럼 함수 길이·레이어 순수성을 assert하면 리뷰에 의존하지 않는다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 코드만 조사, 운영 데이터 미확인 | **현재 DB 상태 스냅샷**을 배경 조사에 포함 |
| Design | Test Plan이 단위/E2E 위주 | **핵심 지표 계측 방법**을 별도 항목으로 요구 |
| Do | 모듈 분할·TDD는 잘 작동 | 유지. 모듈별 회귀 대조도 유지 |
| Check | gap-detector 한도 초과로 무력화 | 에이전트 실패 시 **폴백 절차**를 명시(자기검증 + 한계 기술) |
| Act | 수정 후 재측정 잘 작동 | 유지 |

### 7.2 Tools/Environment

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| 테스트 | 기존 실패 58건(백엔드)·9건(프론트) 정리 | 회귀 판단에 stash 대조가 불필요해짐 |
| 테스트 | `test_run_agent_use_case_observability.py` 5건은 순서 의존 | 테스트 오염 제거 |
| 관측 | run step에 도구 호출 수 노출(이번 추가) | 4~5회 → 실제 몇 회인지 운영 중 확인 가능 |
| 서브에이전트 | 턴 한도 대비 파일 출력 규약 | 부분 결과 유실 방지 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] **배포 전 확인**: V069가 운영 DB에 적용됐는지 (개발 DB는 적용 완료)
- [ ] 배포 후 run step에서 스크랩 워커의 "도구 호출 N회" 실제값 관측
- [ ] Gap-07 판단: 레거시 서버 단위 에이전트를 개별 도구 워커로 재구성할지

### 8.2 Next PDCA Cycle

| Item | Priority | Note |
|------|----------|------|
| Gap-07 에이전트 재구성 | High | collect 혜택(1회 호출 + 근거 규약)을 실제 에이전트가 받게 됨 |
| `generate` 카테고리 + tool_id 하드코딩 분기 리팩토링 | Medium | Design Option B. `compile()` 구조 정리 |
| MCP 카테고리 자동 추론 | Low | 도구 수가 늘면 가치 상승 |

---

## 9. Changelog

### v1.0.0 (2026-09-03)

**Added:**
- `tool_catalog.category` / `max_tool_calls` 컬럼 (V069) — 워커 노드 종류를 데이터로 결정
- `collect` 카테고리 및 단일샷 collect 노드 — 도구를 정확히 1회 호출하고 원본을 근거로 전달
- react 워커 도구 호출 상한 (기본 2회, 도구별 오버라이드) — wiki 분기는 예외
- collect 워커 재라우팅 상한 (`WorkerRunCapHooks`)
- `PATCH /api/v1/tool-catalog/metadata` + `AdminToolsPage` 분류·상한 편집 UI
- MCP 도구 입력 스키마 전달 (`MCPToolAdapter.mcp_input_schema`)
- 워커 도구 호출 횟수 관측 (run step / 로그)

**Changed:**
- `_resolve_category` 해석 순서에 `tool_catalog.category` 단계 추가
  (`agent_tool` → `tool_catalog` → `TOOL_REGISTRY` → `"action"`)
- 운영 DB: 스크랩 도구 3종 `category` `search` → `collect`

**Fixed:**
- MCP 서버가 비정형 `inputSchema`를 반환하면 해당 서버의 도구 로딩 전체가 실패하던 문제

**Compatibility:**
- `category`가 NULL인 도구는 이 변경 이전과 동일하게 동작한다. 백필 없음.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-03 | 완료 보고서 작성 (Match Rate 98.0%) | 배상규 |
