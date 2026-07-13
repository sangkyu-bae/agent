# rag-routed-integration Design Document

> **Plan**: `docs/01-plan/features/rag-routed-integration.plan.md` (개정판 — 독립 opt-in 필드)
> **Author**: 배상규
> **Date**: 2026-07-09
> **Status**: Draft
> **선행**: summary-routed-retrieval (완료 — `RoutedRetrievalUseCase` + `get_configured_routed_retrieval_use_case`)

---

## 1. 설계 요약

기존 search_mode 체계를 **무수정 보존**하고, 독립 opt-in `use_routed_search`로 분기한다. 4개 블록:

1. **필드 신설**: `RagToolConfig.use_routed_search: bool = False`(use_wiki_first 동형) + `RagToolConfigRequest` 동기 — JSON 자동 저장, 마이그레이션 0, 기존 config 부재 키는 기본 False 복원
2. **도구 분기**: `InternalDocumentSearchTool._arun`에서 권한 게이트 통과 후 routed 시도 → **강등(None 반환) 시 기존 경로(그 에이전트의 search_mode) 계속** — 교차검증 기준선 보존
3. **결과 변환**: `[출처: 문서명 > 조 제목]` + 요약 1줄 + 본문 포맷 + `collected_sources`/`record_retrieval` 기존 계약(metadata에 routed/폴백 표기)
4. **풀스택**: ToolFactory getter 주입 + main.py 배선, 프론트 토글(체크박스, 위키 토글 동형) + 타입 동기화

### 코드 확인으로 확정된 사실 (2026-07-09)

| 확인 항목 | 결과 | 영향 |
|-----------|------|------|
| bool opt-in 선례 | `RagToolConfig.use_wiki_first: bool = False` (`rag_tool_config.py:42`) — `__post_init__` 검증 불요, `ToolFactory._select_search`가 소비 | `use_routed_search`를 바로 아래 동형 배치 (D1) |
| 하위호환 복원 | `ToolFactory._parse_rag_config`: `RagToolConfig(**tool_config)` (`tool_factory.py:148-152`) — 부재 키는 dataclass 기본값 | 기존 저장 config → False 자동, FR-03 충족 |
| **권한 필터가 항상 키를 주입** | `_apply_auth_filter` (`tools.py:96-113`): READ_DEPARTMENT_DOCS 없으면 `visibility="public"`, **있으면 `viewer_department_ids` 주입** — effective filter에 항상 비-스코프 키 존재 | 강등 규칙을 "부재 키 전부 강등"으로 하면 **상시 강등(토글 무의미)** → 키별 취급 분류 필수 (D4) |
| viewer_department_ids의 기존 취급 | 주석 명시 "Repository 미지원 시 무시" (`tools.py:110-112`) — 기존 hybrid 경로도 실효 없는 키 | 라우팅에서도 **무시(강등 사유 아님)** — 기존 경로와 동일 취급 (D4) |
| 분기 삽입 지점 | `_arun`(`tools.py:115-134`): 권한 게이트(123-124) → effective filter 합성(128-130) → multi/single 분기(132-134) | routed 시도를 필터 합성 직후·multi 분기 앞에 삽입 (D3) |
| ToolFactory 주입 구조 | getter 패턴 기존(`hybrid_search_use_case_getter`, `tool_factory.py:24,53-58`) + 평탄 필드 전개(79-97) | `routed_retrieval_getter` additive 파라미터 + 도구 필드 2개 전달 (D2) |
| routed 싱글턴 getter | `get_configured_routed_retrieval_use_case` (main.py, summary-routed-retrieval D10) | ToolFactory 생성처에 getter 연결만 — 신규 배선 최소 (D2) |
| record_retrieval 계약 | `_format_results`(`tools.py:182-233`): hit별 best-effort, `hit.metadata`/`hit.id`/`hit.score` 소비 | routed 결과는 RoutedChunk → 전용 포맷터로 동일 계약 충족 (D6) |
| 프론트 토글 선례 | `RagConfigPanel.tsx:218-238` use_wiki_first 체크박스 블록, `ragToolConfig.ts:11,44` optional bool + DEFAULT | 동형 블록 추가 + 타입/DEFAULT 동기화 (D9) |
| RoutedChunk 근거 | `document.filename/summary`, `section.summary/clause_title`, `from_fallback` (routed_retrieval schemas) | 포맷 재료 완비 — 추가 조회 0 (D6) |

---

## 2. 설계 결정 (Decisions)

| ID | 결정 | 근거 |
|----|------|------|
| D1 | `RagToolConfig`에 `use_routed_search: bool = False` 추가(use_wiki_first 바로 아래, 주석으로 교차검증 목적 명시). `RagToolConfigRequest`에 동일 필드. **search_mode Literal·`_VALID_SEARCH_MODES`·`__post_init__` 무수정** | Plan 개정(갈아끼우기 금지). bool은 검증 불요, `model_dump()` 경유 JSON 자동 저장 — 마이그레이션 0 |
| D2 | `ToolFactory.__init__(..., routed_retrieval_getter: Callable[[], Any] \| None = None)` additive. `create()`의 internal_document_search 분기에서 도구에 `use_routed_search=rag_config.use_routed_search`, `routed_retrieval_getter=self._routed_retrieval_getter` 전달. main.py의 **에이전트 빌더 ToolFactory**(RAG 실사용처)에 `get_configured_routed_retrieval_use_case` 연결. 미들웨어 에이전트 ToolFactory는 hybrid getter조차 없는 컨텍스트(RAG 도구 비실사용)라 의도적 제외 — 해당 경로에서 toggle=true여도 `not_wired` 안전 강등 | getter 패턴 선례(hybrid getter) — lifespan 순서 무관. 미주입(None)이면 도구가 강등 처리(FR-09) |
| D3 | **도구 분기 (`_arun`)**: 권한 게이트·effective filter 합성 후, `use_routed_search=True`면 `_routed_search(query)` 시도 — 반환 `str`이면 그대로 응답, **`None`(강등)이면 기존 코드 흐름(multi/single) 그대로 계속**. false면 분기 코드 자체를 타지 않음(기존 경로 바이트 동일) | FR-03/FR-05. 강등의 목적지가 "그 에이전트의 기존 설정"이 되는 구조 — 교차검증 기준선 보존 |
| D4 | **강등 규칙 (필터 정합)**: effective_metadata_filter의 키를 3분류 — ① `kb_id` → `RoutedScope.kb_id` 매핑 ② `viewer_department_ids` → **무시**(기존 hybrid도 실효 없음, 주석 근거 — 동일 취급) ③ `visibility` 또는 **그 외 모든 키**(사용자 custom 필터 포함) → **강등**(요약 payload에 존재 보장 없음 → 조용한 0건 방지 + visibility는 권한 누수 방향 차단). 강등 사유를 warning 로그에 명시 | Plan §4-4. "부재 키 전부 강등"이면 부서 권한 사용자가 상시 강등(코드 확인) — 키별 분류가 유일한 실효 규칙. 누수 방향: visibility 강제 사용자는 항상 기존 경로(권한 필터 적용됨) |
| D5 | **강등 사유 4종**: ⓐ getter 미주입/None 반환 ⓑ D4 ③ 필터 키 ⓒ `RoutedRetrievalUseCase.execute` 예외 ⓓ 결과 0건(내장 폴백까지 비었을 때 — 기존 경로가 더 넓은 recall 가능). 각각 warning + reason 코드(`not_wired`/`filter_incompatible`/`error`/`empty`) — FR-10 관측 | 교차검증 신뢰: 강등률·사유가 로그로 집계 가능해야 토글 실효성 판단 가능(Plan 리스크) |
| D6 | **routed 결과 포맷터 `_format_routed_results`(신설)**: RoutedChunk별 — 라우팅 결과는 `[출처: {document.filename or document_id} > {clause_title}]` 헤더 + `요약: {section.summary 첫 줄[:150]}` + 본문 / 내장 폴백 결과(`from_fallback`)는 `[출처: {clause_title or document_id}]` + 본문(기존 포맷 준용). `collected_sources`에 DocumentSource(chunk_id=section_ref, score=chunk.score) 누적, hit별 `record_retrieval(document_id, chunk_id=section_ref, score, metadata={"search": "routed", "from_fallback": ..., "clause_title": ...})` best-effort — 기존 `_format_results` 계약 동형 | 사용자 결정(근거 헤더). 요약 1줄 150자 절단 = NFR-04(결과당 추가 ~200자 이내). metadata 표기로 RRF 점수 스케일 구분(FR-06) |
| D7 | **multi-query 조합**: `use_routed_search=True`면 **원 질의만 라우팅**(multi-query 우회). 강등 시에는 원래 규칙(use_multi_query → multi) 적용 | 라우팅 자체가 요약 계층으로 recall 보완 — 쿼리 재작성 N개 × IO 5회 비용 회피. 강등 시 기존 동작 완전 재현 |
| D8 | **파라미터 파생**: `RoutedParams(top_k=self.top_k, rrf_k=self.rrf_k)` — doc_top_k(5)/section_top_n(10)/weights(0.5)는 RoutedParams 기본값 그대로. tool top_k 상한 20 ≤ RoutedParams top_k 상한 30이라 검증 충돌 없음(코드 확인) | 사용자 결정(스위치만). 신규 상수·설정 0 |
| D9 | **프론트**: `ragToolConfig.ts`에 `use_routed_search?: boolean` + `DEFAULT_RAG_CONFIG`에 `false`. `RagConfigPanel.tsx`에 위키 토글(218-238) 동형 체크박스 블록 — 라벨 "라우팅 검색 (3계층 요약)", 설명 "문서·섹션 요약을 거쳐 관련 조문을 좁혀 검색합니다. 요약 데이터가 없거나 검색이 실패하면 위 검색 모드로 자동 전환됩니다 (교차검증용)". 기존 검색 모드 라디오 무변경 | Plan D항. `/api-cotract` — 백엔드 필드와 1:1 |
| D10 | **로깅**: routed 성공 시 도구 info 1줄(`routed_results`/`fallback_used`(내장)/`request_id`), 강등 시 warning(reason 코드). 도구 logger는 기존 주입 필드(`self.logger`, None 허용 — None이면 로그 스킵, 기존 관례) | FR-10. record_retrieval와 합쳐 교차검증 데이터 |
| D11 | **테스트 전략**: 기존 도구 테스트 무수정 통과가 FR-03의 증명 — routed 케이스는 신규 테스트 파일/클래스로 분리(fake RoutedRetrievalUseCase getter). 프론트는 RagConfigPanel.test.tsx에 케이스 추가(MSW per-file, `--pool=threads`) | NFR-01/03. 사전 실패 8건 오인 금지 |

---

## 3. 파일 구조 (신규/수정)

```
idt/ (백엔드)
├── src/
│   ├── domain/agent_builder/rag_tool_config.py          [수정: use_routed_search 필드 (D1)]
│   ├── application/agent_builder/schemas.py             [수정: RagToolConfigRequest 필드 (D1)]
│   ├── application/rag_agent/tools.py                   [수정: 분기 _routed_search + _format_routed_results (D3~D7)]
│   ├── infrastructure/agent_builder/tool_factory.py     [수정: getter 파라미터 + 전달 (D2)]
│   └── api/main.py                                      [수정: ToolFactory 생성처에 getter 연결 (D2)]
└── tests/
    ├── application/rag_agent/test_tools_routed.py       [신규: 분기·강등 4사유·포맷·record_retrieval·multi-query 우회]
    ├── domain/agent_builder/test_rag_tool_config.py     [수정: 필드 기본값·하위호환(부재 키 복원)]
    └── infrastructure/agent_builder/test_tool_factory.py [수정: getter 주입·미주입 전달]

idt_front/ (프론트)
├── src/types/ragToolConfig.ts                           [수정: 필드 + DEFAULT (D9)]
├── src/components/agent-builder/RagConfigPanel.tsx      [수정: 토글 블록 (D9)]
└── src/components/agent-builder/RagConfigPanel.test.tsx [수정: 토글 on/off·onChange 전달 케이스]
```

**마이그레이션 0 · config 0 · search_mode 체계 무수정** (D1/D8)

---

## 4. 흐름

```
_arun(query)
  1. 권한 게이트: USE_RAG_SEARCH 없으면 거부                        [기존 무수정]
  2. effective_filter = _apply_auth_filter(...)                    [기존 무수정]
  3. if use_routed_search:
       routed = await _routed_search(query)                        [D3]
         ├ getter 미주입 → None (reason=not_wired)                 [D5-ⓐ]
         ├ 필터 3분류: kb_id→scope / viewer_department_ids→무시 /
         │  visibility·기타 키 → None (reason=filter_incompatible)  [D4, D5-ⓑ]
         ├ RoutedRetrievalUseCase.execute(query, scope,
         │    RoutedParams(top_k, rrf_k)) 예외 → None (error)       [D5-ⓒ, D8]
         ├ 결과 0건 → None (empty)                                  [D5-ⓓ]
         └ 성공 → _format_routed_results(...) 반환                  [D6]
       if routed is not None: return routed
       # None(강등) → 아래 기존 흐름으로 계속 (multi/single — 그 에이전트의 search_mode)
  4. use_multi_query 분기 → _multi_query_search / _single_query_search   [기존 무수정]
```

---

## 5. 테스트 계획 (TDD — 구현 전 작성)

| 파일 | 핵심 케이스 |
|------|------------|
| `test_rag_tool_config.py` (수정) | 필드 기본 False, `RagToolConfig(**{기존 config dict})` 부재 키 복원, model_dump 왕복 |
| `test_tools_routed.py` (신규) | ① true+성공 → routed 포맷 반환·기존 검색 미호출 ② false → 분기 미진입(기존 hybrid 호출 — 기준선) ③ 강등 4사유 각각 → 기존 search_mode 경로 호출 + warning(reason) ④ visibility 강제(부서 권한 없음) → filter_incompatible 강등(누수 0) ⑤ viewer_department_ids만 있으면 라우팅 진행(무시 확인) ⑥ kb_id → RoutedScope 매핑 ⑦ 포맷: 근거 헤더+요약 150자 절단+본문 / from_fallback 기존 포맷 ⑧ collected_sources·record_retrieval(metadata routed 표기) ⑨ use_multi_query=true여도 routed 성공 시 multi 미호출, 강등 시 multi 호출 |
| `test_tool_factory.py` (수정) | getter 주입 시 도구 필드 전달, 미주입 시 None 전달, use_routed_search 평탄 전개 |
| 기존 도구 테스트 | **무수정 통과 = FR-03 증명** |
| `RagConfigPanel.test.tsx` (수정) | 토글 렌더·기본 off, 클릭 → onChange({...use_routed_search: true}), 기존 라디오 동작 불변 |

---

## 6. 구현 순서 (Do 체크리스트)

1. **백엔드 필드(D1)**: VO + Request 스키마 (+ 하위호환 테스트 선작성)
2. **도구 분기(D3~D7)**: `_routed_search`(강등 4사유·필터 3분류) + `_format_routed_results` (+ test_tools_routed.py 선작성 — 9케이스)
3. **ToolFactory(D2)**: getter 파라미터·전달 (+ 테스트) → main.py 생성처 전수 grep·연결
4. **프론트(D9)**: 타입/DEFAULT → 토글 블록 → RTL 케이스 (`--pool=threads`)
5. **검증**: 백엔드 신규+기존 도구·agent_builder 스위트, 프론트 tsc+대상 테스트, `/verify-architecture`·`/verify-tdd`·`/verify-logging`
