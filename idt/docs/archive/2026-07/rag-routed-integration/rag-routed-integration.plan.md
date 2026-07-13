# rag-routed-integration Planning Document

> **Summary**: 검색 파이프라인 4부작이 만든 라우팅 검색(`RoutedRetrievalUseCase`)을 **에이전트의 내부 문서 검색 도구에 연결**한다. 기존 `search_mode`(hybrid/vector_only/bm25_only)는 **전혀 건드리지 않고**, `RagToolConfig`에 **독립 opt-in 필드 `use_routed_search`(기본 false)를 신설**해 에이전트 생성 시 사용자가 선택 → DB(`agent_worker.tool_config` JSON)에 저장 → 도구 실행 시 그 값으로 분기한다. 켜면 3계층 하강 라우팅, 끄거나 라우팅이 강등되면 **그 에이전트의 기존 search_mode 설정 그대로** 동작 — 동일 에이전트 구성에서 스위치만 바꿔 **교차검증(라우팅 vs 기존)**이 가능한 구조(사용자 요구). routed 결과는 **[출처: 문서명 > 조 제목] 헤더 + 섹션 요약 1줄 + 조 본문** 포맷으로 LLM에 전달한다. 프론트 에이전트 빌더 RAG 설정 패널에 토글을 추가하는 **풀스택** 사이클.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Author**: 배상규
> **Date**: 2026-07-09 (사용자 피드백 반영 개정: search_mode 확장 → 독립 opt-in 필드)
> **Status**: Draft
> **선행**: summary-routed-retrieval (완료 — `docs/archive/2026-07/`, `RoutedRetrievalUseCase` 싱글턴 + getter)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 라우팅 검색은 검증용 API로만 존재 — 실제 소비자인 에이전트(내부 문서 검색 도구)는 여전히 rawchunk 하이브리드만 사용. 또한 라우팅을 기존 search_mode 값으로 끼워 넣으면 기존 검색 방식 선택을 대체(갈아끼우기)하게 되어 교차검증이 어렵다. |
| **Solution** | `RagToolConfig`에 **독립 필드 `use_routed_search: bool = false`** 신설(기존 search_mode 무수정·직교). 에이전트 생성 시 선택 → tool_config JSON으로 DB 저장 → `InternalDocumentSearchTool`이 값에 따라 분기: true면 `RoutedRetrievalUseCase`, false/강등 시 기존 search_mode 경로 그대로. 결과는 근거 헤더 포맷으로 LLM 컨텍스트화. |
| **Function/UX Effect** | 에이전트 빌더 RAG 설정에 "라우팅 검색 사용" 토글(체크박스) 추가 — 기존 검색 방식 라디오는 그대로 유지되어 두 설정이 공존. 같은 구성의 에이전트를 토글만 달리해 만들어 답변 품질을 나란히 비교(교차검증) 가능. |
| **Core Value** | 4부작이 **실제 제품 경로(에이전트 대화)**에 연결되면서도 기존 검색 체계는 완전 보존 — off가 기본이라 기존 에이전트·신규 기본값 모두 무영향. 라우팅 품질은 실사용 관측(record_retrieval·폴백률)과 교차검증으로 판단 후 확산. |

---

## 1. Overview

### 1.1 Purpose

에이전트 RAG 도구에 라우팅 검색을 **기존 설정과 직교하는 opt-in 스위치**로 추가한다.

```
에이전트 대화 → search 노드 → InternalDocumentSearchTool
  use_routed_search = false (기본)  → 기존 경로: search_mode(hybrid|vector_only|bm25_only) 그대로 [무수정]
  use_routed_search = true          → RoutedRetrievalUseCase (3계층 하강 + 내장 폴백)
                                      └ 도구 레벨 강등(미배선·실패·필터 비호환) 시 → 기존 search_mode 경로
```

**교차검증 요구(사용자)**: 라우팅이 기존 검색을 대체하는 게 아니라 병존 — 동일 에이전트 구성에서 토글 차이만으로 비교 가능해야 하고, 강등 시 동작이 "그 에이전트의 기존 설정"과 정확히 일치해야 한다.

### 1.2 Background — 현재 구조 (2026-07-09 코드 확인)

**RagToolConfig와 저장·분기 경로** (신규 필드가 자연스럽게 얹히는 지점):
- 도메인 VO: `RagToolConfig`(frozen dataclass) — collection_name/es_index/metadata_filter/top_k/search_mode/rrf_k/tool_name/tool_description/score_threshold/`use_wiki_first: bool = False` (`domain/agent_builder/rag_tool_config.py:21-56`) — **bool opt-in 필드 선례(use_wiki_first) 존재**
- 요청 스키마: `RagToolConfigRequest`(Pydantic, `application/agent_builder/schemas.py:24-35`) — 필드 추가 지점
- 저장: `CreateAgentUseCase`가 `config.model_dump()`를 `agent_worker.tool_config` JSON에 저장 — **신규 bool은 자동 저장(마이그레이션 0)**
- 복원·주입: `ToolFactory.create` → `RagToolConfig(**tool_config)` → 평탄화 필드로 `InternalDocumentSearchTool` 생성 (`tool_factory.py:66-97,148-152`) — routed getter(`get_configured_routed_retrieval_use_case`, main.py 기존) 주입 지점
- 분기 실행: `InternalDocumentSearchTool._single_query_search`가 search_mode로 하이브리드 파라미터 결정 (`application/rag_agent/tools.py:154-162`) — use_routed_search 분기를 그 앞단에 추가
- **⚠️ `UpdateAgentUseCase`는 tool_config를 갱신하지 않음(기존 제약)** — 토글은 에이전트 생성 시에만 설정 가능(§5 리스크, 후속 해소)

**결과 포맷·관측 계약**:
- `_format_results`: `[출처: {source}]\n{content}` + `collected_sources` + hit별 best-effort `tracker.record_retrieval(...)` (`tools.py:182-233`) — routed 결과도 동일 계약(chunk_id=section_ref, metadata에 routed/폴백 표기)
- **점수 스케일**: 라우팅 score는 RRF(1/(k+rank)) — 기존 코사인/BM25와 절대 비교 불가 → metadata 구분 필수

**권한 필터 정합 (핵심 확인 지점)**:
- 도구는 부서 문서 권한 없으면 `metadata_filter["visibility"]="public"` 강제 (`tools.py:107-108`) — **요약 payload에는 visibility가 없어**(kb_id/user_id/collection_name만) 라우팅 단계에 그대로 적용하면 0건 → 부재 키 감지 시 **기존 search_mode 경로로 강등**이 안전 기본선(§4-4)

**프론트**:
- `RagConfigPanel.tsx` — search_mode 라디오(180-192)·**use_wiki_first 체크박스(221-228) 선례** → 동형 토글 추가. 타입 `types/ragToolConfig.ts`(`DEFAULT_RAG_CONFIG` 포함), 전송 `AgentBuilderPage → agentBuilderService.create(tool_configs)`
- 테스트 환경: Vitest `--pool=threads`, MSW per-file listen, 사전 실패 8건(회귀 오인 금지)

### 1.3 사용자 결정 사항

| 질문 | 결정 |
|------|------|
| LLM 전달 포맷 | **조 본문 + 요약 근거 헤더** — `[출처: 문서명 > 조 제목]` + 섹션 요약 1줄 (2026-07-09) |
| 사이클 범위 | **풀스택** — 빌더 토글 UI + `/api-cotract` 동기화 (2026-07-09) |
| 파라미터 노출 | **스위치만 + 기본값** — K/N은 기존 top_k에서 파생 (2026-07-09) |
| **통합 방식 (개정)** | **기존 search_mode를 갈아끼우지 않는다** — 독립 opt-in 필드를 에이전트 생성 시 선택·DB 저장·분기 처리. 기존 설정과 병존해 교차검증 가능해야 함 (2026-07-09 피드백) |

---

## 2. Scope

### 2.1 In Scope

**A. 독립 opt-in 필드 `use_routed_search` (백엔드)**
- [ ] `RagToolConfig`에 `use_routed_search: bool = False` 추가(use_wiki_first 선례와 동형) — **search_mode Literal·검증·기본값 무수정**
- [ ] `RagToolConfigRequest`에 동일 필드 추가 → `model_dump()` 경유 DB(JSON) 자동 저장, 마이그레이션 0
- [ ] 기존 tool_config(필드 부재)는 dataclass 기본값 false로 복원 — 기존 에이전트 완전 불변
- [ ] 라우팅 파라미터 파생: `top_k` → `RoutedParams(top_k=top_k, ...기본값)` (doc_top_k/section_top_n 파생 규칙 Design 확정), rrf_k 재사용

**B. 도구 분기 + 결과 변환**
- [ ] `ToolFactory`: routed getter 주입(main.py 에이전트 빌더 팩토리 배선) + use_routed_search=true인 도구에 전달
- [ ] `InternalDocumentSearchTool`: `use_routed_search` 분기 — true면 `RoutedRetrievalUseCase.execute`, **false는 기존 코드 경로 그대로(회귀 가드)**. 강등(미배선·실행 실패·필터 비호환) 시 해당 에이전트의 기존 search_mode 경로로 폴백 + warning (FR-09)
- [ ] multi-query 경로와의 조합 규칙은 Design 확정(routed는 원 질의만 라우팅 등)
- [ ] 결과 포맷: `[출처: {filename} > {clause_title}]` 헤더 + 섹션 요약 1줄 + 조 본문. 라우팅 내장 폴백 결과(`from_fallback`)는 기존 포맷
- [ ] `collected_sources`/`record_retrieval` 계약 준수 — metadata에 `routed`/`from_fallback` 표기(점수 스케일 구분)

**C. 필터·권한 정합**
- [ ] `metadata_filter` → `RoutedScope` 매핑: 요약 payload 존재 키(kb_id 등)만 라우팅 필터로, **부재 키(visibility 등) 감지 시 기존 search_mode 경로 강등 + warning**을 기본선으로 Design 비교 확정
- [ ] 권한 게이트(USE_RAG_SEARCH 거부, visibility 강제)는 분기와 무관하게 동일 동작 — 권한 누수 방향 차단

**D. 프론트 (풀스택, `/api-cotract`)**
- [ ] `types/ragToolConfig.ts`: `use_routed_search` 필드 + `DEFAULT_RAG_CONFIG`(false) 동기화
- [ ] `RagConfigPanel.tsx`: "라우팅 검색 사용(3계층 요약 — 교차검증용)" 체크박스(use_wiki_first 동형) + 설명 텍스트(기존 검색 방식 설정은 폴백/비교 기준으로 유지됨을 안내)
- [ ] 테스트: RagConfigPanel 토글 on/off·생성 요청 전송 케이스(MSW per-file, `--pool=threads`)

**E. 테스트 (TDD — 구현 전 작성, 백엔드)**
- [ ] VO/스키마: 필드 기본 false, 직렬화 왕복(model_dump→복원), 기존 config(필드 부재) 하위호환
- [ ] 도구 분기: true→라우팅 위임 / false→기존 경로(기존 3모드 테스트 무수정 통과) / 강등 시 기존 search_mode 경로 + warning
- [ ] 포맷·관측: 근거 헤더+요약+본문, 폴백 포맷, record_retrieval metadata 표기
- [ ] 필터 정합: 부재 키 강등 규칙, visibility 강제 시 누수 0
- [ ] ToolFactory: getter 주입/미주입 규칙

### 2.2 Out of Scope (후속)

| 항목 | 사유/비고 |
|------|-----------|
| `UpdateAgentUseCase`의 tool_config 갱신 지원 | 기존 제약 — 토글은 생성 시 설정만. 해소는 agent-tool-config-update 후속 |
| search_mode 값 확장("routed" 추가) | **사용자 피드백으로 폐기** — 기존 체계를 갈아끼우지 않음 |
| 라우팅 파라미터(K/N) 에이전트별 노출 | 스위치만(사용자 결정) — 실측 후 필요 시 |
| `score_threshold` 요청 스키마 갭 | 기존 이슈 별도 정리 |
| General Chat 라우팅 / routing-quality-eval(RAGAS) | 에이전트 도구 검증·실사용 데이터 축적 후 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| FR-01 | 에이전트 생성 시 `use_routed_search`를 선택할 수 있고 tool_config(JSON)로 DB에 저장된다. 기본값 false | High |
| FR-02 | true인 에이전트의 문서 검색 도구는 `RoutedRetrievalUseCase`를 실행한다(3계층 하강 + 내장 폴백) | High |
| FR-03 | **false이거나 필드가 없는(기존) 에이전트는 기존 search_mode 경로가 바이트 단위로 동일하게 동작한다** — search_mode 체계 무수정 | High |
| FR-04 | 라우팅 결과가 `[출처: 문서명 > 조 제목]` 헤더 + 섹션 요약 1줄 + 조 본문으로 LLM에 전달된다. 내장 폴백 결과는 기존 포맷 | High |
| FR-05 | 도구 레벨 강등(미배선·라우팅 실패·필터 비호환) 시 **그 에이전트의 기존 search_mode 설정 그대로** 검색 + warning — 교차검증 기준선 보존 | High |
| FR-06 | `collected_sources`/`record_retrieval`이 기존 계약대로 기록되고 metadata로 routed/폴백·점수 스케일이 구분된다 | High |
| FR-07 | 권한 게이트(USE_RAG_SEARCH, visibility 강제)가 분기와 무관하게 유효하다 — 요약 payload 부재 필터 키는 강등 규칙으로 안전 처리 | High |
| FR-08 | 라우팅 파라미터는 기존 `top_k`/`rrf_k` 파생 — 신규 설정 필드는 `use_routed_search` 하나뿐 | High |
| FR-09 | 에이전트 빌더 RAG 설정 패널 토글로 선택·저장(생성 시)할 수 있고, 기존 검색 방식 라디오는 그대로 유지된다 | High |
| FR-10 | 검색 실행 로그에 use_routed_search·강등/폴백 여부가 run 컨텍스트와 함께 남는다 | Medium |

### 3.2 Non-Functional Requirements

| ID | 요구사항 |
|----|----------|
| NFR-01 | 기존 search_mode 3모드·기존 에이전트·라우팅 API에 회귀 없음 (additive — bool 필드 + 분기 추가만, 마이그레이션 0) |
| NFR-02 | Thin DDD — 필드·검증은 도메인 VO, 분기·포맷은 도구(application), getter 주입은 main.py |
| NFR-03 | TDD — 백엔드 pytest 선작성, 프론트 Vitest(RTL+MSW per-file, `--pool=threads`) |
| NFR-04 | LLM 컨텍스트 상한 — 근거 헤더+요약 추가분 결과당 ~200자 이내(요약 1줄 절단 규칙 Design) |
| NFR-05 | 함수 40줄, config 하드코딩 금지(파생 상수는 정책/상수) |
| NFR-06 | LOG-001 — print 금지, exception= 필수 |
| NFR-07 | 프론트 사전 실패 8건 회귀 오인 금지 — 신규 실패 0 기준 |

---

## 4. 핵심 설계 방향 (Plan 레벨 결정, 상세는 Design)

1. **직교 스위치, 갈아끼우기 아님(사용자 피드백)**: `use_routed_search`는 search_mode와 독립 — 기존 설정은 그대로 저장·유지되고, 스위치 off/강등 시 정확히 그 설정으로 동작. 동일 구성 에이전트를 토글만 달리해 교차검증하는 것이 이 구조의 존재 이유. `use_wiki_first` bool 선례와 동형이라 코드·UI 관례도 일치.
2. **도구는 얇은 분기 어댑터**: 라우팅 로직·내장 폴백·dedup은 전부 `RoutedRetrievalUseCase`에 있음 — 도구는 "분기 + 결과 변환"만. 도구 레벨 강등(FR-05)은 유스케이스 진입 자체가 불가한 경우(미배선·필터 비호환·예외)에 한정.
3. **강등의 목적지는 '그 에이전트의 기존 설정'**: 일반적인 폴백(하이브리드 고정)이 아니라 에이전트별 search_mode 경로 — 교차검증에서 off 기준선과 강등 동작이 일치해야 비교가 성립.
4. **필터 정합은 안전 우선**: metadata_filter의 요약 payload 부재 키(visibility 등)는 조용한 0건을 만든다 — 부재 키 감지 시 기존 경로 강등이 기본선(권한 필터는 기존 경로가 처리 → 누수 방향 차단). 사후 필터 방식은 Design에서 비교.
5. **관측으로 교차검증 데이터 축적**: record_retrieval metadata(`routed`/`from_fallback`) + 도구 로그(use_routed_search·강등 사유) — 라우팅 vs 기존 비교와 백필 우선순위 판단의 원천.
6. **기존 제약 존중**: Update의 tool_config 불변은 이번에 안 풂 — 검증은 신규 에이전트 2개(토글 on/off)로 수행.

---

## 5. Risks & Mitigations

| 리스크 | 영향 | 대응 |
|--------|------|------|
| visibility 등 요약 payload 부재 필터 키 | 라우팅 0건(무의미한 스위치) 또는 권한 누수 | 부재 키 감지 시 기존 경로 강등(기본선) — 누수 방향은 구조 차단, 강등 사유 로그로 관측 |
| 강등이 잦으면 토글이 무의미해 보임 | 교차검증 신뢰 저하 | FR-10 로그 + record_retrieval 관측으로 강등률 가시화 → 백필/필터 개선 우선순위 |
| RRF 점수와 기존 점수 스케일 불일치 | 관측 오독 | metadata 구분(FR-06) + 문서 명시 — 혼합 비교 금지 |
| 기존 에이전트는 토글 변경 불가(Update 제약) | 교차검증은 신규 생성 2개로 수행해야 | Out of scope 명시 + agent-tool-config-update 후속 |
| multi-query × 라우팅 조합 비용 | 지연 증가 | Design 확정(원 질의만 라우팅 등) |
| 근거 헤더 컨텍스트 증가 | 토큰 비용 | 요약 1줄 절단(NFR-04) |

---

## 6. Acceptance Criteria

- [ ] `use_routed_search: true`로 에이전트 생성(API) → tool_config JSON에 저장 확인 → 도구가 RoutedRetrievalUseCase 위임(단위 테스트)
- [ ] false/필드 부재 에이전트는 기존 3모드 테스트 전량 무수정 통과(회귀 가드) — search_mode 체계 무변경
- [ ] 동일 구성 + 토글만 다른 에이전트 2개가 각각 라우팅/기존 경로로 동작(교차검증 시나리오 테스트)
- [ ] 강등 상황(미배선·visibility 강제)에서 해당 에이전트의 search_mode 경로로 검색 + warning, 권한 누수 0
- [ ] LLM 전달 텍스트에 근거 헤더+요약 1줄+본문 포함, record_retrieval metadata에 routed/폴백 구분
- [ ] 프론트: 토글 on → 생성 요청 `tool_configs.use_routed_search=true` 전송(RTL), 기존 라디오 동작 불변, tsc 0, 신규 실패 0
- [ ] `/verify-architecture`, `/verify-tdd`, `/verify-logging` 통과

---

## 7. 후속 로드맵 (참고)

1. **agent-tool-config-update**: 에이전트 수정 시 tool_config 갱신 — 기존 에이전트의 토글 전환 허용
2. **routing-quality-eval**: 교차검증 에이전트 쌍 + record_retrieval/강등률 데이터 + RAGAS 비교 → 기본값 전환 판단
3. **section-summary-backfill**: 강등·폴백률 높은 KB부터 기존 문서 일괄 요약
4. **general-chat-routed**: General Chat 검색 경로 라우팅 옵션
