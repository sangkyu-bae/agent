# mcp-tool-category-routing Gap Analysis

> **Phase**: Check
> **Date**: 2026-09-03
> **Author**: 배상규
> **Plan**: [mcp-tool-category-routing.plan.md](../01-plan/features/mcp-tool-category-routing.plan.md)
> **Design**: [mcp-tool-category-routing.design.md](../02-design/features/mcp-tool-category-routing.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | MCP 도구가 구조적으로 분류 불가 → 전부 react 루프 → 중복 호출 + 근거/분석 경계 붕괴 |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자), 도구 카탈로그 관리자 |
| **RISK** | 기존 저장 에이전트의 동작 변화(회귀). → category NULL = 현행과 100% 동일 경로로 방어 |
| **SUCCESS** | 스크랩 MCP 워커 1회 실행당 MCP 호출 1회, 산출물이 `is_search_result()` 판정 통과, 기존 에이전트 회귀 0건 |
| **SCOPE** | M1 스키마·카탈로그 / M2 collect 노드 / M3 컴파일러 라우팅·상한 / M4 Admin UI |

---

## 0. 분석 방법과 한계

**gap-detector 에이전트는 사용하지 못했다.** 30턴 한도에 걸려 본문 없이(`대기 중.`) 종료됐고,
173k 토큰을 소비했으나 판정 결과를 산출하지 못했다. 재실행 대신 **구현자 자기검증 + 런타임
테스트 실행**으로 대체했다.

이 방법의 한계를 명시한다:

- 정적 판정은 구현자 본인이 수행했으므로 **자기확증 편향이 남아 있다**. 특히 "설계 의도대로
  동작하는가"보다 "설계 문서와 코드가 일치하는가"에 치우칠 수 있다.
- 이를 보정하기 위해 판정 근거를 전부 **기계적으로 확인 가능한 형태**(grep/AST/테스트 실행
  결과)로 제시했고, 주관적 판단이 들어간 항목은 별도 표시했다.
- 초판에서는 실 MCP 서버 실측이 없었으나(Gap-03), **Act 단계에서 실서버 계측을 수행해
  해소했다** (§9 참조). 그 과정에서 운영 이슈 2건(Gap-06/07)이 추가로 드러났다.

---

## 1. Strategic Alignment Check

| 질문 | 판정 | 근거 |
|------|:----:|------|
| PRD/Plan의 핵심 문제(WHY)를 해결했는가 | ✅ | MCP 도구가 `_resolve_category`에서 카탈로그 단계를 거치게 됐고(`workflow_compiler.py:895-913`), `collect` 지정 시 react 루프를 타지 않는다 |
| "수집 vs 분석" 경계를 복원했는가 | ✅ | collect 산출은 도구 원본을 `format_search_result()`로 감싼다 — `test_result_body_is_tool_output_not_llm_synthesis` |
| "데이터로 라우팅" 원칙(코어 하드코딩 금지)을 지켰는가 | ✅ | 노드 선택이 `tool_catalog.category` 값으로 결정됨. tool_id 하드코딩 분기는 추가하지 않음 |
| 무회귀 원칙을 지켰는가 | ✅ | 전체 스위트 실패 집합이 기준선과 **테스트 ID 단위로 동일**(§3) |

**전략적 오정렬 없음.**

---

## 2. Plan Success Criteria 판정

### 2.1 Functional Requirements

| ID | 판정 | 근거 |
|----|:----:|------|
| FR-01 | ✅ | `V069__add_category_to_tool_catalog.sql` — 2컬럼 ADD, COMMENT 3개(컬럼 2 + 테이블 1). `models.py:50,59` `comment=` 동일 반영. `tests/db/test_migration_ddl_comments.py` 통과 |
| FR-02 | ✅ | `ToolCategoryPolicy.ALLOWED` 4종 고정 + `validate()`. `test_tool_category_policy.py` 28건 |
| FR-03 | ✅ | `upsert_by_tool_id`의 `.values()`에 `name/description/is_active/updated_at`만 존재 — category·max_tool_calls 부재. `test_upsert_update_branch_never_touches_category`(SQL 컴파일 파라미터 검증) + `test_sync_preserves_category.py` 3건 |
| FR-04 | ✅ | `_resolve_category(worker_def, catalog_meta)` 4단계. `TestCategoryResolutionPriority` 8건 |
| FR-05 | ✅ | `category in ("search","collect")` 분기 → `_create_worker_node_for_category`. `test_collect_worker_bypasses_create_agent`(create_agent 미호출) + `test_tool_invoked_exactly_once` |
| FR-06 | ✅ | `_resolve_input_schema()` → `CollectArguments` structured output 1회 → `ToolArgumentPolicy.find_placeholder`. **설계 전제였던 `args_schema`가 MCP 어댑터에서 제네릭 래퍼였던 문제를 `mcp_input_schema` 필드 신설로 해결**(§5 편차 D-14) |
| FR-07 | ✅ | 실패 6분기 전부 예외 미전파 + 규약 메시지. `TestCollectFailureBranches` 6건 |
| FR-08 | ✅ | 모든 분기에서 `is_search_result()` 통과. `test_every_branch_yields_one_search_result_message`(5 케이스 파라미터화) |
| FR-09 | ✅ | `policy.needs_compression()` 통과 시에만 압축. `test_short_result_is_not_compressed`(압축 LLM 호출 0회 assert) |
| FR-10 | ✅ | `_tool_call_budget_middleware()` → `ToolCallBudgetPolicy.resolve()` → `MiddlewareBuilder.build_tool_call_budget()`. `test_react_worker_receives_budget_middleware_in_compile`(compile 경로 통합 검증), `test_default_limit_is_two` |
| FR-11 | ⚠️ | **범위 축소 후 충족.** `WorkerRunCapHooks`가 collect 워커만 상한. 원안의 search 포함은 D-12로 제외(사용자 결정). `test_worker_run_cap_hooks.py` 10건 |
| FR-12 | ⚠️ | 로그는 구현됨(`collect_node executing`, `collect_node argument blocked`, `worker run cap applied`) + `STEP_OUTPUT_SUMMARY_KEY` 설정. **다만 react 상한 도달(FR-10)은 langchain 내장 미들웨어가 처리해 우리 로그에 남지 않는다** — §4 Gap-01 |
| FR-13 | ✅ | `PATCH /tool-catalog/metadata` + `AdminToolsPage` 셀렉트·숫자입력. 라우터 14건 + 프론트 8건 |
| FR-14 | ✅ | `tool_catalog_repository=None` → 카탈로그 단계 생략. `test_no_catalog_repo_behaves_as_before`, `test_null_category_takes_react_path`. 전체 회귀 실패 집합 기준선 동일 |

**FR 충족률: 12 ✅ / 2 ⚠️ / 0 ❌ = 12 + (2×0.5) = 13/14 = 92.9%**

### 2.2 Non-Functional Requirements

| 항목 | 판정 | 근거 |
|------|:----:|------|
| 정확성 (호출 1회) | ⚠️ | fake tool 카운터로만 검증. 실 MCP 서버 실측 미수행 — §4 Gap-03 |
| 호환성 (회귀 0건) | ✅ | 백엔드 실패 집합 기준선 동일(58/58, 차집합 양방향 공집합). 프론트도 동일(9/9, stash 대조) |
| 성능 (collect LLM ≤2회) | ✅ | `test_llm_called_once_when_no_compression`가 호출 횟수 assert |
| 아키텍처 (domain 순수성) | ✅ | 신규 domain 4파일에 infrastructure/application/langchain/sqlalchemy/fastapi 참조 0건 (grep 검증) |
| 로깅 (print 금지·스택 보존) | ✅ | 신규 5파일 `print(` 0건. `logger.error(..., exception=e)` 사용 |
| DDL COMMENT | ✅ | `test_migration_ddl_comments.py` 통과 |
| **함수 길이 40줄** | ❌ | **2건 위반** — §4 Gap-02 |

---

## 3. Runtime Verification

| 계층 | 결과 |
|------|------|
| 사이클 관련 백엔드 테스트 | **187 passed / 0 failed** |
| 백엔드 전체 | 8806 passed, 58 failed, 2 skipped |
| 백엔드 기준선 대비 | **신규 실패 0건** (실패 집합 차집합 양방향 공집합) |
| 프론트 `AdminToolsPage` | **8 passed** |
| 프론트 `tsc --noEmit` | **통과** |
| 프론트 전체 | 1168 passed, 9 failed — stash 대조로 **전부 기존 실패** 확인 |

**기준선 측정 방식**: 이번 사이클 변경분만 `git stash`로 되돌린 뒤 동일 스위트를 실행해
실패 집합을 비교했다(백엔드 M1 시점, 프론트 M4 시점). 두 방향 차집합이 모두 공집합이므로
**이 사이클이 유발한 회귀는 0건**이다.

**미실행 항목**: L2/L3(Playwright) 미도입 프로젝트라 해당 없음. 실 MCP 서버 E2E 미수행(Gap-03).

---

## 4. Gap List

### Gap-01 (Important) — react 상한 도달이 관측되지 않는다

**FR-12 부분 미충족.**

`ToolCallLimitMiddleware(exit_behavior="continue")`는 상한 초과 시 도구 호출을 차단하지만,
그 사실이 우리 로그·run step에 남지 않는다. langchain 내부 동작이기 때문이다.

- **영향**: 관찰된 "4~5회 호출"이 실제로 몇 회로 줄었는지, 상한에 걸린 워커가 어느 것인지
  운영 중에 알 수 없다. 이번 사이클의 핵심 지표를 측정할 수단이 없다는 뜻이다.
- **근거**: `middleware_builder.py:build_tool_call_budget` — 인스턴스만 생성, 콜백 없음.
  `collect_pipeline`/`worker_run_cap_hooks`에는 로그가 있으나 react 경로에는 없다.
- **수정 방향**: 워커 실행 후 메시지에서 tool call 수를 세어 step summary에 싣거나,
  `ToolCallLimitMiddleware`를 감싸 차단 시점에 로그를 남기는 얇은 래퍼를 둔다.

### Gap-02 (Important) — 함수 길이 40줄 규칙 위반 2건

`idt/CLAUDE.md` §3 "함수 길이 40줄 초과 금지" 위반.

| 함수 | 전체 | 주석·docstring 제외 코드 | 기존 동종 함수 |
|------|---:|---:|---|
| `collect_pipeline.create_collect_node` | 86 | **66** | `create_search_pipeline_node` 49 |
| `collect_pipeline.collect_node` (내부) | 65 | **56** | `search_node` 39 |
| `_build_arguments` | 44 | 35 | — (기준 내) |
| `update_metadata_use_case.execute` | 65 | 38 | — (기준 내) |

- **영향**: 가독성·테스트 용이성 저하. 특히 `collect_node` 본문에 4갈래 분기(근거부족 /
  차단 / 정상 / 실패)가 인라인으로 들어가 있어 분기 추가 시 급격히 악화된다.
- **판정 근거**: AST로 측정. 뒤의 두 건은 docstring 비중이 커 실질 코드가 40줄 이내라
  위반으로 보지 않았다. 앞의 두 건은 **기존 동종 함수보다도 크다**.
- **설계 위반이기도 하다**: Design §10.4가 "collect 노드는 단계별 헬퍼로 분해"를 명시했고
  헬퍼 3개(`_build_arguments`/`_invoke_once`/`_maybe_compress`)는 만들었으나, 노드 본문의
  분기 결정 로직을 분리하지 않았다.
- **수정 방향**: `collect_node`의 4갈래 분기를 `_resolve_body(plan, tool, ...) -> _BodyResult`
  같은 헬퍼로 추출한다.

### Gap-03 (Important) — 핵심 SUCCESS 기준이 실측되지 않았다

Plan Definition of Done: "스크랩 MCP 도구를 `collect`로 지정한 에이전트에서 **실제 호출
1회를 실측**".

- **현재 상태**: fake tool 호출 카운터(`test_tool_invoked_exactly_once`)로만 검증됐다.
  실제 MCP 서버에 붙여 요청→호출 횟수를 관측한 적이 없다.
- **영향**: 이 사이클이 해결하려던 바로 그 증상(4~5회 → 1회)이 실환경에서 사라졌는지
  확인되지 않았다. 단위 테스트는 "우리 코드가 1회만 부른다"를 보장할 뿐, MCP 어댑터·
  supervisor 경로를 포함한 실제 호출 수는 다를 수 있다.
- **수정 방향**: `/verify-mcp-connections` 스킬 또는 로컬 DB의 스크랩 MCP 도구를 `collect`로
  지정한 뒤 실제 실행. Gap-01을 먼저 처리하면 계측이 쉬워진다.

### Gap-04 (Minor) — 설계 문서와 구현의 명시적 편차 3건 (전부 문서 반영 완료)

의도적 편차이며 근거와 함께 문서에 기록했다. 미반영 편차는 없다.

| ID | 편차 | 반영 위치 |
|----|------|----------|
| D-12 | FR-11 상한 대상을 collect 한정으로 축소 (search 제외) | Design §5 D-12, Plan FR-11 |
| D-13 | `PATCH /{tool_id}/metadata` → `PATCH /metadata` + body | Design §4.1/§4.2 |
| D-14 | MCP `inputSchema` 전달 필드 신설 (설계는 `args_schema` 사용을 전제했으나 어댑터가 제네릭 래퍼였음) | 본 문서 §5 — **Design §2.2 다이어그램은 아직 `args_schema`로 표기됨** |

### Gap-05 (Minor) — 예외 타입 계약이 설계 §4.2에 미기재

미존재는 `LookupError`(→404), 도메인 위반은 `ValueError`(→400)로 구분했다. 설계 §4.2
에러표에는 상태코드만 있고 예외 타입 계약이 없다. `test_lookup_error_is_not_value_error`가
코드에서는 이를 고정하고 있으나 문서에는 없다.

---

## 5. Decision Record Verification

| 결정 | 준수 | 근거 |
|------|:----:|------|
| D-01 tool_catalog 컬럼 저장 | ✅ | V069 + `_load_catalog_metadata` |
| D-02 sync SET 절 제외 | ✅ | `.values()`에 부재 (SQL 파라미터 테스트) |
| D-03 collect 전용 노드 (search 재사용 안 함) | ✅ | `collect_pipeline.py` 신설 |
| D-04 collect는 단일 도구 참조만 | ✅ | `assert_assignable` + UC 검증 + 400 응답 |
| D-05 내장 `ToolCallLimitMiddleware` | ✅ | `build_tool_call_budget` |
| **D-06 wiki 분기 상한 예외** | ✅ | wiki 분기 `middleware=_instantiate(...)` 단독, 일반 분기만 budget 추가. `test_wiki_branch_gets_no_budget_middleware` |
| D-07 `skip_workers` 훅으로 구현, supervisor 코어 미수정 | ✅ | `supervisor_nodes.py` 변경 없음 |
| D-08 optional dep, 미주입 시 기존 동작 | ✅ | `test_no_catalog_repo_behaves_as_before` |
| D-09 compile당 1회 배치 조회 | ✅ | `test_catalog_queried_once_per_compile`(워커 3개, 조회 1회) |
| D-10 graceful degrade | ✅ | `test_catalog_failure_degrades_to_empty` |
| D-11 langchain 참조를 MiddlewareBuilder에 격리 | ✅ | `ToolCallLimitMiddleware` import는 `middleware_builder.py` 1곳 (`worker_run_cap_hooks.py`는 주석 언급만) |
| D-12 FR-11 collect 한정 | ✅ | `collect_worker_ids`만 훅에 전달 |
| D-13 body 방식 엔드포인트 | ✅ | `@router.patch("/metadata")` |

**미준수 결정 0건.**

---

## 6. API Contract 3-way 검증

| 항목 | Design §4 | 서버 | 클라이언트 | 일치 |
|------|-----------|------|-----------|:----:|
| 엔드포인트 | `PATCH /tool-catalog/metadata` | `tool_catalog_router.py:70` | `api.ts:75 TOOL_CATALOG_METADATA` | ✅ |
| 요청 필드 | `tool_id`/`category`/`max_tool_calls` | `ToolMetadataRequest` | `ToolMetadataRequest` (동일 3필드) | ✅ |
| 응답 필드 | `tool_id`/`category`/`max_tool_calls` | `ToolMetadataResponse` | `ToolMetadataResponse` | ✅ |
| 목록 응답 확장 | `category`, `max_tool_calls` | `ToolCatalogItemResponse` | `CatalogTool` | ✅ |
| 부분 갱신 의미론 | 생략=미변경, null=되돌리기 | `model_fields_set` | payload 선택 구성 | ✅ |
| 권한 | Admin | `require_role("admin")` | — | ✅ |
| 에러 | 400/404 | `ValueError`→400, `LookupError`→404 | 에러 배너 | ✅ |

**계약 불일치 0건.** 루트 `CLAUDE.md` §4-1(백엔드 스키마 변경 시 프론트 타입 동기화) 준수.

---

## 7. Match Rate

정적 전용 공식 적용 — 런타임은 단위/통합 테스트로 수행했으나 스킬이 정의한 L1(HTTP 서버)·
L2/L3(Playwright)는 미실행이라 보수적으로 static-only 공식을 쓴다.

```
Structural = 100%   설계 §11.1 파일 목록 전량 존재 + 계획 외 3파일 추가(session_scoped,
                    tool_adapter/tool_registry 수정 — 전부 문서화된 편차)
Functional =  86%   FR 13/14 (FR-11 ⚠️, FR-12 ⚠️) - 함수길이 위반 감점
Contract   = 100%   3-way 전량 일치

Overall = (100 × 0.2) + (86 × 0.4) + (100 × 0.4)
        = 20 + 34.4 + 40
        = 94.4%
```

| 축 | 비율 |
|----|-----:|
| Structural Match | 100% |
| Functional Depth | 86% |
| API Contract | 100% |
| **Overall** | **94.4%** |

> 참고: 런타임 축을 포함했다면 사이클 테스트 187/187 통과로 더 높았겠지만, 실 MCP 실측
> 부재(Gap-03)를 감안하면 현재 수치가 정직하다.

---

## 8. 권고

Match Rate 90% 이상이므로 `iterate` 없이 진행 가능하나, **Gap-01~03은 이번 사이클의 목적과
직결**되므로 처리를 권한다.

| Gap | 심각도 | 권고 |
|-----|:------:|------|
| Gap-03 실측 부재 | Important | **최우선.** 이 사이클이 문제를 실제로 고쳤는지 확인하는 유일한 방법 |
| Gap-01 상한 관측 불가 | Important | Gap-03의 계측 수단이 되므로 함께 처리하면 효율적 |
| Gap-02 함수 길이 | Important | 규칙 위반이며 설계 §10.4 지시 미이행. 분기 추출로 해소 |
| Gap-04 §2.2 다이어그램 | Minor | `args_schema` → `mcp_input_schema` 표기 수정 |
| Gap-05 예외 계약 문서화 | Minor | Design §4.2 에러표에 예외 타입 열 추가 |

---

## 9. Act 단계 결과 (Gap-01·02 수정 + Gap-03 실측)

### 9.1 Gap-01 해소 — react 도구 호출 관측 추가

`_tool_call_step_summary(messages, limit)`를 신설하고 `_wrap_worker`에서 호출한다.
계측 위치는 `_blocked_step_summary`와 동일하다 — react 내부 트레이스가 state로 유출되기
전(worker-toolmessage-leak-fix D1)에 횟수만 건져 올린다.

- 적용 상한을 `worker_run_limits` 맵으로 워커별 기록해 `_wrap_worker`에 전달 → "상한 N 도달"
  표기가 가능해졌다. wiki 분기(D-06)는 상한이 없어 맵에 담기지 않으므로 횟수만 남는다.
- 로그 `worker tool calls` + step summary 동시 반영. 기존 차단 요약과 `" / "`로 병합해
  덮어쓰지 않는다.
- 테스트 11건 (`test_worker_tool_call_observability.py`).

### 9.2 Gap-02 해소 — 분기 추출로 함수 길이 규칙 충족

`collect_node` 본문의 4갈래 분기(근거부족/차단/정상/실패)를 `_resolve_body()`로 추출하고
결과를 `_BodyOutcome`으로 나른다. Design §10.4가 지시한 "단계별 헬퍼로 분해"의 마지막 조각.

**측정 방식도 바로잡았다.** 초판의 `create_collect_node=66`은 중첩 함수(`collect_node`)
본문을 포함한 수치였다 — 클로저를 반환하는 노드 팩토리는 그대로 세면 내부 함수를 두 번
계산해 항상 위반으로 잡힌다(기존 `create_search_pipeline_node`도 같은 이유로 49). 중첩 함수
본문을 제외하도록 고쳤고, **같은 잣대를 기존 `search_pipeline.py`에도 적용해 통과함을
테스트로 고정**했다(`test_measurement_matches_existing_peer_module`) — 새 기준을 신규 코드에만
자의적으로 들이대지 않는다는 근거다.

| 함수 | 수정 전 | 수정 후 |
|------|------:|------:|
| `create_collect_node` (중첩 제외) | 위반 | ✅ ≤40 |
| `collect_node` | 56 | ✅ ≤40 |

### 9.3 Gap-03 해소 — 실 MCP 서버 계측

로컬 `Scrap MCP`(`http://localhost:8002/sse`, 도구 3개)를 프로덕션 코드 경로로 로드해 측정했다.

**입력 스키마 전달 검증 (D-14)**

| 도구 | 스키마 전달 | required |
|------|:---:|---|
| `scrape_url` | ✅ | `['url']` |
| `scrape_urls` | ✅ | `['urls']` |
| `extract_structured` | ✅ | `['url', 'selector']` |

설계 D-03의 전제("스크랩은 `query`가 아니라 `url`을 받는다")가 실서버로 확인됐다.

**collect 노드 호출 횟수 계측** (`MCPToolAdapter._arun` 후킹, LLM은 인자 산출 스텁)

| 시나리오 | MCP 호출 | `is_search_result()` | 결과 |
|----------|:---:|:---:|------|
| 플레이스홀더 URL(`example.com`) | **0회** | ✅ | 서버 도달 전 차단 (§6.1 #3) |
| 실제 URL(`python.org`) | **1회** | ✅ | 인자 `{'url': ...}`, 본문 2705자 |

정상 경로 본문은 도구 원본 JSON(`{"url":…, "title":"Welcome to Python.org", "text":…}`)으로,
**워커 LLM의 종합문이 아님**이 실서버로 확인됐다. Plan SUCCESS 기준 3개가 모두 실측으로
충족됐다.

**계측의 한계**: 인자 생성 LLM은 스텁이다. 실 LLM이 근거 있는 URL을 산출하는지는 별도
확인이 필요하다. 또한 react 경로의 "4~5회"는 이번에 재현 측정하지 않았다 — 비교 기준선이
없으므로 개선 폭은 수치로 말할 수 없다.

---

## 10. 실측 중 발견된 운영 이슈

### Gap-06 (Critical) — 실 DB의 스크랩 도구가 `category='search'`로 설정돼 있다

```
mcp:081c6fe7-…:scrape_url        category='search'  (updated_at 2026-09-03 09:55)
mcp:081c6fe7-…:scrape_urls       category='search'
mcp:081c6fe7-…:extract_structured category='search'
```

- **이 사이클 이전에는 무해했다.** `_resolve_category`가 카탈로그를 읽지 않았으므로 값이
  무시됐다. **이번 변경으로 카탈로그가 실제로 읽히면서 이 값이 활성화된다.**
- `category='search'` → search 파이프라인 → `_safe_search`가 `tool.ainvoke({"query": …})`.
  그런데 세 도구의 required는 `url`/`urls`다(§9.3 실측) → **호출이 성립하지 않는다.**
- 이 값을 설정한 주체는 확인하지 못했다. sync는 category를 쓰지 않으므로(D-02)
  `PATCH /metadata` 또는 직접 SQL 경로다.
**조치 완료 (사용자 승인)**: 세 도구를 `collect`로 변경했다. 직접 SQL이 아니라
`UpdateToolMetadataUseCase`를 태워 `ToolCategoryPolicy` 검증(D-04 단일 도구 참조 확인
포함)을 거치게 했다 — 우회 경로로 규칙을 건너뛰지 않기 위해서다.

```
BEFORE  scrape_url / scrape_urls / extract_structured : category='search'
AFTER   scrape_url / scrape_urls / extract_structured : category='collect'
```

**조치 후 실 DB 카탈로그(13개 엔트리)로 재검증**:

| tool_id | 해석된 category | react 상한 |
|---------|----------------|----------:|
| `mcp:081c6fe7-…:scrape_url` | **collect** | 2 |
| `mcp:081c6fe7-…:scrape_urls` | **collect** | 2 |
| `mcp_081c6fe7-…` (레거시, 실제 에이전트) | action | 2 |
| `tavily_search` (내부) | search | 2 |

레거시 워커가 `action`으로 남는 것은 Gap-07 그대로이며, 사용자 결정에 따라 현 상태를
수용한다(상한 2회만 적용).

### Gap-07 (Important) — 실제 에이전트가 레거시 서버 단위 워커를 쓴다

```
agent_tool: agent_id=df9d0fd2-…  tool_id='mcp_081c6fe7-…'  category=NULL
```

- `mcp_{server}` 레거시 형식이라 카탈로그 키(`mcp:{srv}:{tool}`)와 매칭되지 않는다 →
  `_resolve_category` 카탈로그 단계 미스 → `"action"` → **react 경로 유지**.
- 즉 **현재 운영 중인 에이전트는 collect의 혜택을 받지 못한다.** D-04에 따라 서버 단위
  워커에는 `collect`를 지정할 수도 없다(도구가 3개라 "1회 호출"이 정의되지 않음).
- 다만 **react 호출 상한(FR-10)은 적용된다** — 카탈로그 미스 시 기본값 2회. 관찰된 4~5회는
  최대 2회로 줄어든다. Gap-01의 관측으로 실행 이력에서 확인 가능해졌다.
- **결정 (사용자)**: **② 현 상태 수용.** 관찰된 4~5회는 상한으로 최대 2회가 되고,
  Gap-01의 관측으로 실행 이력에서 실제 횟수를 확인할 수 있다. 개별 도구 워커로의 재구성은
  운영 에이전트 변경이라 사용자 판단 영역으로 남긴다.
- **잔여 리스크**: 이 에이전트는 collect의 "1회 호출 + 근거 규약" 혜택을 받지 못한다.
  산출은 여전히 워커 LLM의 종합문이므로 "분석 혼입" 증상이 이 경로에서는 남는다.

---

## 11. Match Rate 재산정 (Act 후)

```
Structural = 100%
Functional =  95%   FR-12 ✅(Gap-01 해소), 함수길이 ✅(Gap-02 해소), FR-11 ⚠️ 유지
Contract   = 100%

Overall = (100 × 0.2) + (95 × 0.4) + (100 × 0.4) = 98.0%
```

| 축 | 초판 | Act 후 |
|----|---:|---:|
| Structural | 100% | 100% |
| Functional | 86% | 95% |
| Contract | 100% | 100% |
| **Overall** | **94.4%** | **98.0%** |

남은 ⚠️는 FR-11(설계 원안 대비 collect 한정으로 축소 — D-12, 사용자 결정)뿐이다.

**단, Gap-06은 코드가 아니라 운영 데이터 문제이며 Match Rate에 반영되지 않는다.**
배포 전 반드시 처리해야 한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-03 | 최초 Gap 분석. gap-detector 실패로 자기검증 대체(한계 §0 명시) | 배상규 |
| 0.3 | 2026-09-03 | Gap-06 조치 완료(3개 도구 collect 변경) + 실 DB 재검증. Gap-07 현 상태 수용 결정 | 배상규 |
| 0.2 | 2026-09-03 | Act 결과 반영 — Gap-01·02 해소, Gap-03 실서버 실측. 실측 중 Gap-06(Critical)·07 발견. Match Rate 94.4% → 98.0% | 배상규 |
