# KB 지식기반 파이프라인 — 청킹·저장·검색·라우팅 아키텍처

> 작성일: 2026-07-11
> 대상 범위: `knowledge_base` 업로드 경로(현행 KB 파이프라인) + 요약 계층 생성 + Routed Retrieval(3단계 라우팅 검색)
> 소스 기준: master 워킹트리 (V041~V047 마이그레이션 반영)

---

## 1. 한눈에 보기

```
[인제스트]
POST /api/v1/knowledge-bases/{kb_id}/documents
  → KnowledgeBaseUploadUseCase          (KB 조회·권한·프로파일 해석)
  → UnifiedUploadUseCase                (파싱 → 청킹 → 임베딩 → 저장)
      ├─ ClauseAwareStrategy            (조/항 분리, DB 프로파일 기반)
      ├─ Qdrant  : 벡터 (parent + child 청크)
      ├─ ES      : BM25 (형태소 분석 포함, _id = chunk_id)
      └─ MySQL   : document_metadata (문서 단위 메타)
  → SectionSummaryLauncher (비동기 백그라운드 잡)
      ├─ 섹션(조) 요약: 조별 LLM 1회 → 키워드 3~8 + 3줄 요약
      └─ 문서 요약: 섹션 요약 취합 → 5줄 요약 (키워드는 빈도 집계, LLM 0회)

[검색]
POST /api/v1/retrieval/routed  (또는 에이전트 RAG 도구 use_routed_search)
  → 1차: 문서 라우팅   (Qdrant, chunk_type=document_summary)
  → 2차: 섹션 라우팅   (Qdrant 벡터 + ES BM25 → RRF 융합, chunk_type=section_summary)
  → 3차: 청크 확장     (ES ids 쿼리, _id = section_ref = 조 parent chunk_id)
  → 폴백: 결과 < top_k 이면 legacy HybridSearch(RRF)로 보충
```

- **요약 계층은 사전 계산(오프라인)**: 검색 시 LLM 호출 0회, 임베딩 호출 1회(쿼리)뿐이다.
- **조/항 분리 규칙은 전부 DB(`chunking_profile.boundary_rules` JSON)에서 조절 가능** — 코드에 하드코딩된 정규식 없음. (§4 참조)

---

## 2. 인제스트 파이프라인 (업로드 → 청킹 → 저장)

### 2-1. 진입점과 계층

| 단계 | 위치 |
|------|------|
| API | `src/api/routes/knowledge_base_router.py:339` — `POST /api/v1/knowledge-bases/{kb_id}/documents` |
| KB UseCase | `src/application/knowledge_base/upload_use_case.py:51` — KB 조회, 권한 정책, 청킹 설정 해석, 요약 잡 기동 |
| 엔진 | `src/application/unified_upload/use_case.py:67` — 파싱→청킹→임베딩→3-스토어 저장 (KB/비KB 공용 엔진) |

처리 순서 (`UnifiedUploadUseCase.execute`):

1. 컬렉션 존재 확인 → 컬렉션 생성 시점 활동로그에서 **임베딩 모델 역추적** (`_resolve_embedding_model`, `use_case.py:216`) → MySQL `embedding_model` 테이블 조회.
2. **파싱**: `parser.parse_bytes()` → 페이지당 LangChain `Document` 1개.
3. **청킹**: `_build_strategy()` (`use_case.py:190`) — KB에서 내려온 `chunking_config`가 있으면 `clause_aware`, 없으면 legacy `parent_child`(2000/500/50 하드코딩).
4. `document_id = uuid4()` 발급, 모든 청크 메타에 `document_id / user_id / collection_name / kb_id / kb_name` 주입 (`use_case.py:92-98`).
5. **Qdrant + ES 동시 저장**: `asyncio.gather(_store_to_qdrant, _store_to_es)` (`use_case.py:100-108`).
6. **MySQL** `document_metadata` 저장 — document_id, chunk_count, chunk_strategy, **kb_id(V047)** (`use_case.py:132-143`).
7. 업로드 성공 시 KB UseCase가 **섹션 요약 잡 기동** (`upload_use_case.py:94`) — 실패해도 업로드에는 영향 없음.

### 2-2. 스토어별 저장 내용

| 스토어 | 단위 | 내용 | ID |
|--------|------|------|-----|
| **Qdrant** | 청크(parent+child) 1개 = 포인트 1개 | `content` + 메타(전부 `str()` 강제 변환) | **포인트 ID = 랜덤 uuid4** (`qdrant_vectorstore.py:62`) — 메타의 `chunk_id`와 다름 |
| **Elasticsearch** | 청크 1개 = 문서 1개 | `content`, `morph_keywords`, `morph_text`(형태소), chunk 메타 | **`_id` = chunk_id** (`use_case.py:298`) — 3차 확장의 근거 |
| **MySQL** | 문서 1행 | `document_metadata` (청크 단위 행 없음) | document_id |

- ES 인덱스: KB 경로는 `settings.es_index`(기본 `"documents"`, 단일 공유 인덱스)를 사용한다 (`main.py:2646`). Routed Retrieval도 같은 값을 쓰므로 정합. ※ legacy 파이프라인 노드(`dual_store_node.py:52`)는 `docs_{collection}` 인덱스를 쓰므로 **그 경로로 적재된 문서는 라우팅 검색이 못 본다** — §9 주의사항 참조.
- Qdrant 컬렉션은 첫 insert 시 벡터 차원 자동 감지 + COSINE으로 자동 생성 (`qdrant_vectorstore.py:36-48`).

---

## 3. 조/항 분리 로직 (ClauseAwareStrategy)

구현: `src/infrastructure/chunking/strategies/clause_aware_strategy.py` (전략명 `"clause_aware"`)

### 3-1. 알고리즘

```
전체 페이지 텍스트 join (+ offset→page 매핑 유지)
  └─ parent 패턴으로 분할  ("제N조의N" 우선, 없으면 "제N조")
       ├─ 첫 매치 이전 텍스트 → "(전문)" 세그먼트
       ├─ 패턴 전혀 없으면 → 문서 전체가 "(전문)" 1개 (fallback)
       └─ 각 조(parent) 세그먼트:
            ├─ parent_chunk_size(기본 2000토큰) 초과 시 토큰 분할 (같은 clause_title 공유)
            └─ child 분할:
                 ├─ child 패턴(항 ①…/호 N./목 가.)으로 경계 분할
                 ├─ chunk_size(기본 500토큰) 이하로 인접 세그먼트 greedy 병합 (boundary="clause")
                 └─ 병합 후에도 초과분은 토큰 분할 (boundary="token", overlap 적용)
  └─ 문서 전역으로 child의 chunk_index / total_chunks 재부여
```

핵심 지점:

- **패턴 선택은 "첫 매치 우선"**: priority 오름차순으로 시도해 문서에서 실제로 매치되는 첫 패턴 하나만 사용 (`_first_matching`, `:114`). 조의N 패턴이 우선순위 1이므로 "제3조의2"가 "제3조" 패턴에 잘못 잘리지 않는다.
- **계층은 2단**: parent(조) → child. 항·호·목은 별도 계층이 아니라 **child 경계 패턴**으로만 쓰이고, 이후 토큰 상한 내에서 greedy 병합된다. 즉 조→항→호 3단 트리가 아니다.
- **overlap은 토큰 분할 폴백에만 적용** (`base_token_chunker.py:56-69`, step = chunk_size − overlap). 항/호 경계 분할(boundary="clause")에는 overlap이 없다. parent끼리도 overlap 없음.
- 토큰 계산: `tiktoken` (`config.encoding_model`).
- 패턴 컴파일: `re.compile(p, re.MULTILINE)` (`chunking_factory.py:216-221`) — `^` 앵커가 각 줄 시작에 매치.

### 3-2. 청크 메타데이터

| 필드 | parent | child | 비고 |
|------|:---:|:---:|------|
| `chunk_type` | `"parent"` | `"child"` | 요약 계층은 `"section_summary"`/`"document_summary"` |
| `chunk_id` | uuid4 | uuid4 | ES `_id`로 사용 |
| `parent_id` | — | 소속 parent의 chunk_id | |
| `children_ids` | child id 목록 | — | Qdrant엔 문자열로 강제 변환되어 저장됨 (주의) |
| `clause_title` | 조 첫 줄 ≤100자 | 동일 | 예: "제5조(대출한도)" |
| `page_start/page_end` | ✓ | ✓ | offset→page 매핑에서 계산 |
| `boundary` | | `"clause"` \| `"token"` \| `"fallback"` | 분할 근거 추적 |
| `chunk_index/total_chunks` | ✓ | ✓(문서 전역 재부여) | |

---

## 4. 조/항 규칙은 DB에서 조절 가능한가? — **가능 (완전 DB 설정)**

### 4-1. `chunking_profile` 테이블 (V041)

| 컬럼 | 타입 | 의미 |
|------|------|------|
| `id` | VARCHAR(36) PK | uuid |
| `name` / `description` | VARCHAR | 프로파일 이름/설명 |
| **`boundary_rules`** | **JSON NOT NULL** | **`[{"pattern","priority","level":"parent\|child"}]` — 조/항 정규식 자체가 여기 저장** |
| `parent_chunk_size` | INT (기본 2000) | 조 토큰 상한 |
| `chunk_size` | INT (기본 500) | child 토큰 상한 |
| `chunk_overlap` | INT (기본 50) | 토큰 분할 시 overlap |
| `is_default` | TINYINT(1) | 전역 기본 프로파일 (유일성은 UseCase 단일 세션 보장) |
| `summary_llm_model_id` | VARCHAR(36) NULL (V043) | 요약 잡용 LLM. **NULL이면 요약 계층 생성 자체가 꺼짐** |
| `status` | VARCHAR(20) | `active` / `deleted` (soft delete — KB 참조 보존) |

시드된 기본 프로파일("법령·규정 기본", V041):

```
parent:  ^제[0-9]+조의[0-9]+   (priority 1)
         ^제[0-9]+조           (priority 2)
child :  ^[ ]*[①②③…⑮]        (항, priority 1)
         ^[ ]*[0-9]+[.]        (호, priority 2)
         ^[ ]*[가나다…하][.]    (목, priority 3)
```

**결론: 조/항 분리 정규식·우선순위·parent/child 레벨·토큰 상한·overlap 전부 DB 값이다.** `ClauseAwareStrategy`에는 정규식이 하드코딩되어 있지 않고, 팩토리(`chunking_factory.py:196-233`)가 프로파일의 문자열 패턴을 컴파일해 주입한다. 관리자 API로 패턴을 바꾸면(예: "Article N", "제N절" 등) **코드 변경 없이** 다른 문서 구조에 대응할 수 있다. 유일한 하드코딩은 매치 실패 시 세그먼트명 `"(전문)"` 뿐이다.

검증 정책(`src/domain/chunking_profile/policy.py`): 규칙 최대 50개, 패턴 ≤200자, parent 규칙 ≥1개 필수, 패턴은 실제 `re.compile`로 유효성 검사. parent_size 100~8000, child_size 100~4000, overlap 0~500, `overlap < chunk_size ≤ parent_size`. 기본 프로파일은 삭제 불가(409).

### 4-2. 프로파일 해석 우선순위 (`chunking_resolver.py`)

KB 테이블에도 V042로 오버라이드 컬럼이 추가됐다: `use_clause_chunking`(opt-in 스위치, 기본 0), `chunking_profile_id`(FK), `chunk_size`, `chunk_overlap`(NULL = 프로파일 값 late binding).

```
kb.use_clause_chunking == False
  → 조/항 분리 안 함. legacy parent_child(2000/500/50) 경로.
kb.use_clause_chunking == True
  → kb.chunking_profile_id가 있고 active면 그 프로파일
  → 없으면 is_default=1 프로파일
  → 그것도 없으면 legacy 폴백 (업로드는 절대 실패하지 않음)
토큰 값 우선순위:
  chunk_size    = kb.chunk_size    (NULL이면 프로파일 값)
  chunk_overlap = kb.chunk_overlap (NULL이면 프로파일 값)
  parent_chunk_size = 항상 프로파일 값
```

주의: clause 청킹이 활성인 KB에서는 업로드 API의 쿼리 파라미터 `child_chunk_size`/`child_chunk_overlap`가 **무시**된다 (경고 로그만 남음, `upload_use_case.py:142-150`).

### 4-3. 프로파일 관리 API

| 메서드/경로 | 설명 |
|-------------|------|
| `POST /api/v1/admin/chunking/profiles` | 생성 (admin 전용). body: name, boundary_rules[], parent_chunk_size, chunk_size, chunk_overlap, is_default, summary_llm_model_id |
| `GET /api/v1/admin/chunking/profiles`, `GET .../{id}` | 조회 |
| `PUT .../{id}` | 수정 |
| `PUT .../{id}/default` | 기본 프로파일 지정 |
| `DELETE .../{id}` | soft delete (기본 프로파일이면 409) |
| `GET /api/v1/chunking/profiles` | 일반 사용자 read-only (KB 생성 폼 프리필용) |

---

## 5. 요약 계층 생성 (섹션 요약 → 문서 요약)

업로드 성공 후 `SectionSummaryLauncher`(`section_summary/launcher.py:48`)가 in-process `asyncio.create_task`로 잡을 기동한다. 조건: `kb.use_clause_chunking == True` **그리고** 프로파일에 `summary_llm_model_id` 설정. 잡 상태는 MySQL `section_summary_job`(V044, document_id UNIQUE, 임베딩 provider/model 스냅샷 포함)에 기록된다.

`SummarizeSectionsUseCase.run`(`section_summary/use_case.py:71`):

1. **섹션 소스** = Qdrant에서 해당 문서의 `chunk_type="parent"` 포인트 스캔 (`qdrant_section_source.py:29`). 즉 **섹션 = 조(parent 청크)**. 최대 500섹션.
2. **섹션별 LLM 1회** (동시성 Semaphore 3): 키워드 3~8개 + 정확히 3줄 요약. structured output 우선, 미지원 모델은 JSON 프롬프트 폴백 (`llm_summarizer.py:71`).
3. `제목\n요약` 텍스트를 임베딩 → **ES 먼저, Qdrant 나중** 순서로 기록 (`summary_writer.py:39`) — Qdrant 포인트 존재가 완료 마커라서 재실행 시 멱등(idempotent).
4. 전 섹션 성공 시 **문서 요약** (`document_summary_step.py:164`): 섹션 요약 합이 입력 상한 이하면 LLM 1회로 5줄 요약, 초과 시 배치 중간요약 → 최종 병합 2단. **문서 키워드는 섹션 키워드 빈도 집계(top 15) — LLM 호출 없음**.

ID 규약 (멱등 업서트의 핵심):

- 섹션 요약 ID = `uuid5("section-summary:{section_ref}")`, `section_ref` = **원본 parent 청크의 chunk_id**
- 문서 요약 ID = `uuid5("document-summary:{document_id}")`
- 두 요약 모두 ES `_id` == Qdrant 포인트 ID (결정적 uuid5 공유)

또한 섹션 요약의 ES 문서는 `content`/`morph_*` 필드를 **의도적으로 뺀다** — 기존 BM25 검색에 요약이 섞여 나오지 않게 하기 위함. Qdrant 쪽은 `_apply_section_summary_guard`(`qdrant_vectorstore.py:166-192`)가 모든 벡터 검색에 `must_not chunk_type IN (section_summary, document_summary)`를 자동 부착해 일반 검색을 오염시키지 않는다. 호출자가 명시적으로 해당 chunk_type을 필터로 요청할 때만 가드가 해제(bypass)된다.

잡 조회/재시도 API: `GET /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/section-summary`, `POST .../section-summary/retry`.

---

## 6. 검색 파이프라인 — Routed Retrieval (3단계 라우팅)

진입점: `POST /api/v1/retrieval/routed` (`routed_retrieval_router.py:120`) 또는 에이전트 RAG 도구(§8). 오케스트레이터: `RoutedRetrievalUseCase.execute` (`routed_retrieval/use_case.py:50`).

| 단계 | 컴포넌트 | 스토어 | 동작 |
|------|----------|--------|------|
| 0 | — | OpenAI 임베딩 | 쿼리 임베딩 **1회** (전 단계 공유) |
| 1차 문서 라우팅 | `QdrantDocumentRouter` | Qdrant | `chunk_type=document_summary` (+ kb_id) 벡터 검색, doc_top_k(기본 5). **0건이면 즉시 빈 결과 반환**(short-circuit) → 폴백으로 |
| 2차 섹션 라우팅 | `HybridSectionRouter` | Qdrant + ES | 벡터: `chunk_type=section_summary AND document_id IN [1차 결과]` / BM25: `summary_text^1.5, summary_keywords` multi_match + 동일 필터 → **RRF 융합**, section_top_n(기본 10). 한쪽 스토어 장애 시 경고 후 나머지 한쪽으로 degrade |
| 3차 청크 확장 | `EsChunkExpander` | ES | `ids` 쿼리 1회: `_id IN [section_ref...]` → **조(parent) 본문 전체**를 가져옴. 이웃/자식 fan-out 없음 — parent가 곧 반환 단위 |
| 폴백 | `HybridSearchUseCase` | Qdrant + ES | `결과 수 < top_k`이면 legacy 하이브리드 검색으로 보충. dedup 키 = routed 결과의 section_ref(청크의 chunk_id/parent_id와 대조), `from_fallback=True` 마킹 |

### 계층 간 ID 계약

```
document_summary ──(document_id)──▶ section_summary ──(section_ref = parent chunk_id)──▶ raw parent 청크 (ES _id)
```

- 요약 2계층: ES `_id` == Qdrant 포인트 ID (uuid5 결정적) → 2차 RRF에서 두 스토어 히트가 같은 id로 융합됨("both" 판정 가능).
- **raw 청크: ES `_id` == chunk_id 이지만 Qdrant 포인트 ID는 무관한 uuid4** — 3차 확장이 Qdrant가 아니라 **ES ids 쿼리**인 이유가 바로 이것 (`es_chunk_expander.py:3-6` 주석에 명시).
- 2차에서 `section_ref` 없는 히트, 3차에서 ES에 없는 ref는 skip + 경고(전체 실패 아님).

### 응답과 관측성

응답(`RoutedSearchAPIResponse`)에는 청크 본문 외에 라우팅 근거가 실린다: 문서 후보(summary/keywords/score), 섹션 후보(summary, clause_title, vector_rank/bm25_rank/source), `fallback_used/fallback_count`, `document_candidates/section_candidates` 카운트. 에이전트 경로에서는 히트별로 `ai_retrieval_source`(V046 `query_context` 포함)에 `search_mode="routed"`로 기록된다.

---

## 7. 하이브리드 검색 · RRF · 설정값

RRF: `RRFFusionPolicy.merge` (`domain/hybrid_search/policies.py:33`) — `score = Σ weight × 1/(k + rank)`, 기본 k=60 (Cormack et al. 2009). source는 `both | bm25_only | vector_only`.

| 파라미터 | 기본값 | 범위(API) | 정의 위치 |
|----------|-------:|-----------|-----------|
| `doc_top_k` | 5 | 1~20 | `routed_retrieval/schemas.py:17` |
| `section_top_k(n)` | 10 | 1~50 | 〃 |
| `top_k` (routed) | 5 | 1~30 | 〃 |
| `rrf_k` | 60 | — | 〃 |
| `bm25_weight/vector_weight` | 0.5/0.5 | — | 〃 |
| hybrid `top_k` | 10 | 1~50 | `hybrid_search/schemas.py:9` |
| hybrid `bm25/vector_top_k` | 20/20 | 1~100 | 〃 |
| `vector_score_threshold` | 0.0 | — | 전역 `settings.rag_vector_score_threshold` (`config.py:41`), 에이전트별 `RagToolConfig.score_threshold` 오버라이드 |
| ES 인덱스 | `"documents"` | — | `settings.es_index` (`config.py:49`) |

**리랭커 없음** — 융합은 RRF뿐, cross-encoder/LLM 리랭크 단계는 없다. (legacy `RetrievalUseCase`에만 선택적 LLM compressor가 있으며 routed/에이전트 경로와 무관.)

이 값들은 **DB가 아니라 요청 파라미터 + config.py**로 조절한다. DB로 조절 가능한 것은 청킹 프로파일(§4)과 에이전트별 `RagToolConfig`(score_threshold, kb_id, use_routed_search 등)이다.

---

## 8. 에이전트 RAG 도구 경로와 KB 필터

`InternalDocumentSearchTool._arun` (`rag_agent/tools.py:132`):

```
① USE_RAG_SEARCH 권한 없음 → 거부 메시지
② 인증 컨텍스트 필터 적용 (READ_DEPARTMENT_DOCS 없으면 visibility=public 강제 주입)
③ use_routed_search=True → routed 시도
     degrade 조건(→ legacy로 폴스루):
       not_wired(DI 미주입) / filter_incompatible / error / empty
④ 아니면 use_multi_query → 멀티쿼리, 아니면 단일 하이브리드
```

- **filter_incompatible이 중요**: routed가 허용하는 필터 키는 `kb_id`뿐(+`viewer_department_ids`는 무시). `visibility`, `document_id` 등 다른 키가 있으면 routed를 포기하고 legacy로 degrade한다. 따라서 **부서문서 열람 권한이 없는 사용자는 visibility=public이 주입되어 항상 legacy 경로**를 탄다.
- **KB 필터(kb-rag-filter)**: `RagToolConfig.kb_id`가 1급 필드. `ToolFactory._merge_kb_filter`(`tool_factory.py:156`)가 metadata_filter에 병합하며 수동 `metadata_filter["kb_id"]`보다 우선. routed에선 `RoutedScope.kb_id` → 1차 Qdrant 필터 + 2차 ES term + 폴백 metadata_filter로 일관 적용. 2차 벡터 검색은 kb_id를 직접 걸지 않지만 1차 문서 집합을 통해 이행적으로 격리된다.
- KB 열람 권한(`KnowledgeBasePolicy.can_read_ref`): ADMIN 전체 / PUBLIC 전체 / PERSONAL 소유자 / DEPARTMENT 소속 — 검증 책임은 설정을 저장하는 UseCase 측.
- 결과 포맷: `[출처: filename > clause_title]` + 섹션 요약 1줄 + 원문. 폴백 청크는 평문 포맷.

폴백은 2중 구조다: (a) 도구 레벨 degrade → legacy search_mode, (b) routed UseCase 내부 폴백 → hybrid로 부족분 보충. 서로 독립.

---

## 9. 주의사항 / 알려진 함정

1. **Qdrant 포인트 ID ≠ chunk_id (raw 청크)** — 포인트 ID는 저장 시 uuid4로 새로 발급된다(`qdrant_vectorstore.py:62`). chunk_id는 payload 필드로만 존재. raw 청크를 ID로 찾을 땐 반드시 ES를 써야 한다.
2. **Qdrant 메타 문자열 강제 변환** — 업로드 시 모든 메타 값이 `str()` 처리되어 `children_ids`가 리스트 repr 문자열로 저장된다 (`unified_upload/use_case.py:262`). 반면 요약 계층의 `keywords`는 진짜 배열. payload를 파싱할 때 혼동 주의.
3. **임베딩 모델 일치가 하드 요구사항** — 요약 벡터는 업로드 시점의 기본 임베딩 모델로 생성되며 검색 시 기본 모델과 같아야 한다 (`routed_retrieval_router.py:126-127`). 잡 테이블에 provider/model 스냅샷이 남는다(V044).
4. **ES 인덱스 이원화** — 현행 KB 경로는 `settings.es_index`(공유 "documents")를 쓰지만, legacy 파이프라인 노드(`dual_store_node.py:52`)는 `docs_{collection}`에 적재한다. legacy 노드로 들어간 문서는 routed 2·3차가 조회하지 못한다(누락 ref는 경고만 남기고 조용히 skip).
5. **V047 이전 업로드 문서는 kb_id가 NULL** — KB 문서 목록에 나타나지 않고 kb_id 필터 검색에서도 빠진다.
6. **요약 없는 문서는 라우팅 불가** — `use_clause_chunking=0`이거나 프로파일에 `summary_llm_model_id`가 없으면 요약 계층이 안 생기고, 1차 라우팅 0건 → 전량 폴백(hybrid)으로 처리된다. 라우팅 품질은 요약 잡 완료 여부에 종속.
7. **E2E 실측 미수행** — 라우팅 4부작(청킹→섹션→문서 요약→라우팅 API)은 구현·단위검증 완료 상태이며, Qdrant/ES 실기동 E2E는 V047 적용 후 일괄 체크리스트로 이월되어 있다 (`docs/task-registry.md` 참조).

---

## 10. 관련 파일 색인

| 영역 | 파일 |
|------|------|
| KB 업로드 | `src/application/knowledge_base/upload_use_case.py`, `chunking_resolver.py` |
| 업로드 엔진 | `src/application/unified_upload/use_case.py` |
| 조/항 청킹 | `src/infrastructure/chunking/strategies/clause_aware_strategy.py`, `chunking_factory.py`, `base_token_chunker.py` |
| 프로파일 | `src/domain/chunking_profile/{entities,policy}.py`, `src/infrastructure/persistence/models/chunking_profile.py`, `src/application/chunking_profile/use_case.py` |
| 요약 잡 | `src/application/section_summary/{launcher,use_case,query_use_case}.py`, `src/infrastructure/section_summary/{qdrant_section_source,llm_summarizer,summary_writer,document_summary_step}.py`, `src/domain/section_summary/{entities,policy}.py` |
| 라우팅 검색 | `src/application/routed_retrieval/use_case.py`, `src/infrastructure/routed_retrieval/{qdrant_document_router,hybrid_section_router,es_chunk_expander}.py`, `src/domain/routed_retrieval/{schemas,interfaces,policy}.py` |
| 하이브리드 | `src/application/hybrid_search/use_case.py`, `src/domain/hybrid_search/{policies,schemas}.py` |
| 에이전트 도구 | `src/application/rag_agent/tools.py`, `src/infrastructure/agent_builder/tool_factory.py`, `src/domain/agent_builder/rag_tool_config.py` |
| 가드 | `src/infrastructure/vector/qdrant_vectorstore.py` (`_apply_section_summary_guard`) |
| API | `src/api/routes/{knowledge_base_router,admin_chunking_router,chunking_profile_router,routed_retrieval_router,hybrid_search_router}.py` |
| 마이그레이션 | `db/migration/V041`(chunking_profile+시드), `V042`(KB 컬럼), `V043`(summary_llm_model_id), `V044`(section_summary_job), `V046`(query_context), `V047`(document_metadata.kb_id) |
