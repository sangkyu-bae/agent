# Deep Search Pipeline Planning Document

> **Summary**: 현행 search 워커는 복잡한 질문도 **검색 쿼리 1개**로 압축하고, validate 루프는 결과를 **교체**할 뿐 누적하지 않아 다축 질문에서 근거가 구조적으로 유실된다. 이를 해결하기 위해 `Requirement 분해 → 병렬 검색 → Evidence 추출·누적 → Coverage 검증 → 부족분만 선택적 재검색` 상태머신을 **독립 모듈**로 신설한다. 기존 `search_pipeline.py`는 그대로 두고 config 플래그(`search_pipeline_mode`)로 **교체 대기** 상태를 유지하며, 1단계 적용 대상은 웹검색(tavily)으로 한정한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-25
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `search_pipeline.py`의 rewrite는 `RewrittenQuery.query: str` **단수 필드**이고 프롬프트가 "쿼리 **하나**를, 한 문장으로"를 강제한다. "A와 B의 BIS 비율"은 `"A B BIS 비율"` 한 줄로 뭉개져 검색 결과 하나에 두 사실이 함께 나오길 기대하는 구조가 된다. validate 루프(최대 3회)는 `text` 변수를 매 시도 **덮어쓰므로**(`search_pipeline.py:269`) 이전 시도의 근거가 버려지고, 판정 기준도 "부분적으로라도 유용하면 통과"라 **한 축만 채워져도 종료**한다. supervisor 재라우팅으로 재검색해도 rewrite 입력(`latest_user_question` + 워커 산출물이 제외된 `_collect_context`)이 1회차와 동일해 **같은 쿼리를 반복 생성**한다 |
| **Solution** | 검색 전에 **Search Plan**을 만든다. QuestionAnalyzer가 `single/parallel/iterative` 전략을 판정하고, SearchPlanner가 `Requirement[]`(정보 슬롯)와 requirement별 쿼리를 **분리해** 산출한다. 병렬 검색 → EvidenceExtractor가 사실을 구조화 → EvidenceStore에 iteration 간 **누적** → SufficiencyEvaluator가 requirement별 충족/제약(시점 정합 등)을 판정 → **미충족 슬롯만** SearchReplanner가 **검색 전략을 바꿔** 재검색. 종료는 4중 조건(coverage complete / max iteration / no information gain / search exhaustion) |
| **Function/UX Effect** | 다축·비교형 질문에서 각 축의 근거가 독립적으로 확보되고, 이미 찾은 사실은 재검색하지 않는다. 비교 질문은 값이 다 있어도 **기준 시점이 어긋나면 미충족**으로 판정해 정렬 검색을 한 번 더 시도한다. 단순 질문(`single`)은 분해 없이 기존과 동일한 1쿼리 경로로 빠져나가 비용이 늘지 않는다 |
| **Core Value** | 루프의 기준을 "검색을 몇 번 했는가"에서 **"질문에 필요한 fact slot이 얼마나 채워졌는가"**로 옮긴다. LLM 자유 재귀가 아닌 **상태머신 + 예산 상한**이라 운영 환경에서 예측 가능하고 디버깅 가능하다. 기존 파이프라인을 건드리지 않는 교체 대기 모듈이므로 롤백이 환경변수 한 줄이다 |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | 다축 질문이 단일 쿼리로 뭉개지고, 재시도 루프가 근거를 누적하지 않고 교체해 구조적으로 일부 축의 근거가 유실됨 |
| **WHO** | P2 에이전트 소유자(검색 워커 품질), 웹검색 도구를 쓰는 최종 사용자(P1) — 비교·다개체·목록형 질의 전반 |
| **RISK** | ① LLM 호출 증가로 지연·비용 상승 ② Extractor가 검색 결과에 없는 값을 생성(환각) ③ Replanner가 표현만 바꾼 동어반복 쿼리 생성 ④ 금융 도메인 특화가 코어에 하드코딩(CLAUDE.md 일반화 원칙 위반) ⑤ 기존 legacy 경로 회귀 |
| **SUCCESS** | 다축 질의에서 requirement 수만큼 독립 쿼리 발행·근거 누적(테스트 고정), `single` 전략은 LLM 호출 수가 legacy 이하, 플래그 `legacy` 시 기존 동작 변화 0(반환 계약 테스트), 4중 종료 조건 각각 단위 테스트로 고정, 기존 테스트 회귀 0 |
| **SCOPE** | 1단계: domain 스키마·정책 + application 노드·워크플로우(모듈 완결) / 2단계: config 플래그 + workflow_compiler 분기(웹검색 한정) / 3단계: 관측 지표(coverage/stop_reason) 노출. **내부문서검색 적용·AnswerGenerator·multi_query 통합은 범위 밖** |

---

## 1. Overview

### 1.1 Purpose

검색 워커가 **"무엇을 몇 개 알아내야 하는가"를 먼저 구조화**하고, 채워지지 않은 슬롯만 선택적으로 재검색하는 iterative retrieval 모듈을 신설한다. 목적은 세 가지다.

1. **커버리지**: 다축 질문의 각 축이 독립된 검색으로 근거를 확보한다.
2. **효율**: 이미 확보한 사실은 재검색하지 않고, 검색 결과 원문 대신 구조화 Evidence를 다음 iteration에 전달해 토큰을 절감한다.
3. **예측 가능성**: LLM 자유 재귀가 아닌 상태머신 + 4중 종료 조건 + 예산 상한으로 최악 비용이 계산 가능하다.

### 1.2 Background (2026-08-25 코드 추적 결과)

**결함 확정 근거**

| 사실 | 위치 |
|------|------|
| rewrite 산출 스키마가 `query: str` **단수** — 복수 쿼리 표현 불가 | `src/application/agent_builder/search_pipeline.py:97` |
| 프롬프트가 "쿼리 **하나**", "**한 문장**, 명사구 중심" 명시 | `search_pipeline.py:114-124` |
| validate 루프가 `ok, text = await _safe_search(...)`로 **매 시도 결과를 덮어씀** → 이전 근거 소실 | `search_pipeline.py:269` |
| validate 판정이 "부분적으로라도 유용하면 relevant=true" → 한 축만 채워져도 통과 | `search_pipeline.py:138` |
| 재라우팅 시 rewrite 입력이 1회차와 동일 — `_collect_context`가 `is_worker_output`으로 **이전 검색 결과를 제외** | `search_pipeline.py:156-162`, `:57` |
| 검색 시도 상한 3회(최초 1 + 재시도 2), 마지막 시도는 validate 생략 | `src/domain/agent_builder/policies.py:214` |
| 웹검색 도구는 `query` 단일 인자, LLM 쿼리 무가공 전달 | `src/infrastructure/web_search/tavily_tool.py:44` |
| search 노드 배선 지점 (교체 분기 위치) | `src/application/agent_builder/workflow_compiler.py:349-359` |
| `category="search"` 도구는 tavily(웹) + internal_document_search(내부) 2종 — **동일 노드 사용** | `src/domain/agent_builder/tool_registry.py:34, 110` |

**기존 자산 (재사용 대상)**

| 자산 | 위치 | 재사용 방식 |
|------|------|------------|
| 메시지 규약 단일 출처 `format_search_result` / `is_search_result` (D2) | `search_pipeline.py:39-54` | **그대로 import** — 반환 계약 동일 유지의 핵심 |
| 최근 질문 추출 `latest_user_question` (품질 피드백 스킵 포함) | `search_pipeline.py:79` | 그대로 import |
| 경량 파이프라인 LLM 해석 `_resolve_pipeline_llm` (캐시 + 실패 폴백) | `workflow_compiler.py:767` | 그대로 재사용 |
| 사용자 컨텍스트 prepend 블록 | `workflow_compiler.py` → `user_context_block` | 신규 노드 프롬프트에 동일 적용 |
| config 주입 패턴 (`search_compress_threshold`) | `src/config.py:118`, `src/api/main.py:2695` | 신규 키 동일 패턴 |
| 병렬 검색 + RRF 융합 선례 | `src/application/multi_query/workflow.py` | **참고만** — 하이브리드 검색 전용이라 직접 재사용 불가 |

**참고 — 미배선 자산**: `multi_query` 모듈(분류 → 최대 5쿼리 → 병렬 → RRF)이 존재하나 `use_multi_query` 기본값 `False`이고 `tool_factory.py:92-114`에서 `multi_query_use_case`를 주입하지 않아 **전 코드베이스에서 활성화되지 않는다**. 본 기능은 이 모듈을 건드리지 않으며, 동일한 미배선 상태를 반복하지 않기 위해 **config 플래그로 실사용 가능한 형태**로 배선한다.

### 1.3 Related Documents

| 문서 | 위치 | 관계 |
|------|------|------|
| 유저 시나리오 (SoT) | `docs/USER-SCENARIOS.md` | P2 주인공, 일반화 > 특화 원칙 |
| search-node-query-pipeline 설계 | `docs/archive/*/search-node-query-pipeline/` | 대체 대상 파이프라인의 원 설계 (D1/D2/D4/D5) |
| multi-query-rewrite 계획 | `docs/01-plan/features/multi-query-rewrite.plan.md` | 선행 시도 — 미배선 사유 참고 |
| runtime-datetime-context | `docs/01-plan/features/runtime-datetime-context.plan.md` | 날짜 블록 — "최신/latest" 제약 해석에 직접 의존 |
| 도구 & MCP 규칙 | `idt/docs/rules/tool-and-mcp.md` | 도구 변경 시 필수 확인 |
| 로깅 규칙 | `idt/docs/rules/logging.md` | 신규 모듈 로깅 |

---

## 2. Scope

### 2.1 In Scope

| # | 항목 | 비고 |
|---|------|------|
| 1 | `domain/deep_search/` 스키마·정책 (LLM/LangChain 미사용) | Requirement/Evidence/State, 예산·종료 정책 |
| 2 | `application/deep_search/` 7노드 LangGraph 워크플로우 | Analyzer→Planner→Executor→Extractor→Store→Evaluator→Replanner |
| 3 | `create_deep_search_node()` — **기존 `create_search_pipeline_node`과 동일 시그니처·동일 반환 계약** | 무회귀 교체의 전제 |
| 4 | config 키 `search_pipeline_mode: str = "legacy"` + main.py 주입 | 기본값 legacy → 무영향 배포 |
| 5 | `workflow_compiler.py` category=="search" 분기 (웹검색 한정) | 최소 변경 |
| 6 | 예산 상한 4종 + 종료 조건 4종 | max_iteration/max_query/max_result/token |
| 7 | 전 단계 graceful fallback → 실패 시 legacy 단일 쿼리 경로 | 그래프 비중단 |
| 8 | 관측: `_step_output_summary`에 coverage·iteration·stop_reason | 기존 step tracking 재사용 |
| 9 | 단위 테스트 (TDD 필수 — 테스트 선행) | 종료 조건·폴백·반환 계약 |

### 2.2 Out of Scope

| # | 제외 항목 | 사유 |
|---|-----------|------|
| 1 | `internal_document_search`(내부 하이브리드) 적용 | 결과 포맷(청크)이 웹(XML)과 달라 Extractor 검증 부담 2배. 웹 검증 후 후속 사이클 |
| 2 | 모듈 내 AnswerGenerator | `final_answer` 노드가 이미 워커 결과를 종합하며 supervisor draft answer를 폐기하는 계약(`supervisor_nodes.py:281`). 이중 답변 위험 |
| 3 | `multi_query` 모듈 통합·폐기·활성화 | 별개 자산. 본 사이클에서 손대지 않음 |
| 4 | 기존 `search_pipeline.py` 로직 수정 | **교체 대기** 전제. 재사용 심볼 import만 |
| 5 | 프론트엔드 UI / 에이전트 빌더 설정 노출 | config 플래그로 충분. 에이전트별 노출은 후속 |
| 6 | 도메인 특화 검색 소스 하드코딩 (`site:fss.or.kr` 등) | CLAUDE.md §6-2 일반화 원칙. Replanner 프롬프트의 전략 **예시** 수준까지만 |
| 7 | 서브에이전트(depth>0) 경로 적용 | 1단계는 depth=0 워커 한정 |
| 8 | DB 스키마 변경 / 마이그레이션 | Evidence는 런타임 state, 영속화 없음 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|:--------:|
| **FR-01** | QuestionAnalyzer가 질문을 구조화하고 `search_strategy ∈ {single, parallel, iterative}`를 판정한다 | P0 |
| **FR-02** | `single` 판정 시 분해를 **생략**하고 쿼리 1개로 즉시 검색·반환한다 (LLM 호출 수 legacy 이하 보장) | P0 |
| **FR-03** | SearchPlanner가 `Requirement[]`와 `SearchQuery[]`를 **분리된 두 산출물**로 생성한다. Requirement 스키마는 일반형 — `{id, description, constraints: dict, status}`, `entity/metric/period`는 constraints의 **선택 키** | P0 |
| **FR-04** | SearchExecutor가 쿼리를 `asyncio.gather`로 병렬 실행하고, 개별 쿼리 예외는 격리해 나머지 결과를 살린다 | P0 |
| **FR-05** | EvidenceExtractor가 검색 결과를 `Evidence{requirement_id, content, source, confidence, attrs}`로 구조화한다. **source(URL/출처) 필수**, 원문에 없는 값 생성 금지 | P0 |
| **FR-06** | EvidenceStore가 iteration 간 Evidence를 **누적**하고 requirement_id별로 병합·중복 제거한다 | P0 |
| **FR-07** | SufficiencyEvaluator가 requirement별 `satisfied/missing`을 판정한다. `constraints`가 있으면 값 존재만으로 충족 처리하지 않고 제약(예: 시점 정합)을 함께 검증한다 | P0 |
| **FR-08** | SearchReplanner가 **미충족 requirement만** 대상으로 재쿼리를 생성한다. 이전 iteration의 전체 쿼리 이력을 입력받아 **표현 변경이 아닌 검색 전략 전환**을 수행하고, 대안이 없으면 `can_retry=false`를 반환한다 | P0 |
| **FR-09** | 4중 종료 조건을 모두 구현한다: ① coverage complete ② `iteration >= MAX_ITERATION` ③ no information gain(`new_evidence_count == 0`) ④ search exhaustion(`can_retry=false`) | P0 |
| **FR-10** | 예산 상한 4종을 도메인 정책 상수로 둔다: `MAX_SEARCH_ITERATION`, `MAX_QUERY_PER_ITERATION`, `MAX_RESULT_PER_QUERY`, 토큰 상한 | P0 |
| **FR-11** | 모든 LLM 단계가 graceful fallback한다. Analyzer/Planner 실패 시 **legacy 단일 쿼리 경로**로 폴백하고 그래프를 중단하지 않는다 | P0 |
| **FR-12** | 노드 반환 계약이 기존과 동일하다 — `format_search_result(worker_id, body)` 메시지 + `last_worker_id` + `token_usage` + `_step_output_summary` | P0 |
| **FR-13** | `search_pipeline_mode` config 키(`legacy` \| `deep`, 기본 `legacy`)로 노드 팩토리를 선택한다. 미지정·오타 값은 `legacy`로 안전 폴백 | P0 |
| **FR-14** | `_step_output_summary`에 `strategy / iteration / satisfied_count / total_requirements / stop_reason`을 기록한다 | P1 |
| **FR-15** | Evidence Store를 최종 반환 본문으로 렌더할 때 requirement별 그룹 + source를 보존한다 (`final_answer`가 소비) | P1 |
| **FR-16** | 미충족 requirement가 남은 채 종료하면 본문에 **명시적 미확보 표시**를 포함한다 (final_answer의 환각 방지) | P1 |

### 3.2 Non-Functional Requirements

| ID | 항목 | 기준 |
|----|------|------|
| NFR-01 | **아키텍처** | domain 레이어에 LangChain/LLM/외부 API 참조 금지. 정책은 순수 함수 |
| NFR-02 | **비용 상한** | `iterative` 최악 경로에서 LLM 호출 ≤ 12회, 검색 호출 ≤ 10회 (초기 예산 `MAX_ITERATION=2`) |
| NFR-03 | **무회귀** | `search_pipeline_mode=legacy`에서 기존 테스트 전량 통과, 동작 변화 0 |
| NFR-04 | **코딩 규칙** | 함수 40줄 이내, if 중첩 2단계 이내, `print()` 금지, config 하드코딩 금지 |
| NFR-05 | **로깅** | 각 노드 진입/종료에 구조화 로그. 예외는 스택 트레이스 포함(`logger.error(exception=e)`) |
| NFR-06 | **TDD** | 테스트 선행 필수 (Red → Green → Refactor) |
| NFR-07 | **일반성** | 금융 도메인 어휘를 코어 스키마·분기문에 하드코딩하지 않음 (프롬프트 예시는 허용) |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `search_pipeline_mode=legacy`에서 기존 테스트 전량 통과 (FAILED 목록 diff = 0)
- [ ] "A와 B의 X" 형태 질의에서 requirement 2개·독립 쿼리 2개가 생성됨 (테스트로 고정)
- [ ] iteration 2회차에 **이미 충족된 requirement의 쿼리가 재발행되지 않음** (테스트로 고정)
- [ ] 4중 종료 조건이 각각 독립 단위 테스트로 검증됨
- [ ] `single` 전략 경로의 LLM 호출 수가 legacy(≤4) 이하임을 테스트로 고정
- [ ] Analyzer/Planner 실패 주입 시 legacy 단일 쿼리 경로로 폴백하고 예외가 전파되지 않음
- [ ] 반환 메시지가 `is_search_result()`로 식별되고 `final_answer`가 정상 소비함
- [ ] 미충족 requirement 잔존 시 본문에 미확보 표시가 포함됨
- [ ] `verify-architecture` / `verify-logging` / `verify-tdd` 스킬 통과

### 4.2 Quality Criteria

| 항목 | 기준 |
|------|------|
| Gap Analysis Match Rate | ≥ 90% |
| 신규 모듈 테스트 커버리지 | 노드별 최소 1개 정상 + 1개 실패 폴백 테스트 |
| domain 레이어 순수성 | `domain/deep_search/`에 langchain/openai import 0건 |
| 기존 파일 변경량 | `search_pipeline.py` **0줄(불변, 최우선 기준)**, `workflow_compiler.py` ≤ 35줄, `config.py` ≤ 10줄, `main.py` ≤ 5줄 |

---

## 5. Risks and Mitigation

| # | 리스크 | 영향 | 완화 |
|---|--------|------|------|
| R1 | **비용·지연 증가** — 노드 4단계 추가로 LLM 호출이 legacy 대비 3~4배 | 높음 | `single` 전략 조기 탈출(FR-02) + 초기 예산 `MAX_ITERATION=2` 보수 설정 + 경량 pipeline LLM 재사용 + NFR-02 상한 테스트 |
| R2 | **Extractor 환각** — 검색 결과에 없는 수치를 생성 | 높음 | source 필드 필수화 + "원문에 없으면 추출하지 않는다" 프롬프트 규칙 + confidence 하한 미달 시 미채택. 기존 compress 프롬프트의 "원문에 없는 내용 추가·추측 금지" 규칙 계승 |
| R3 | **Replanner 동어반복** — 표현만 살짝 바꾼 무의미한 재검색 | 중간 | 이전 쿼리 **전체 이력**을 프롬프트에 주입 + "표현 변경은 실패로 간주, 검색 전략(소스·용어 체계·시점 범위)을 바꿔라" 명시 + 신규 쿼리가 기존과 과도히 유사하면 `can_retry=false` 처리 |
| R4 | **도메인 특화 오염** — `site:fss.or.kr`, BIS 등이 코어에 박힘 | 중간 | 스키마 일반형 확정(FR-03) + 코어 분기문에 도메인 어휘 금지(NFR-07) + 특화는 에이전트 시스템 프롬프트/데이터로 |
| R5 | **무한 루프·재귀 한도 초과** | 높음 | 상태머신 + 4중 종료 + LangGraph recursion_limit는 기존 `IterationLimitPolicy.derive_recursion_limit` 산식 하에서 여유 확보 확인 |
| R6 | **legacy 회귀** | 높음 | 기본값 `legacy` + 반환 계약 동일성 테스트 + `search_pipeline.py` 무수정 원칙 |
| R7 | ~~**미배선 데드코드화**~~ (multi_query 전철) — **해소됨 (2026-08-26)** | — | module-4에서 `config.search_pipeline_mode` → `main.py:2704` → `workflow_compiler` 분기까지 배선 완료. `SEARCH_PIPELINE_MODE=deep` 한 줄로 활성화된다 |
| R8 | ~~**"latest" 제약 해석 불가**~~ — **해소됨 (2026-08-26)** | — | `runtime-datetime-context`가 완료 배선되어 `datetime_block`이 `workflow_compiler.py:372`에서 주입된다. deep 파이프라인도 동일 파라미터를 받아 plan/extract/evaluate 세 단계 모두에 날짜를 전달한다 (Design D16, 테스트로 고정) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| 유형 | 경로 | 변경 |
|------|------|------|
| 신규 | `src/domain/deep_search/schemas.py` | Requirement / SearchQuery / Evidence / DeepSearchState / StopReason |
| 신규 | `src/domain/deep_search/policies.py` | DeepSearchBudgetPolicy, CoveragePolicy (순수 판정) |
| 신규 | `src/application/deep_search/prompts.py` | Analyzer / Planner / Extractor / Evaluator / Replanner 프롬프트 |
| 신규 | `src/application/deep_search/nodes.py` | 노드 함수 (전부 graceful fallback) |
| 신규 | `src/application/deep_search/evidence_store.py` | 누적·병합·dedup·렌더 |
| 신규 | `src/application/deep_search/workflow.py` | StateGraph 조립 + `create_deep_search_node()` |
| 신규 | `tests/domain/deep_search/`, `tests/application/deep_search/` | 단위 테스트 |
| 수정 | `src/config.py` | `search_pipeline_mode: str = "legacy"` 1줄 |
| 수정 | `src/api/main.py` | `search_pipeline_mode=settings.search_pipeline_mode` 주입 1줄 |
| 수정 | `src/application/agent_builder/workflow_compiler.py` | 배선 상수 4 + `__init__` 파라미터 1 + 헬퍼 4개(`_normalize_search_mode`/`_resolve_search_mode`/`_deep_search_policy`/`_create_search_node`) + 분기 교체 — **실측 +31줄** |
| **무수정** | `src/application/agent_builder/search_pipeline.py` | 심볼 import만 (교체 대기 전제) |

### 6.2 Current Consumers

| 소비자 | 영향 |
|--------|------|
| `category="search"` 워커를 가진 모든 커스텀 에이전트 | 기본값 `legacy`이므로 **무영향**. `deep` 전환 시 웹검색 워커만 경로 변경 |
| `final_answer` / `analysis` 노드 | `is_search_result()` 식별 계약 동일 → 무영향 |
| `quality_gate` 재시도 | 반환 메시지 형태 동일 → 무영향 |
| `internal_document_search` 워커 | 1단계 범위 밖 → legacy 유지 |
| 프론트엔드 | 변경 없음 |

### 6.3 Verification

```bash
# 1) 무회귀 (legacy 기본값)
pytest tests/application/agent_builder/ tests/domain/agent_builder/ -q

# 2) 신규 모듈
pytest tests/domain/deep_search/ tests/application/deep_search/ -q

# 3) 아키텍처·로깅·TDD 규칙
/verify-architecture
/verify-logging
/verify-tdd

# 4) 전체 회귀 (FAILED 목록 diff)
pytest -q
```

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

**Dynamic** — 기존 Thin DDD + LangGraph 스택 내부의 신규 모듈. 인프라·스키마 변경 없음.

### 7.2 Key Architectural Decisions

| # | 결정 | 근거 |
|---|------|------|
| **AD-1** | 기존 `search_pipeline.py`를 수정하지 않고 **동일 시그니처의 별도 팩토리**를 만든다 | 교체/롤백이 config 한 줄. 두 경로를 나란히 두고 A/B 가능 |
| **AD-2** | 배선은 **config 전역 플래그**(`search_pipeline_mode`) | `WorkerDefinition` 스키마·프론트 빌더 UI까지 파급되지 않음. 변경량 최소 |
| **AD-3** | 1단계 적용은 **웹검색(tavily) 한정** | 내부 하이브리드 검색은 결과 포맷이 달라 Extractor 검증 부담이 2배. 웹 검증 후 확장 |
| **AD-4** | 모듈은 **Evidence만 반환**, 최종 답변은 기존 `final_answer`가 생성 | 이미 supervisor draft answer를 폐기하는 계약이 존재. 답변 책임 중복 시 이중 답변 재발 |
| **AD-5** | Requirement 스키마는 **일반형 + constraints 확장** | CLAUDE.md §6-2 "일반화가 이긴다". `entity/metric/period`는 constraints의 선택 키로 두어 금융 케이스는 그대로, 개념 설명형 질문도 깨지지 않음 |
| **AD-6** | 종료 조건을 **domain 순수 정책**으로 분리 | LLM 없이 단위 테스트 가능. 4중 조건 각각 독립 검증 |
| **AD-7** | Replan은 **미충족 requirement만** 대상 | 토큰·검색 호출 절감의 핵심. Evidence Store가 이를 가능하게 함 |
| **AD-8** | 실패 시 폴백 목적지는 **legacy 단일 쿼리 검색** (그래프 중단 아님) | 기존 파이프라인의 §3 실패 분기 매트릭스 철학 계승 |

### 7.3 Clean Architecture Approach

```
domain/deep_search/          ← 순수 규칙 (LLM·외부 API 금지)
  schemas.py                 Requirement, SearchQuery, Evidence, DeepSearchState, StopReason
  policies.py                DeepSearchBudgetPolicy(상한), CoveragePolicy(종료 판정)
        ▲
application/deep_search/     ← 흐름 제어 (LangGraph, LLM 호출)
  prompts.py                 5종 system prompt
  nodes.py                   analyzer/planner/executor/extractor/evaluator/replanner
  evidence_store.py          누적·병합·렌더
  workflow.py                StateGraph + create_deep_search_node()
        ▲
application/agent_builder/workflow_compiler.py   ← 배선 (플래그 분기)
        ▲
infrastructure/web_search/tavily_tool.py         ← 도구 (무수정, 주입만)
```

- domain은 `HybridSearchResult` 같은 인프라 타입에 의존하지 않는다 (Evidence는 자체 타입).
- 노드는 `tool`, `pipeline_llm`, `logger`를 **주입받는다** — 팩토리 내부에서 세션·클라이언트를 생성하지 않는다.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

| 규칙 | 적용 |
|------|------|
| Thin DDD 레이어 책임 | domain=규칙, application=흐름, infrastructure=어댑터 |
| 함수 40줄 / if 중첩 2단계 | 노드 함수 분할 |
| `print()` 금지, 구조화 logger | 각 노드 진입·종료·실패 로깅 |
| 스택 트레이스 필수 | `logger.error(..., exception=e)` |
| config 하드코딩 금지 | 예산 상수는 domain 정책, 모드는 config 키 |
| TDD 선행 | Red → Green → Refactor |
| 메시지 규약 단일 출처 (D2) | `format_search_result` import — 재정의 금지 |

### 8.2 Conventions to Define/Verify

| 항목 | 내용 |
|------|------|
| StopReason enum | `COMPLETE / MAX_ITERATION / NO_GAIN / EXHAUSTED / FALLBACK` — 로그·요약 문자열 단일 출처 |
| Evidence 렌더 포맷 | requirement별 그룹 + source 보존 형식 (final_answer 소비 계약) |
| 미확보 표시 문구 | 미충족 requirement 명시 형식 (환각 방지) |

### 8.3 Environment Variables Needed

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SEARCH_PIPELINE_MODE` | `legacy` | `legacy` \| `deep`. 오타·미지정은 `legacy` 폴백 |

기존 `TAVILY_API_KEY`, `SEARCH_COMPRESS_THRESHOLD`는 그대로 사용한다.

### 8.4 Pipeline Integration

```bash
/pdca status                        # 현재 상태
/pdca design deep-search-pipeline   # 다음 단계 (3가지 설계안 비교)
```

---

## 9. Next Steps

1. `/pdca design deep-search-pipeline` — 3가지 아키텍처 옵션 비교 후 선택
2. Design에서 확정할 것: 노드별 structured output 스키마 확정, 5종 프롬프트 초안, 예산 상수 최종값, 종료 조건 우선순위, Evidence 렌더 포맷
3. `/pdca do deep-search-pipeline --scope module-1` — domain 스키마·정책부터 TDD
4. 웹검색 실측 후 `internal_document_search` 확장 여부를 별도 사이클로 판단

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-25 | 배상규 | 최초 작성 — Checkpoint 1/2 확정 사항 반영 (config 플래그 배선 / 웹검색 한정 / Evidence만 반환 / 일반형 스키마) |
| 1.1 | 2026-08-26 | 배상규 | R8 해소(`runtime-datetime-context` 완료 배선), R7 해소(module-4에서 config 플래그 배선 완료 — 미배선 데드코드화 방지), 환경변수 표에 실제 키 확정 |
| 1.2 | 2026-08-26 | 배상규 | **G-02 해소** — §4.2 변경량 기준을 실측 기반으로 정정(`workflow_compiler.py` ≤10줄 → ≤35줄). 헬퍼 4개가 필요해 원 추정이 비현실적이었음. `search_pipeline.py` 0줄은 최우선 기준으로 유지 |
