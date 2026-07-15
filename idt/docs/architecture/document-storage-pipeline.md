# 문서 저장 파이프라인 (Document Storage Pipeline)

> Last Updated: 2026-07-14
> 대상 독자: 백엔드 개발자, 파이프라인 튜닝/디버깅 담당자
> 관련 문서: `architecture/kb-chunking-retrieval-routing.md`(검색 측), `architecture/elasticsearch-strategy.md`, `rules/rag-retrieval.md`

문서 하나를 업로드하면 **어떤 코드가, 어떤 순서로, 어떤 저장소에, 어떤 형태로** 데이터를 남기는지를 코드 기준으로 풀어서 설명한다.

---

## 1. 한눈에 보는 전체 흐름

```
[파일 업로드]
     │
     ├─ 일반 업로드  POST /api/v1/documents/upload-all          (unified_upload_router.py)
     └─ KB 업로드    POST /api/v1/knowledge-bases/{kb_id}/documents (knowledge_base_router.py)
            │  KB 권한검증 + 물리 컬렉션 자동결정 + kb_id/kb_name 주입 + 청킹설정 해석
            ▼
   UnifiedUploadUseCase.execute()          ← 두 경로가 합류하는 단일 파이프라인
            │
   ① 사전 검증        컬렉션 존재 확인 + 임베딩 모델 결정
   ② 파싱             PDF bytes → 페이지당 LangChain Document
   ③ 청킹             parent_child(기본) 또는 clause_aware(KB opt-in)
   ④ 메타데이터 주입   document_id(uuid4) / user_id / collection_name / kb_id...
   ⑤ 병렬 저장         asyncio.gather ──┬─ Qdrant (임베딩 + 벡터 upsert)
                                        └─ Elasticsearch (형태소 분석 + bulk index)
   ⑥ MySQL 기록        document_metadata 1행 (best-effort)
   ⑦ 감사 로그         activity_log (ADD_DOCUMENT)
   ⑧ 상태 판정         completed / partial / failed
            │
            ▼ (KB 경로 + 요약 opt-in 시에만)
   ⑨ 섹션 요약 잡 킥오프 (백그라운드 asyncio.create_task)
        섹션(조)당 LLM 요약 → section_summary 계층 저장
        → 전 섹션 완료 시 문서 요약 자동 체이닝 → document_summary 계층 저장
```

최종적으로 문서 1개는 **4곳**에 데이터를 남긴다:

| 저장소 | 데이터 | 용도 |
|--------|--------|------|
| **Qdrant** (벡터) | 청크별 벡터 point (+요약 계층 point) | 벡터/하이브리드/라우팅 검색 |
| **Elasticsearch** | 청크별 문서 (형태소 키워드 포함) | BM25 키워드 검색, 본문 확장 |
| **MySQL** `document_metadata` | 문서 1행 | 문서 목록/브라우징의 진실 소스 |
| **MySQL** `activity_log` / `section_summary_job` | 감사 이력 / 요약 잡 상태 | 운영 추적, 요약 진행률/재시도 |

---

## 2. 진입점: 두 개의 업로드 경로

### 2-1. 일반 업로드 — `POST /api/v1/documents/upload-all`

`src/api/routes/unified_upload_router.py`

- 파라미터: `file`(multipart), `user_id`, `collection_name`(대상 Qdrant 컬렉션), `child_chunk_size`(기본 500), `child_chunk_overlap`(기본 50)
- 물리 컬렉션을 **호출자가 직접 지정**한다. `extra_metadata` 없음 → kb_id가 주입되지 않아 `document_metadata.kb_id = NULL`.
- 즉시 `UnifiedUploadUseCase.execute()` 위임.

### 2-2. KB 업로드 — `POST /api/v1/knowledge-bases/{kb_id}/documents`

`src/application/knowledge_base/upload_use_case.py` (`KnowledgeBaseUploadUseCase`)

일반 업로드를 감싸는 래퍼로, 위임 전에 4가지를 처리한다:

1. **KB 존재/권한 검증** — `KnowledgeBasePolicy.can_write(user, kb, dept_ids)`. 소유자/부서/scope 규칙 위반 시 403.
2. **물리 컬렉션 자동 결정** — 사용자는 컬렉션을 모른다. `kb.collection_name`(KB 생성 시 관리자 컬렉션에 배정된 값)을 사용.
3. **격리 메타데이터 주입** — `extra_metadata={"kb_id": kb.id, "kb_name": kb.name}`. 이 두 키가 Qdrant payload와 ES 문서 양쪽에 실려 **단일 물리 컬렉션 안에서 KB 단위 논리 격리**를 만든다 (kb_id는 불변 UUID라 KB 이름을 바꿔도 벡터 재태깅 불필요).
4. **청킹 설정 해석** — `ChunkingSettingsResolver`가 `kb.use_clause_chunking` 여부를 보고:
   - `false` → `None` 반환 → 기본 `parent_child` 경로 (Query 파라미터의 child size/overlap 사용)
   - `true` → `chunking_profile`(관리자 CRUD 테이블)에서 경계 정규식/토큰 설정을 **업로드 시점에 late-binding**으로 읽어 `clause_aware` 설정 구성. 이때 Query 청킹 파라미터는 무시(경고 로그).

업로드 성공 후에는 §6의 **섹션 요약 잡 킥오프**를 시도한다 (실패해도 업로드 결과에 영향 없음 — FR-09).

> 이 외에 레거시 `POST /api/v1/ingest/pdf`, 엑셀 업로드(`excel-upload-chunk-api`), 미리보기(`preview_router`) 경로가 있으나 본 문서는 주 경로인 unified upload 계열만 다룬다.

---

## 3. 본 파이프라인: `UnifiedUploadUseCase.execute()`

`src/application/unified_upload/use_case.py`

### ① 사전 검증 & 임베딩 모델 결정

- `collection_repo.collection_exists()` — 대상 Qdrant 컬렉션이 없으면 422.
- **임베딩 모델은 컬렉션 생성 이력에서 역추적한다** (`_resolve_embedding_model`):
  `activity_log`에서 해당 컬렉션의 `CREATE` 액션 로그를 찾아 `detail.embedding_model`을 읽고, `embedding_model` 레지스트리에서 해당 모델을 조회한다.
  → 컬렉션 생성 시 쓴 모델과 **항상 같은 모델로 임베딩**되도록 강제하는 장치다 (벡터 차원/의미 공간 불일치 방지). CREATE 로그가 없거나 모델 미등록이면 업로드 자체가 422로 실패한다.

### ② 파싱

- `parser.parse_bytes(file_bytes, filename, user_id)` → **페이지당 1개의 LangChain `Document`** 리스트.
- 파서는 `ParserFactory`(`src/infrastructure/parser/parser_factory.py`)에서 `settings.parser_type`으로 선택 — 기본값 `pymupdf`. 선택지: `pymupdf` / `pymupdf4llm`(마크다운) / `llamaparser`(클라우드, API 키 필요) / `docling` / `fallback`.
- `total_pages = len(parsed_docs)`가 응답의 페이지 수가 된다.

> ⚠️ "페이지당 Document" 산출이라는 점이 clause_aware 전략 설계에 영향을 준다 — 조(條)가 페이지 경계를 넘을 수 있어서 전략 내부가 페이지를 결합해 처리한다 (§3-③).

### ③ 청킹 — 전략 선택과 계층 구조

`_build_strategy()` → `ChunkingStrategyFactory.create_strategy()`

| 조건 | 전략 | 파라미터 |
|------|------|----------|
| `chunking_config is None` (일반 업로드, clause 미사용 KB) | **`parent_child`** (기본) | parent 2000 토큰 고정, child = Query 파라미터(기본 500/overlap 50) |
| KB `use_clause_chunking=true` | **`clause_aware`** | 프로파일의 경계 정규식 + 토큰/overlap 설정 |

(팩토리에는 `full_token`/`section_aware`/`semantic` 전략도 등록돼 있으나 업로드 주 경로에서는 위 2개만 사용된다.)

**parent_child** (`strategies/parent_child_strategy.py`):
텍스트를 parent(2000토큰) 단위로 자르고, 각 parent를 다시 child(500토큰, overlap 50)로 자른다. 구조 무관 순수 토큰 분할.

**clause_aware** (`strategies/clause_aware_strategy.py`):
① 조·항 의미 경계(프로파일 정규식, 예: `제N조`) 우선 분할 → ② 초과 시 토큰 분할 → ③ overlap. **조 = parent, 항/호 = child**로 매핑하고, 페이지들을 결합한 뒤 누적 offset으로 `page_start`/`page_end`를 산출한다(페이지 경계를 넘는 조 대응). 추가 메타로 `clause_title` 보유.

두 전략 모두 **동일한 메타데이터 계약**을 산출한다 — 이것이 하이브리드 검색 코드가 전략과 무관하게 동작하는 이유다:

```
chunk_type   : "parent" | "child"
chunk_id     : 청크 고유 id (uuid)
parent_id    : (child만) 소속 parent의 chunk_id
children_ids : (parent만) 자식 chunk_id 목록
chunk_index / total_chunks
```

> 검색은 child(작은 단위)로 정밀 매칭하고, 답변 컨텍스트는 parent(조 전체)로 확장하는 **small-to-big** 구조의 데이터 기반이다.

### ④ 공통 메타데이터 주입

```python
document_id = str(uuid.uuid4())          # 이 업로드의 문서 식별자 (모든 저장소 공통 키)
for chunk in chunks:
    chunk.metadata["document_id"]     = document_id
    chunk.metadata["user_id"]         = request.user_id
    chunk.metadata["collection_name"] = request.collection_name
    for key, value in request.extra_metadata.items():
        chunk.metadata.setdefault(key, value)   # kb_id/kb_name 등 — 고정키 우선(setdefault)
```

- `document_id`는 **여기서 최초 발급**되어 Qdrant payload, ES 문서, MySQL 행, 요약 잡까지 전부 관통하는 조인 키가 된다.
- `setdefault`인 이유: 청킹 전략이 이미 넣은 고정 키(chunk_id 등)를 extra_metadata가 덮어쓰지 못하게 하는 방어.

### ⑤ 병렬 저장 — Qdrant ∥ Elasticsearch

`asyncio.gather(..., return_exceptions=True)`로 **동시에** 저장하고, 한쪽이 실패해도 다른 쪽은 진행한다.

#### ⑤-a. Qdrant (`_store_to_qdrant`)

1. ①에서 결정한 모델로 `EmbeddingFactory`가 임베딩 클라이언트 생성.
2. **모든 청크(parent+child)의 본문을 일괄 임베딩** — `embed_documents(texts)`.
3. `QdrantVectorStore.add_documents()`:
   - point id = **랜덤 `uuid4()`** (id를 넘기지 않으므로) ← ⚠️ `chunk_id`와 다르다! (§5 ID 계약 참조)
   - payload = `{"content": 본문, **metadata}` — 메타데이터 값은 **전부 문자열로 캐스팅**되어 저장된다 (`str(v)`).
   - 컬렉션이 없으면 첫 문서의 벡터 차원으로 생성(`ensure_collection`).

**Qdrant point payload 최종 형태 (rawchunk):**

```json
{
  "content": "제5조(대출한도) ① ...",
  "chunk_type": "child",                  // 또는 "parent"
  "chunk_id": "<uuid>",
  "parent_id": "<parent chunk_id>",       // child만
  "chunk_index": "3", "total_chunks": "12",
  "document_id": "<문서 uuid>",
  "user_id": "1", "collection_name": "loan-docs",
  "kb_id": "<KB uuid>", "kb_name": "여신규정",   // KB 업로드만
  "clause_title": "제5조(대출한도)",             // clause_aware만
  "page_start": "3", "page_end": "4"            // clause_aware만
}
```

#### ⑤-b. Elasticsearch (`_store_to_es`)

청크마다:

1. **형태소 분석** (`morph_analyzer.analyze`) — 한국어 BM25 품질의 핵심.
   - `NNG`(일반명사)/`NNP`(고유명사)/`VV`(동사)/`VA`(형용사) 품사만 추출, 동사/형용사는 원형화(`+다`), 순서 보존 dedup → `morph_keywords` 리스트 + 공백 join한 `morph_text`.
2. ES 문서 구성 — **`_id` = `chunk_id`** (Qdrant point id와 달리 청크 id와 일치):

```json
{
  "_id": "<chunk_id>",
  "content": "원문", "morph_keywords": [...], "morph_text": "...",
  "chunk_id": "...", "chunk_type": "child", "chunk_index": 3, "total_chunks": 12,
  "parent_id": "...",                       // child만
  "document_id": "...", "user_id": "...", "collection_name": "...",
  "kb_id": "...", "kb_name": "..."          // KB 업로드만 (setdefault)
}
```

3. `es_repo.bulk_index()` — 인덱스는 단일 `settings.es_index`(기본 `documents`). 컬렉션/KB 구분은 인덱스 분리가 아니라 **필드 필터**로 한다.

> ⚠️ ES는 위처럼 **화이트리스트 방식으로 body를 직접 구성**한다. 새 메타 필드를 검색에 태우려면 (a) 이 코드에 필드 추가 + (b) ES 매핑 반영이 모두 필요하다. 반면 Qdrant는 metadata 전체를 복사하므로 자동 전파된다. (kb_id 도입 때 실제로 밟은 함정 — knowledge-base-scoping 참조)

### ⑥ MySQL `document_metadata` 저장

문서당 1행. **문서 목록/브라우징 화면의 진실 소스**다 (ES 집계가 아니라 — filename/created_at 보존, 페이지네이션 용이).

| 컬럼 | 값 |
|------|-----|
| `document_id` | ④에서 발급한 uuid (UNIQUE) |
| `collection_name` / `filename` / `user_id` | 요청 값 |
| `category` | `"uncategorized"` 고정 (현재 미분류) |
| `chunk_count` / `chunk_strategy` | 청킹 결과 (`parent_child` \| `clause_aware`) |
| `kb_id` | `extra_metadata`의 kb_id — **KB 업로드만 값 존재, 일반 업로드는 NULL** (V047) |

**best-effort**: 저장 실패해도 warning만 남기고 업로드는 계속된다 (벡터/ES가 본체, 메타는 부가).

### ⑦ 감사 로그 & ⑧ 상태 판정

- `activity_log`에 `ADD_DOCUMENT` 액션 기록 — document_id, 파일명, 페이지/청크 수, 임베딩 모델, 저장소별 성공 여부.
- 최종 status: 둘 다 성공 `completed` / 한쪽만 실패 `partial` / 둘 다 실패 `failed`. 응답에 저장소별 결과(`qdrant.stored_ids`, `es.indexed_count`, 각 error)가 그대로 실려 **부분 실패를 클라이언트가 식별**할 수 있다.

---

## 4. 후처리: 요약 계층 생성 (KB + opt-in 전용, 백그라운드)

업로드 응답과 **독립적으로** 진행되는 비동기 단계. 3계층 라우팅 검색(문서 요약 → 섹션 요약 → 원문 청크)의 데이터를 만든다.

### 킥오프 조건 (전부 충족해야 시작)

1. **KB 업로드 경로**일 것 (일반 업로드는 대상 아님)
2. 업로드 status가 `failed`가 아닐 것
3. KB의 청킹 프로파일에 **`summary_llm_model_id`가 지정**돼 있을 것 (V043, `NULL`=비활성 — **opt-in**)

> 조건 미충족이면 잡 자체가 생성되지 않는다. 이때 상태 조회 API(`GET .../documents/{id}/section-summary`)는 404를 반환하며 이는 **정상 동작**이다.

### 진행 흐름

```
SectionSummaryLauncher.launch()
  → section_summary_job 1행 생성 (MySQL, UNIQUE(document_id), 실행 스냅샷 보존)
  → asyncio.create_task 로 인프로세스 러너 시작
       │
       ├─ [섹션 요약] Qdrant에서 chunk_type=parent(조) 청크 열거 (SectionSource)
       │    섹션당 LLM 1회: 제목 + 3줄 요약 + 키워드 (structured output, 실패 시 JSON 프롬프트 폴백 1회)
       │    저장(SummaryWriter): "ES 먼저 → Qdrant 마지막(완료 마커)"
       │      · id = uuid5("section-summary:{section_ref}")   ← 결정적 → 재시도 멱등 upsert
       │      · section_ref = 원본 parent의 chunk_id           ← 원문 청크와의 연결 고리
       │      · Qdrant payload: chunk_type=section_summary, summary_text, summary_keywords, clause_title
       │      · ES: content=summary_text, morph 필드 대신 summary_* 전용 필드 (BM25 본문 검색에 구조적 미노출)
       │
       └─ [문서 요약 체이닝] 전 섹션 성공 시 DocumentSummaryStep 자동 실행
            섹션 요약 전량 집계 → cap(24,000자) 이내면 LLM 1회 / 초과 시 배치 map-reduce
            키워드는 섹션 키워드 빈도 상위 15 (LLM 0회, 결정론)
            저장: 문서당 1 point, id = uuid5("document-summary:{document_id}"), chunk_type=document_summary
       → 잡 completed (= 섹션 전량 + 문서 요약까지 성공)
```

- **재시도**(`POST .../section-summary/retry`): 완료 여부를 "Qdrant point 존재"로 판정해 **실패분만** 재처리 — 섹션별 상태 테이블 없이 결정적 ID + upsert로 멱등성을 얻는 구조.
- 요약 point는 원문과 **같은 컬렉션**에 들어가므로, 일반 검색이 요약을 집어오지 않도록 Qdrant 어댑터 `search_by_vector`에 `chunk_type` **must_not 가드**가 있다 (명시적으로 요약 타입을 필터하면 해제 — 라우팅 검색이 이 경로).

---

## 5. ID 계약 — 디버깅 시 가장 자주 헷갈리는 부분

| 계층 | Qdrant point id | ES `_id` | 비고 |
|------|-----------------|----------|------|
| **rawchunk** (parent/child) | 랜덤 `uuid4` (≠ chunk_id) | **= `chunk_id`** | payload/body 안의 `chunk_id` 필드는 양쪽 동일. 원문 본문 확장은 ES `ids` 쿼리(= chunk_id)로 수행 |
| **section_summary** | `uuid5("section-summary:{section_ref}")` | 동일 | point id = ES _id = 결정적 uuid5 **3자 일치**. `section_ref` = 원본 parent chunk_id |
| **document_summary** | `uuid5("document-summary:{document_id}")` | 동일 | 문서당 1개 |

- 조인 키 요약: **문서 단위** = `document_id`(모든 저장소 공통), **청크 단위** = `chunk_id`(Qdrant는 payload 필드로만, ES는 _id로도), **요약→원문** = `section_ref`.
- rawchunk의 Qdrant point id로 ES를 직조회하면 안 된다 (일치하지 않음). 반대로 요약 계층은 3자 일치라 RRF 병합 키로 그대로 쓴다.

---

## 6. 실패 모드와 복구

| 실패 지점 | 동작 | 복구 |
|-----------|------|------|
| 컬렉션 없음 / 임베딩 모델 미해결 | 422, 아무것도 저장 안 됨 | 컬렉션 생성(관리자) 또는 CREATE 로그/모델 등록 확인 |
| Qdrant 또는 ES 한쪽 실패 | `partial` — 성공한 쪽은 남음 | 응답의 error 확인 후 재업로드(현재 청크 단위 보정 없음) |
| document_metadata 저장 실패 | warning, 업로드는 성공 | 문서 목록에만 안 보임 — 행 수동 보정 가능 |
| 섹션 요약 LLM 실패 | 잡 failed (업로드와 무관) | retry API — 성공 섹션은 스킵, 실패분만 재처리 |
| 문서 요약 실패 | 잡 error에 `document summary failed:` prefix | retry 시 섹션 LLM 0회로 문서 요약만 재생성 (free win) |
| 서버 재시작으로 잡 고아화 | updated_at heartbeat 기반 stale 판정 | 상태 API가 is_stale 노출, retry로 재개 |

---

## 7. 관련 설정 / 마이그레이션 / 코드 맵

**설정** (`src/config.py` · `.env`):
`parser_type`(기본 pymupdf), `es_index`(기본 documents), 섹션 요약 동시성·입력 절단·stale 기준·섹션 상한 (`section_summary_*`)

**필수 마이그레이션** (누락 시 증상):
- V040 `knowledge_base` / V041·V043 `chunking_profile`(+summary 모델) / V044 `section_summary_job`
- **V047 `document_metadata.kb_id`** — 누락 시 KB 문서 목록 조회가 500 `Unknown column 'kb_id'` (2026-07-14 실발생 사례)
- ES: `kb_id`/`kb_name` keyword 매핑 1회 반영 필요 (summary_* 필드는 기동 시 put_mapping 자동)

**코드 맵**:

| 역할 | 파일 |
|------|------|
| 일반 업로드 라우터 | `src/api/routes/unified_upload_router.py` |
| KB 업로드 UseCase | `src/application/knowledge_base/upload_use_case.py` |
| KB 청킹 설정 해석 | `src/application/knowledge_base/chunking_resolver.py` |
| **본 파이프라인** | `src/application/unified_upload/use_case.py` |
| 파서 팩토리 | `src/infrastructure/parser/parser_factory.py` |
| 청킹 전략 | `src/infrastructure/chunking/strategies/{parent_child,clause_aware}_strategy.py` |
| Qdrant 저장 | `src/infrastructure/vector/qdrant_vectorstore.py` |
| ES 저장 | `src/infrastructure/elasticsearch/` (bulk_index) |
| 문서 메타 | `src/infrastructure/doc_browse/document_metadata_repository.py` |
| 섹션/문서 요약 | `src/application/section_summary/` + `src/infrastructure/section_summary/` |
| DI 조립 | `src/api/main.py` (`UnifiedUploadUseCase` 팩토리) |
