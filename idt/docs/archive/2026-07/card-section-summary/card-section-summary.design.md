# card-section-summary Design Document

> **Plan**: `docs/01-plan/features/card-section-summary.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-08
> **Status**: Draft
> **선행**: clause-aware-chunking (완료 — 조=parent 청킹, 프로파일 인프라)

---

## 1. 설계 요약

업로드 완료 후 백그라운드 잡이 카드 섹션(=clause-aware parent 청크)마다 LLM 1회 호출로 키워드+3줄 요약을 생성해 저장한다. 5개 블록:

1. **프로파일 확장**: `chunking_profile.summary_llm_model_id`(V043, NULL=요약 비활성) + 관리자 CRUD 반영
2. **잡 도메인**: `section_summary_job` 테이블(V044, 문서당 1행) + 상태 머신(pending→processing→completed|failed) + 재시도 정책
3. **요약 파이프라인**: SectionSource(parent 청크 scroll) → LLM(structured output+JSON 폴백) → 임베딩 → Qdrant(`chunk_type='section_summary'`, 결정적 ID upsert) + ES(전용 필드) 저장
4. **실행/API**: 인프로세스 `asyncio.create_task` 런처(독립 세션·짧은 트랜잭션) + KB 라우터에 상태 조회/재시도 엔드포인트 additive
5. **검색 격리**: Qdrant 어댑터 단일 초크포인트 must_not 가드 + ES 전용 필드 저장(BM25 미노출) + doc_browse 제외 필터

### 코드 확인으로 확정된 사실 (2026-07-08)

| 확인 항목 | 결과 | 영향 |
|-----------|------|------|
| parent 청크 메타 | `clause_title`, `page_start/end`, `boundary`, `chunk_id`, `children_ids` (`clause_aware_strategy.py:144-152`) | 섹션 카드 재료 완비 — SectionSource가 그대로 사용 (D1) |
| Qdrant point id | 업로드 시 `VectorDocument(id=None)` → `add_documents`가 uuid4 생성 (`qdrant_vectorstore.py:57`). **id 지정 시 upsert 동작** (`:65 client.upsert`) | 요약 point는 결정적 id 지정으로 멱등 upsert (D5) |
| 하이브리드 검색 격리 | BM25·벡터 **양쪽 모두 chunk_type 필터 없음** (`hybrid_search/use_case.py:92-109, 136-150`) — Plan의 "Qdrant는 child 필터로 자동 격리" 가정은 `parent_child_retriever` 경로에만 해당 | Qdrant는 어댑터 레벨 must_not 가드 필요 (D8), ES는 전용 필드로 회피 (D7) |
| ES 저장 | `_store_to_es` 고정 화이트리스트, doc `_id=chunk_id` (`unified_upload/use_case.py:280-296`). 인덱스명 `settings.es_index`(`config.py:49`), 시작 시 `_ensure_es_index`(`main.py:3039`) | 요약 ES 문서는 별도 writer가 색인, `_id`=요약 id 멱등 (D5, D7) |
| 문서 삭제 | Qdrant/ES 모두 `document_id` 단일 조건 삭제 (`delete_document_use_case.py:228-266`) | 요약 payload/필드에 `document_id` 포함 → 동반 삭제 자동 (D6) |
| doc_browse | `document_id` 단독 scroll (`get_chunks_use_case.py:99-116`) → 요약 청크가 문서 열람에 혼입됨 | post-filter로 제외 (D9) |
| chunk_type 게이트 | `VALID_CHUNK_TYPES` 집합 2곳(`chunking/value_objects.py:6`, `retriever/.../metadata_filter.py:13`), Literal 제약 pydantic 필드 없음(전부 str), `_detect_strategy` 분기(`get_chunks_use_case.py:120-127`) | 집합 2곳에 `section_summary` 추가 + `_detect_strategy`는 parent 존재로 판정 유지(수정 불요) |
| LLM 인프라 | `LLMFactory.create(llm_model, temperature)` (`llm_factory.py:16-28`), vLLM=openai+base_url(`:33-46`). `LlmModelRepository.find_by_id` 존재(`llm_model_repository.py:33`), id는 `str` | 프로파일 검증·잡 실행 모두 기존 인프라 재사용 (D2, D16) |
| structured output 선례 | `with_structured_output(Pydantic)` 20개 파일(`search_pipeline.py:164` 등) + 수동 JSON 파싱·1회 재시도 폴백(`slot_extractor.py:116-148`). provider별 분기 없음 | 두 패턴 결합: structured 시도 → JSON 폴백 (D10) |
| 임베딩 | `EmbeddingFactory.create_from_string(provider, model)` → `embed_documents` 배치 (`embedding_factory.py:68-91`, 업로드 사용 `use_case.py:243-248`) | 잡에 provider/model 스냅샷 후 동일 팩토리 사용 (D13) |
| 백그라운드 선례 | `asyncio.create_task` 사용처 전무. 표준 = `session_factory` 주입 + 독립 짧은 세션(`trigger_due_schedules_use_case.py`, DB-001) | create_task 신규 도입하되 세션 규칙은 기존 패턴 준수 (D11) |
| KB 업로드 삽입 지점 | `upload_use_case.py:84` `unified_upload.execute` 반환 직후(document_id 확보) | 런처 호출 지점 (D14) |
| 마이그레이션 | 최신 V042 | V043, V044 |

---

## 2. 설계 결정 (Decisions)

| ID | 결정 | 근거 |
|----|------|------|
| D1 | **카드 섹션 = parent 청크.** `SectionSource` 인터페이스(domain)로 추상화: `list_sections(collection_name, document_id, request_id) -> list[SectionCard]`, `SectionCard = {section_ref(=parent chunk_id), title(clause_title), text, chunk_index}`. v1 구현 `QdrantSectionSource`: `document_id + chunk_type='parent'` 복합 필터 scroll, `chunk_index` 정렬 | 사용자 결정(조 단위, 상위 경계 교체 용이). 후속에 장·절 소스로 교체 시 이 구현만 갈아끼움 — 파이프라인·저장 계약 불변 |
| D2 | 프로파일 additive 컬럼 1개: `summary_llm_model_id VARCHAR(36) NULL`. **FK 제약 없음(soft reference)** — 검증은 UseCase(`find_by_id` + `is_active`). NULL=요약 비활성(opt-in). 키워드 개수 등 파라미터 컬럼은 두지 않음 | llm_model은 삭제가 아닌 deactivate 운영이라 FK 무결성 이득이 적고, cross-table 콜레이션 리스크(errno 3780) 회피. 파라미터는 상수/설정으로 충분(YAGNI) |
| D3 | 잡 테이블 `section_summary_job`(V044): **문서당 1행**(`UNIQUE(document_id)`), 진행 카운트(total/done/failed) + 실행 스냅샷(`llm_model_id`, `embedding_provider`, `embedding_model`, `collection_name`, `chunking_profile_id`, `kb_id`). **섹션별 상태 테이블 없음** — 섹션 완료 판정은 Qdrant 요약 point 존재로 | 과도한 정규화 회피. 스냅샷으로 실행 중 프로파일 변경에 영향받지 않음(Plan §4-5). 카운트만으로 진행률 UX 충족 |
| D4 | 상태 머신: `pending → processing → completed \| failed`. **재시도 가능 조건**(Policy 판정): `failed`, 또는 `pending`/`processing`이면서 stale(`updated_at + section_summary_stale_seconds` 경과 — 서버 재시작 고아 복구). 조회 응답에 `is_stale` 계산 노출(자동 상태 변경 없음 — 조회는 read-only) | Plan FR-06/07. stale 자동 정리는 cron 없이는 불완전 — 판정만 노출하고 복구는 명시적 재시도로 |
| D5 | **결정적 ID로 멱등성 확보**: `summary_id = uuid5(NAMESPACE_URL, f"section-summary:{section_ref}")`. Qdrant point id = summary_id(`VectorDocument(id=DocumentId(summary_id))` → 기존 upsert 경로), ES `_id` = summary_id(재색인=덮어쓰기) | 재시도 중복 저장 원천 차단(Plan 리스크). 기존 `add_documents`/`index` 무수정 재사용 |
| D6 | 섹션 처리 순서: **ES 먼저 → Qdrant 마지막(완료 마커)**. 재시도 시 Qdrant에서 기존 `section_summary` point의 `section_ref` 집합을 scroll → 미완료 섹션만 LLM 재처리 | Qdrant 존재=완료(D3)와 일관. ES가 성공하고 Qdrant가 실패하면 재시도 시 ES는 덮어쓰기(멱등)라 안전. 요약 payload에 `document_id` 포함 → 문서 삭제 시 동반 삭제 자동 |
| D7 | **ES 격리 = 전용 필드**: 요약 ES 문서는 `content`/`morph_text`/`morph_keywords`를 **채우지 않는다**. 신규 매핑 필드: `summary_text`(text, `korean_nori`), `summary_keywords`(keyword), `section_ref`(keyword), `clause_title`(text). 공통 필드(`document_id`, `user_id`, `collection_name`, `kb_id/kb_name`, `chunk_id`, `chunk_type='section_summary'`)는 유지. `DOCUMENTS_INDEX_MAPPINGS`에 필드 추가 + 시작 시 기존 인덱스에 **additive `put_mapping`**(`_ensure_es_index` 확장) | BM25 `multi_match(content^1.5, morph_text)`가 구조적으로 요약을 못 봄 — 기존 검색 쿼리 무수정(NFR-01). 후속 키워드 검색은 `summary_keywords`/`summary_text`를 명시 조회 |
| D8 | **Qdrant 격리 = 어댑터 단일 초크포인트 가드**: `QdrantVectorStore.search_by_vector`가 필터를 조립할 때, 호출자가 명시적으로 `chunk_type='section_summary'`를 요구하지 않는 한 `must_not[chunk_type=section_summary]`를 추가 | 벡터 검색 경로가 다수(hybrid, collection_search, retrieval, agent search_pipeline)라 경로별 수정은 누락 위험. 기존 적재 데이터에 section_summary가 없으므로 **동작 보존**(기존 결과 불변). 후속 라우팅 검색은 명시 필터로 가드 통과. `scroll`/`delete_by_metadata`에는 미적용(삭제 동반·조회 명시 목적) |
| D9 | doc_browse `get_chunks`는 `chunk_type='section_summary'` point를 **post-filter로 제외**. `_detect_strategy`는 parent/child 존재로 판정하므로 무수정 | 문서 청크 열람 UI에 요약 혼입 방지(동작 보존 수정). scroll 쿼리 자체는 무수정 — 파이썬 레벨 제외가 최소 변경 |
| D10 | LLM 호출: **1섹션 1호출**, `llm.with_structured_output(SectionSummaryOutput)` 시도 → 예외 시 **JSON 지시 프롬프트 + 수동 파싱 1회 재시도**(slot_extractor 선례) → 최종 실패는 해당 섹션만 `failed_sections`로 격리. `SectionSummaryOutput = {keywords: list[str](1~10개), summary_lines: list[str](정확히 3줄 지시)}`. 입력 = `clause_title` + 섹션 본문(`section_summary_input_char_cap` 절단). temperature 0.0 | vLLM 등 function calling 미지원 모델 폴백(Plan 리스크). 방어 규칙: keywords 최대 10개 절단, summary 라인당 300자 절단(domain Policy, NFR-08) |
| D11 | 실행 구조: `SectionSummaryLauncher`(**싱글턴**, `session_factory` 주입). `launch(spec)` = ① 독립 짧은 세션으로 잡 INSERT(pending) ② `asyncio.create_task(runner.run(job_id))` ③ 잡 정보 반환. **KB 업로드 UseCase는 launcher 호출만** — 자기 요청 세션과 분리(한 UseCase 내 이중 세션 금지 규칙 준수). 러너(`SummarizeSectionsUseCase`)의 DB 접근은 회차별 독립 세션·짧은 트랜잭션(agent_schedule 선례), **LLM/임베딩 호출은 트랜잭션 밖**. launch 실패는 warning 로그 후 무시(업로드 결과 무영향, FR-09) | `asyncio.create_task` 선례는 없으나(코드 확인) 사용자 결정(인프로세스+재시도 API). 세션 규칙(DB-001)은 기존 표준 그대로. task 참조는 launcher가 보관(GC 방지) |
| D12 | 동시성: `asyncio.Semaphore(settings.section_summary_concurrency)`로 LLM 호출 제한. 진행 카운트는 섹션 완료마다 `asyncio.Lock` 하에 UPDATE — `updated_at` 갱신이 heartbeat(=stale 판정 기준) 역할 겸함 | 폭주 방지(NFR-07) + 실시간 진행률(FR-06) + stale 판정 데이터 확보를 한 메커니즘으로 |
| D13 | 임베딩: 잡 스냅샷의 `embedding_provider/model`로 `EmbeddingFactory.create_from_string` → 임베딩 입력 = `f"{clause_title}\n{summary_text}"` | 원 업로드와 동일 모델 → 컬렉션 차원 일치 보장. 제목+요약 결합이 라우팅 대표성에 유리 |
| D14 | 킥오프 조건·배선: `ChunkingSettingsResolver`에 additive 메서드 `resolve_summary_spec(kb) -> SectionSummarySpec \| None`(프로파일의 `summary_llm_model_id` 존재 시 스펙 반환; 기존 `resolve()` 무수정). KB 업로드 UseCase는 업로드 성공(`status != "failed"`) && spec 존재 시 `launcher.launch(...)` 호출 | resolver가 이미 프로파일 로드 책임 보유 — 요약 스펙 해석도 동일 책임. 기존 시그니처 불변(additive) |
| D15 | API(additive, `knowledge_base_router.py`): `GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/section-summary`(can_read, 잡 없으면 404) / `POST .../section-summary/retry`(can_write, 재시도 불가 상태면 409, 성공 시 202). KB 업로드 응답에 optional `section_summary: {job_id, status} \| null` 추가 | 잡의 수명·권한이 KB에 종속. 프론트 후속 작업이 이 두 엔드포인트만 붙이면 됨 |
| D16 | 검증: 프로파일 저장/수정 시 `summary_llm_model_id` 지정이면 `LlmModelRepository.find_by_id`로 존재+`is_active` 확인, 위반 시 422. 잡 실행 시점에 모델 부재/비활성이면 잡 `failed`(명확한 error 메시지) — 업로드는 이미 성공 상태 유지 | FR-01. late-binding 실패는 상태로 표면화(에러 삼킴 금지) |
| D17 | 신규 설정(`config.py`, 전부 기본값 보유): `section_summary_concurrency=3`, `section_summary_input_char_cap=12000`, `section_summary_stale_seconds=600`, `section_summary_max_sections=500`(초과 시 잡 failed + error 메시지 — 조용한 절단 금지) | config 하드코딩 금지(NFR-04). parent≤2000토큰이라 12000자 cap은 여유, doc-extractor 20000자 절단 선례 |
| D18 | `VALID_CHUNK_TYPES` 2곳(`chunking/value_objects.py:6`, `metadata_filter.py:13`)에 `"section_summary"` 추가. `ChunkMetadata` VO는 요약 저장 경로에서 미사용(writer가 `VectorDocument` 직접 구성) — 집합 확장은 후속 라우팅 검색의 `MetadataFilter(chunk_type="section_summary")` 대비 | 런타임 게이트 2곳이 실질 검증 지점(코드 확인 — Literal 제약 없음) |

---

## 3. 파일 구조 (신규/수정)

```
idt/
├── db/migration/
│   ├── V043__alter_chunking_profile_add_summary_model.sql    [신규]
│   └── V044__create_section_summary_job.sql                  [신규]
├── src/
│   ├── domain/
│   │   ├── section_summary/
│   │   │   ├── __init__.py                                   [신규]
│   │   │   ├── entities.py    # SectionSummaryJob, SectionCard, SectionSummarySpec, SectionSummaryResult [신규]
│   │   │   ├── interfaces.py  # SectionSummaryJobRepositoryInterface, SectionSourceInterface, SectionSummarizerInterface, SummaryWriterInterface [신규]
│   │   │   └── policy.py      # SectionSummaryJobPolicy (상태 전이·재시도·stale·출력 방어 절단) [신규]
│   │   ├── chunking/value_objects.py                         [수정: VALID_CHUNK_TYPES += section_summary]
│   │   ├── retriever/value_objects/metadata_filter.py        [수정: 동일]
│   │   └── chunking_profile/entities.py, policy.py           [수정: summary_llm_model_id additive]
│   ├── application/
│   │   ├── section_summary/
│   │   │   ├── __init__.py                                   [신규]
│   │   │   ├── launcher.py    # SectionSummaryLauncher (잡 생성 + create_task) [신규]
│   │   │   ├── use_case.py    # SummarizeSectionsUseCase (러너: 섹션 순회·격리·카운트) [신규]
│   │   │   └── schemas.py     # JobStatusResult 등 [신규]
│   │   ├── chunking_profile/use_case.py                      [수정: summary 모델 검증(D16)]
│   │   ├── knowledge_base/chunking_resolver.py               [수정: resolve_summary_spec additive (D14)]
│   │   ├── knowledge_base/upload_use_case.py                 [수정: launcher 호출 (D14)]
│   │   └── doc_browse/get_chunks_use_case.py                 [수정: section_summary 제외 (D9)]
│   ├── infrastructure/
│   │   ├── persistence/models/section_summary_job.py         [신규]
│   │   ├── persistence/models/chunking_profile.py            [수정: 컬럼 additive]
│   │   ├── section_summary/
│   │   │   ├── job_repository.py                             [신규]
│   │   │   ├── qdrant_section_source.py  # parent scroll (D1) + 완료 section_ref 조회 (D6) [신규]
│   │   │   ├── llm_summarizer.py         # structured + JSON 폴백 (D10) [신규]
│   │   │   └── summary_writer.py         # ES→Qdrant 저장, 결정적 id (D5, D6, D7) [신규]
│   │   ├── chunking_profile/repository.py                    [수정: 매핑 additive]
│   │   ├── vector/qdrant_vectorstore.py                      [수정: search_by_vector must_not 가드 (D8)]
│   │   └── elasticsearch/es_index_mappings.py                [수정: 요약 필드 4개 (D7)]
│   ├── api/
│   │   ├── routes/knowledge_base_router.py                   [수정: 상태/재시도 엔드포인트 + 업로드 응답 필드 (D15)]
│   │   ├── routes/admin_chunking_router.py                   [수정: Body/Response summary_llm_model_id]
│   │   └── main.py                                           [수정: launcher 배선 + put_mapping 확장]
│   └── config.py                                             [수정: D17 설정 4개]
└── tests/
    ├── domain/section_summary/test_policy.py                 [신규]
    ├── application/section_summary/test_launcher.py          [신규]
    ├── application/section_summary/test_use_case.py          [신규] (멱등 재시도·부분 실패·cap 포함)
    ├── application/knowledge_base/test_upload_summary_kickoff.py [신규] (킥오프 조건·업로드 무영향·회귀 가드)
    ├── infrastructure/section_summary/test_llm_summarizer.py [신규] (structured/폴백/파싱 실패)
    ├── infrastructure/section_summary/test_summary_writer.py [신규] (결정적 id·ES 필드 격리)
    ├── infrastructure/vector/test_qdrant_search_guard.py     [신규] (D8 가드·명시 필터 통과)
    ├── application/chunking_profile/test_use_case.py         [수정: summary 모델 검증 케이스]
    └── api/test_knowledge_base_router.py                     [수정: 상태 404/200·retry 403/409/202]
```

---

## 4. DB 스키마

### 4.1 `V043__alter_chunking_profile_add_summary_model.sql`

```sql
-- card-section-summary D2: 섹션 요약용 LLM 모델 소프트 참조 (NULL = 요약 비활성).
-- FK 제약 없음 — llm_model은 deactivate 운영, 무결성은 UseCase 검증(422).
ALTER TABLE chunking_profile
    ADD COLUMN summary_llm_model_id VARCHAR(36) NULL
        COMMENT '섹션 요약 LLM(llm_model.id 소프트 참조), NULL=요약 비활성';
```

### 4.2 `V044__create_section_summary_job.sql`

```sql
-- card-section-summary D3/D4: 섹션 요약 백그라운드 잡 (문서당 1행).
-- 섹션별 상태는 저장하지 않음 — 완료 판정은 Qdrant section_summary point 존재(D6).
-- ⚠️ FK 콜레이션 주의(errno 3780): CHARSET/COLLATE 명시 금지, ENGINE=InnoDB만 (V037 선례).
CREATE TABLE section_summary_job (
    id                  VARCHAR(36)  NOT NULL PRIMARY KEY,
    document_id         VARCHAR(36)  NOT NULL,
    kb_id               VARCHAR(36)  NOT NULL,
    collection_name     VARCHAR(255) NOT NULL,
    chunking_profile_id VARCHAR(36)  NOT NULL COMMENT '생성 시점 스냅샷',
    llm_model_id        VARCHAR(36)  NOT NULL COMMENT '생성 시점 스냅샷',
    embedding_provider  VARCHAR(50)  NOT NULL COMMENT '원 업로드와 동일 임베딩(차원 일치)',
    embedding_model     VARCHAR(100) NOT NULL,
    status              VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT 'pending|processing|completed|failed',
    total_sections      INT          NULL COMMENT '러너 시작 시 확정',
    done_sections       INT          NOT NULL DEFAULT 0,
    failed_sections     INT          NOT NULL DEFAULT 0,
    error               VARCHAR(1000) NULL,
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_section_summary_job_document (document_id),
    INDEX idx_section_summary_job_kb (kb_id),
    INDEX idx_section_summary_job_status (status)
) ENGINE=InnoDB;
```

---

## 5. 저장 데이터 계약

### 5.1 Qdrant 요약 point (동일 컬렉션)

```
id      = uuid5(NAMESPACE_URL, f"section-summary:{section_ref}")   # 멱등 (D5)
vector  = embed(f"{clause_title}\n{summary_text}")                 # 원 업로드와 동일 모델 (D13)
payload = {
  "content": <3줄 요약 텍스트>,               # point 본문 관례(_point_to_document 호환)
  "chunk_type": "section_summary",
  "chunk_id": <summary_id>,
  "section_ref": <원 parent chunk_id>,        # → rawchunk 확장 연결고리 (후속 라우팅)
  "document_id": <document_id>,               # → 문서 삭제 동반 (D6)
  "collection_name": ..., "user_id": ...,     # 기존 청크 payload 공통 필드와 정합
  "kb_id": ..., "kb_name": ...,
  "clause_title": <조 제목>,
  "chunk_index": <원 parent chunk_index>,
  "keywords": <list[str]>,                    # LLM 키워드 (배열 유지 — MatchAny 필터 대비)
  "summary": <3줄 요약 텍스트("\n" join)>,
  "filename": ...,
}
```

### 5.2 ES 요약 문서 (동일 인덱스, `_id = summary_id`)

```
{
  "document_id", "user_id", "collection_name", "kb_id", "kb_name", "filename",
  "chunk_id": <summary_id>, "chunk_type": "section_summary",
  "section_ref": <parent chunk_id>,
  "clause_title": <조 제목>,
  "summary_text": <3줄 요약>,          # 신규 필드 (nori_analyzer)
  "summary_keywords": [<키워드>...]     # 신규 필드 (keyword)
  # content / morph_text / morph_keywords 없음 → 기존 BM25 미노출 (D7)
}
```

### 5.3 ES 매핑 추가 (`es_index_mappings.py` + startup put_mapping)

```python
"summary_text":     {"type": "text", "analyzer": "nori_analyzer"},
"summary_keywords": {"type": "keyword"},
"section_ref":      {"type": "keyword"},
"clause_title":     {"type": "text", "fields": {"raw": {"type": "keyword"}}},
```

`main.py`의 `_ensure_es_index`를 확장: 인덱스 존재 시에도 신규 필드를 `put_mapping`으로 additive 반영(멱등 — 동일 매핑 재적용은 no-op).

---

## 6. 파이프라인 흐름

### 6.1 킥오프 (KB 업로드 내, D11/D14)

```
KnowledgeBaseUploadUseCase.execute()
  ├─ (기존) resolver.resolve(kb) → chunking_config
  ├─ (기존) unified_upload.execute() → result
  ├─ (신규) result.status != "failed"
  │     and spec := resolver.resolve_summary_spec(kb)   # 프로파일 summary_llm_model_id 존재 시
  │     → launch_info = launcher.launch(spec + result.document_id + 업로드 임베딩 provider/model)
  │        (launch 내부 예외는 warning 로그 후 None — 업로드 결과 무영향, FR-09)
  └─ 응답에 section_summary={job_id, status:"pending"} | null
```

### 6.2 러너 (`SummarizeSectionsUseCase.run(job_id)`, D6/D10/D12)

```
1. [세션A] 잡 로드 + pending/재시도 검증 → processing 전이
2. LLM 모델 로드(find_by_id) — 부재/비활성 → [세션] failed + error, 종료 (D16)
3. sections = section_source.list_sections(collection, document_id)      # parent scroll, chunk_index 정렬
   len > max_sections → failed + error, 종료 (D17)
4. done_refs = section_source.list_done_refs(collection, document_id)    # 기존 summary point의 section_ref (재시도 멱등)
5. [세션B] total_sections 확정 UPDATE
6. asyncio.gather( per-section, Semaphore(concurrency) ):
     a. LLM structured output → 실패 시 JSON 폴백 1회 (D10)
     b. Policy 방어 절단(키워드≤10, 라인≤300자, 3줄 보정)
     c. embed(clause_title + summary)
     d. writer.write(ES doc → Qdrant point)                              # Qdrant=완료 마커 (D6)
     e. [Lock+단기 세션] done/failed 카운트 UPDATE                        # heartbeat 겸용 (D12)
   — 섹션 예외는 격리: failed_sections 증가, 잡 계속 (FR-09)
7. [세션Z] 최종 상태: failed_sections==0 → completed / else → failed(카운트 유지)
   모든 세션은 독립·짧은 트랜잭션, LLM/임베딩 호출은 트랜잭션 밖 (D11)
```

### 6.3 재시도 (`POST .../retry`, D4)

```
1. KB 조회 + policy.can_write 검증 (403)
2. 잡 로드 (404) → Policy.can_retry(job, now, stale_seconds)?  아니면 409
3. done/failed 카운트 리셋 없이 processing 재전이 → launcher가 create_task 재킥오프 (202)
   러너 4단계의 done_refs 조회가 완료분 스킵을 보장 (멱등)
```

---

## 7. API 계약

### 7.1 프로파일 (admin, 기존 라우터 확장)

- `ChunkingProfileBody`/`ProfileResponse`에 `summary_llm_model_id: str | None = None` 추가
- 지정 시 존재+활성 검증 실패 → 422 `"summary_llm_model_id: 존재하지 않거나 비활성인 모델"`

### 7.2 상태 조회

```
GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/section-summary
→ 200 {
  "job_id": str, "document_id": str, "status": "pending|processing|completed|failed",
  "total_sections": int|null, "done_sections": int, "failed_sections": int,
  "is_stale": bool,            # processing/pending && updated_at 경과 (D4)
  "error": str|null, "created_at": iso, "updated_at": iso
}
→ 404 잡 없음(요약 비활성 업로드 포함) / 403 KB 읽기 권한 없음
```

### 7.3 재시도

```
POST /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/section-summary/retry
→ 202 { "job_id": str, "status": "processing" }
→ 409 재시도 불가 상태(completed, 진행 중이며 stale 아님) / 403 쓰기 권한 없음 / 404 잡 없음
```

### 7.4 KB 업로드 응답 (additive)

```
기존 응답 + "section_summary": { "job_id": str, "status": "pending" } | null
```

> `/api-contract-sync`: 프론트 타입 동기화는 후속 PDCA(section-summary-frontend)에서 일괄 수행.

---

## 8. 프롬프트 & 출력 스키마 (D10)

```python
class SectionSummaryOutput(BaseModel):
    keywords: list[str]       # 3~8개 권장, 최대 10개(초과 절단)
    summary_lines: list[str]  # 정확히 3줄, 각 1문장

SYSTEM = (
    "당신은 금융/정책 문서 색인 전문가다. 주어진 조문 섹션을 읽고 "
    "(1) 검색 키워드 3~8개(명사구, 조문에 실제 등장하거나 직접 지칭하는 개념), "
    "(2) 섹션의 핵심 내용을 3줄로 요약하라(각 줄 1문장, 존댓말 금지, 사실만). "
    "섹션에 없는 내용을 추가하지 마라."
)
USER = f"[섹션 제목]\n{clause_title}\n\n[섹션 본문]\n{text[:input_char_cap]}"
```

- 1차: `llm.with_structured_output(SectionSummaryOutput).ainvoke(...)`
- 폴백: 동일 내용 + "반드시 JSON만 출력: {\"keywords\": [...], \"summary_lines\": [...]}" → 코드펜스 제거 후 `json.loads` (slot_extractor `_CODE_FENCE_RE` 선례), 1회 재시도
- 방어(Policy): keywords 공백/중복 제거·10개 절단, summary_lines 3줄 미만이면 있는 줄 사용(1줄 이상이면 성공), 라인당 300자 절단

---

## 9. 테스트 계획 (TDD — 구현 전 작성)

| 파일 | 핵심 케이스 |
|------|------------|
| `test_policy.py` | 상태 전이 허용/거부, can_retry(failed○/completed×/processing+stale○/processing+fresh×), 출력 절단(키워드 10개·라인 300자·3줄 보정) |
| `test_launcher.py` | 잡 INSERT+task 생성, document_id 중복(UNIQUE) 처리, launch 예외가 호출자에 미전파 |
| `test_use_case.py` (러너) | 정상 완료(카운트·completed), 일부 섹션 실패 격리(failed+카운트), 재시도 시 done_refs 스킵(LLM 미호출 검증), max_sections 초과 failed, 모델 비활성 failed, 세션 단기 사용 |
| `test_upload_summary_kickoff.py` | spec 존재+업로드 성공 → launch 호출 / 요약 비활성 프로파일 → 미호출·기존 동작 불변(회귀 가드) / 업로드 failed → 미호출 / launch 예외 → 업로드 응답 정상 |
| `test_llm_summarizer.py` | structured 성공, structured 예외→JSON 폴백 성공, 코드펜스 제거, 최종 파싱 실패 예외 |
| `test_summary_writer.py` | 결정적 id(동일 입력=동일 id), ES 문서에 content/morph_* 부재, Qdrant payload 계약(§5.1), ES→Qdrant 순서 |
| `test_qdrant_search_guard.py` | 기본 검색에 must_not 추가, 기존 필터 보존, `chunk_type=section_summary` 명시 시 가드 미적용 |
| `test_use_case.py` (프로파일, 수정) | summary_llm_model_id 부재/비활성 422, 정상 저장·응답 노출 |
| `test_knowledge_base_router.py` (수정) | GET 200/404/403, retry 202/409/403, 업로드 응답 section_summary 필드 |
| 기존 스위트 | 회귀 0건 (chunk_type 집합 확장·가드 추가 후) |

---

## 10. 구현 순서 (Do 체크리스트)

1. **마이그레이션 + 모델**: V043/V044, `chunking_profile.py` 컬럼, `section_summary_job.py` 모델
2. **domain/section_summary**: 엔티티·인터페이스·Policy (+ 테스트 선작성)
3. **chunk_type 확장**: `VALID_CHUNK_TYPES` 2곳 + ES 매핑 필드 + `_ensure_es_index` put_mapping
4. **격리 가드**: `qdrant_vectorstore.search_by_vector` must_not (+ 가드 테스트), doc_browse post-filter
5. **infrastructure/section_summary**: job_repository → qdrant_section_source → llm_summarizer → summary_writer (각 테스트 선작성)
6. **application**: SummarizeSectionsUseCase(러너) → SectionSummaryLauncher (+ 테스트)
7. **프로파일 확장**: 엔티티/정책/UseCase 검증/admin 라우터 (+ 테스트)
8. **KB 연동**: resolver `resolve_summary_spec` → upload_use_case 킥오프 → KB 라우터 엔드포인트·응답 필드 (+ 테스트)
9. **배선**: main.py launcher 싱글턴(session_factory, embedding_factory, llm factory/repo, vector store, es repo) + config 설정 4개
10. **검증**: 전체 테스트 + `/verify-architecture` + `/verify-tdd` + `/verify-logging` + 회귀 가드 확인
