# kb-content-browser Design — KB 저장 내용(3계층) 드릴다운 뷰어

> Feature: KB 상세에서 문서 요약 → 섹션 요약 → parent/child 청크를 ES/Qdrant 저장소별로 나눠 확인
> Created: 2026-07-14
> Status: Design
> Plan: `docs/01-plan/features/kb-content-browser.plan.md`
> Related: `kb-management-ui`(archived), `card-section-summary`(archived), `document-summary-routing`(archived), `collection-document-browser`(완료 선례)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | KB에 저장된 3계층 데이터(청크·섹션 요약·문서 요약)를 확인할 API/화면이 없고, 데이터는 ES와 Qdrant에 이중 저장되어 어느 쪽이 어떻게 들어갔는지 검증 불가. |
| **Solution** | KB 라우터 하위 조회 API 3종 신규, 모든 API에 `source=qdrant\|es` 파라미터 — 사용자가 저장소를 토글로 나눠서 확인. 청크 키워드 검색도 선택된 저장소에서 실행(ES=nori match, Qdrant=scroll 후 서버측 부분일치). |
| **Function/UX Effect** | KB 상세 문서 행 클릭 → 3탭(문서 요약/섹션 요약/청크) 패널. 저장소 토글, 요약 잡 진행률·재시도, payload 메타 토글 제공. |
| **Core Value** | ES 우선-Qdrant 마지막 이중 쓰기 구조의 저장 정합성을 눈으로 교차 검증하는 디버깅 도구. |

---

## 1. 설계 개요

Plan에서 이월된 결정 2건에 대한 사용자 확정:

1. **요약/청크 조회 소스** → 한쪽을 고르지 않고 **ES와 Qdrant를 나눠서 볼 수 있게** (저장소 토글)
2. **청크 키워드 검색** → **사용자가 선택한 저장소 기준으로 실행**

이에 따라 조회 API 3종 모두 `source` 쿼리 파라미터를 받고, 프론트 패널에 저장소 토글(segmented control)을 둔다.

---

## 2. As-Is 조사 근거 (2026-07-14 코드 확인)

| # | 확인 사항 | 근거 |
|---|-----------|------|
| 1 | 청크·섹션요약·문서요약 3계층 모두 ES 단일 전역 인덱스 `settings.es_index`("documents")에 색인 | `src/application/unified_upload/use_case.py:272-301`, `summary_writer.py`, `document_summary_step.py` (KB 업로드는 `UnifiedUploadUseCase` 경로 — `docs_{collection}` 인덱스는 advanced pipeline 전용으로 KB와 무관) |
| 2 | 3계층 모두 ES에 `kb_id`(keyword) 색인됨 → term 필터 가능 | `es_index_mappings.py:45`, `unified_upload/use_case.py:296-297`, `summary_writer.py:74`, `document_summary_step.py:325` |
| 3 | Qdrant는 `kb.collection_name` 컬렉션에 저장, payload에 `kb_id`/`document_id`/`chunk_type` 포함 | `unified_upload/use_case.py:92-98, 242-270` |
| 4 | **Qdrant content 풀텍스트 인덱스 없음** — `create_payload_index`/`MatchText` 호출 코드 전무 | `qdrant_vectorstore.py:36-48`, `qdrant_client.py:57-79` |
| 5 | 섹션 요약 ES body에는 `summary_text`(content/morph_text 없음 — BM25 격리 D7), Qdrant payload에는 `content`=summary_text | `summary_writer.py:61-103` |
| 6 | 문서 요약도 동일 구조 + `section_count`, `section_ref`/`clause_title` 없음 | `document_summary_step.py:314-351` |
| 7 | Qdrant scroll 선례: `client.scroll` 직접 호출 (`Filter(must=[FieldCondition(...)])`) | `get_chunks_use_case.py:107-124`, `qdrant_section_source.py:107-126` |
| 8 | `QdrantVectorStore.search_by_vector`는 요약 청크 must_not 가드 — **scroll은 가드 없음** → browse는 scroll 사용 | `qdrant_vectorstore.py:166-192` |
| 9 | KB 라우터 DI: 플레이스홀더 함수 + `app.dependency_overrides` 바인딩, 응답 스키마는 라우터 파일 인라인 | `knowledge_base_router.py:32-45`, `main.py:3725, 3795-3854` |
| 10 | KB 권한/존재 검증 선례: `ListKbDocumentsUseCase` → `KnowledgeBaseUseCase.get()` 위임 (`ValueError`→404, `PermissionError`→403, 라우터 `_raise_http`) | `list_documents_use_case.py:50-58`, `knowledge_base_router.py:175-186` |
| 11 | 컬렉션 청크 뷰어 선례: `GetChunksUseCase`(요약 제외 + 전략 감지 + `_build_hierarchy`), 프론트 `ChunkDetailPanel`(카드 6개/페이지 클라이언트 페이지네이션) | `get_chunks_use_case.py`, `ChunkDetailPanel.tsx` |
| 12 | 섹션 요약 잡 상태 API는 존재하나 **프론트 미연동** | `knowledge_base_router.py:417, 445`, 프론트 grep 0건 |
| 13 | ES `_id`=chunk_id, Qdrant point id와 불일치 | `es_chunk_expander.py:4-6` |

---

## 3. 결정사항 (D1~D9)

| ID | 결정 | 근거 |
|----|------|------|
| **D1** | 조회 API 3종은 `knowledge_base_router` 하위 신규 (`/{kb_id}/documents/{document_id}/summary`, `/section-summaries`, `/chunks`). 기존 컬렉션 API(`doc_browse_router`)·요약 파이프라인 무변경 | 독립 opt-in, KB 권한 검증 재사용 |
| **D2** | 모든 조회 API에 `source: "qdrant" \| "es"` 쿼리 파라미터 (기본값 `qdrant`). 프론트는 패널 상단 저장소 토글로 항상 명시 전송 | 사용자 결정 ① — 두 저장소를 나눠서 확인 |
| **D3** | 청크 키워드 검색 `q`는 선택된 source에서 실행: **ES** = `match`(content, nori 형태소) / **Qdrant** = scroll 전체 조회 후 서버측 대소문자 무시 부분일치 필터 | 사용자 결정 ② + Qdrant 풀텍스트 인덱스 부재(As-Is #4). payload index 마이그레이션은 범위 외 — 응답에 `search_mode`(`"match"`/`"contains"`) 명시해 UI가 차이 안내 |
| **D4** | KB 소속 검증 공통 가드: `KnowledgeBaseUseCase.get(kb_id, user)` (404/403) → `document_metadata.find_by_id`로 `kb_id` 일치 확인, 불일치·kb_id NULL이면 404. 검증 결과에서 `collection_name`(Qdrant용)·`filename` 획득 | KB 격리 계약, V047 kb_id 컬럼 기준 |
| **D5** | 응답 정규화: 두 저장소 결과를 동일 스키마로 통일(요약본문은 ES `summary_text` / Qdrant `content`를 `summary_text` 필드로 정규화). 각 항목에 원본 payload/소스 필드를 `metadata: Dict[str,str]`로 그대로 노출 (payload 메타 눈검증 요건) | Plan In-Scope B |
| **D6** | 문서 요약 미생성 시 404가 아닌 `{exists: false}` 응답 | 요약 없는 문서와 잘못된 접근 구분 |
| **D7** | Qdrant 조회는 `client.scroll` 직접 사용(선례 준수, 요약 가드 미적용 경로). 요약 계층은 `chunk_type` 필터로, 청크는 요약 chunk_type 제외로 분리 | As-Is #7, #8 |
| **D8** | 서버 페이지네이션 없이 전량 반환(scroll limit 10000 / ES size 10000), 페이지네이션은 프론트 클라이언트측 | `GetChunksUseCase`·`ChunkDetailPanel` 선례와 동일. Plan의 "API 페이지네이션" 항목을 선례 일관성 우선으로 조정 |
| **D9** | 섹션 요약 잡 상태는 기존 API 프론트 연동만 신규 (`GET/POST .../section-summary`, `/retry`) — 잡이 running이면 5초 폴링, 완료 시 목록 refetch | As-Is #12 |

---

## 4. 백엔드 설계 (idt/)

### 4.1 API 계약 (knowledge_base_router.py에 추가)

```
GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/summary
    ?source=qdrant|es                          (기본 qdrant)
→ KbDocumentSummaryResponse
    { exists: bool, source: str,
      chunk_id?: str, summary_text?: str, keywords?: list[str],
      section_count?: int, filename?: str, metadata?: dict[str,str] }

GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/section-summaries
    ?source=qdrant|es
→ KbSectionSummaryListResponse
    { source: str, document_id: str, total: int,
      items: [ { chunk_id, section_ref, clause_title, chunk_index: int,
                 summary_text, keywords: list[str], metadata: dict[str,str] } ] }
    # chunk_index 오름차순 정렬(str→int 캐스팅, 실패 시 0)

GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/chunks
    ?source=qdrant|es & include_parent=bool & q=str?
→ KbDocumentChunksResponse
    { source: str, search_mode: "match"|"contains"|null,
      document_id, filename, chunk_strategy, total_chunks,
      chunks: [ChunkDetailResponse], parents?: [ParentChunkGroupResponse] }
    # ChunkDetail/ParentChunkGroup 구조는 doc_browse_router.py:46-68과 동일 형태로 신규 정의
```

- 오류: KB 미존재/문서 미소속 → 404, 읽기권한 없음 → 403 (기존 `_raise_http` 재사용)
- `q` 지정 + `include_parent=true`인 경우: 매칭 child의 parent 그룹만 유지(parent content 매칭도 포함)

### 4.2 애플리케이션 (src/application/knowledge_base/)

신규 3파일. 생성자 의존성은 `GetChunksUseCase` 선례처럼 클라이언트 직접 주입:

```python
# content_browse_guard.py (공통 가드 — 3 UseCase가 조합해서 사용)
class KbDocumentGuard:
    def __init__(self, kb_use_case: KnowledgeBaseUseCase,
                 doc_meta_repo: DocumentMetadataRepositoryInterface, logger): ...
    async def ensure(self, kb_id, document_id, user, request_id) -> KbDocumentContext:
        # ① kb_use_case.get(kb_id, user) — ValueError/PermissionError 그대로 전파
        # ② doc_meta = doc_meta_repo.find_by_id(document_id)
        #    doc_meta 없음 or doc_meta.kb_id != kb_id → ValueError("document ... not found in kb ...")
        # ③ return KbDocumentContext(collection_name, filename, chunk_strategy)

# get_kb_document_summary_use_case.py
class GetKbDocumentSummaryUseCase:
    def __init__(self, guard, qdrant_client: AsyncQdrantClient,
                 es_repo: ElasticsearchRepository, es_index: str, logger): ...
    async def execute(self, kb_id, document_id, source: str, user, request_id) -> KbDocumentSummaryResult

# list_kb_section_summaries_use_case.py
class ListKbSectionSummariesUseCase:  # 동일 의존성
    async def execute(self, kb_id, document_id, source, user, request_id) -> KbSectionSummaryListResult

# get_kb_document_chunks_use_case.py
class GetKbDocumentChunksUseCase:  # 동일 의존성
    async def execute(self, kb_id, document_id, source, include_parent, q, user, request_id) -> KbDocumentChunksResult
```

**소스별 조회 로직** (UseCase 내부 private 메서드로 분기, if 중첩 2단계 이내 유지):

| 계층 | Qdrant (`collection_name` 컬렉션에 scroll) | ES (`es_index`에 ESSearchQuery) |
|------|------|------|
| 문서 요약 | filter: `document_id` + `chunk_type=document_summary`, limit 1. `content`→summary_text, `keywords`, `section_count` | bool filter: term `kb_id`+`document_id`+`chunk_type=document_summary`, size 1. `summary_text`, `summary_keywords` |
| 섹션 요약 | filter: `document_id` + `chunk_type=section_summary`. `content`→summary_text | bool filter: 동일 + `chunk_type=section_summary`, size 10000 |
| 청크 | filter: `document_id`, 요약 chunk_type 2종 제외(기존 로직), q는 Python `q.lower() in content.lower()` | bool filter: term `kb_id`+`document_id` + must_not term chunk_type 요약 2종; q 있으면 must: `{"match": {"content": q}}`, size 10000 |

- 청크 계층/전략 처리(`_detect_strategy`, `_build_hierarchy`, `_build_flat_list`)는 `GetChunksUseCase`의 로직을 **payload dict 리스트 입력의 공용 헬퍼로 추출**(`src/application/doc_browse/chunk_assembler.py` 신규)해 양쪽 UseCase가 공유 — `GetChunksUseCase`는 내부 구현만 헬퍼 호출로 바뀌고 시그니처/응답 무변경
- ES hit → payload dict 변환 시 `_id`를 `chunk_id`로 사용(As-Is #13), 값 str 캐스팅해 Qdrant 경로와 동일 형태로 정규화
- 결과 dataclass는 `src/domain/doc_browse/schemas.py` 패턴대로 `src/domain/knowledge_base/browse_schemas.py`(신규)에 정의

### 4.3 인터페이스 (knowledge_base_router.py)

- DI 플레이스홀더 3종 추가: `get_kb_document_summary_use_case`, `get_kb_section_summaries_use_case`, `get_kb_document_chunks_use_case`
- 응답 스키마 인라인 정의(§4.1), `source` 파라미터는 `Query(pattern="^(qdrant|es)$")`로 검증 (Gap P1 반영 — 기능 동등, 잘못된 값 422)
- 엔드포인트는 UseCase 위임 + `_raise_http` 예외 매핑만 (비즈니스 로직 금지)

### 4.4 DI 조립 (main.py)

- `_kb_browse_uc_factory` 패턴: `AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)` + `ElasticsearchClient.from_config(ElasticsearchConfig(...))` → `ElasticsearchRepository` (선례: main.py:3831-3837) + `KbDocumentGuard`(kb_use_case·doc_meta_repo는 세션 필요 → `Depends(get_session)` 팩토리, 선례: `kb_documents_factory` main.py:2727)
- `app.dependency_overrides` 3건 바인딩

### 4.5 무변경 명시

- `doc_browse_router` 기존 엔드포인트, `GetChunksUseCase` 공개 시그니처/응답
- `DualStoreSummaryWriter`, `document_summary_step` (읽기만 추가)
- Qdrant 컬렉션 설정/인덱스 (payload index 생성 안 함)
- ES 매핑 (신규 필드 0)

---

## 5. 프론트엔드 설계 (idt_front/)

### 5.1 타입 (src/types/knowledgeBase.ts)

```ts
export type KbStoreSource = 'qdrant' | 'es';

export interface KbDocumentSummaryResponse {
  exists: boolean; source: KbStoreSource;
  chunk_id?: string; summary_text?: string; keywords?: string[];
  section_count?: number; filename?: string; metadata?: Record<string, string>;
}
export interface KbSectionSummaryItem {
  chunk_id: string; section_ref: string; clause_title: string; chunk_index: number;
  summary_text: string; keywords: string[]; metadata: Record<string, string>;
}
export interface KbSectionSummaryListResponse { source: KbStoreSource; document_id: string; total: number; items: KbSectionSummaryItem[]; }
export interface KbDocumentChunksResponse {  // 청크 타입은 KB 전용 로컬 정의 (Gap P2 — collection 타입과 chunk_type/metadata 계약이 달라 의도적 분리)
  source: KbStoreSource; search_mode: 'match' | 'contains' | null;
  document_id: string; filename: string; chunk_strategy: string; total_chunks: number;
  chunks: ChunkDetail[]; parents?: ParentChunkGroup[];
}
export interface SectionSummaryStatusResponse {  // 기존 백엔드 스키마 대응 (신규 연동)
  job_id: string; document_id: string; status: string;
  total_sections: number | null; done_sections: number; failed_sections: number;
  is_stale: boolean; error: string | null; created_at: string; updated_at: string;
}
```

### 5.2 상수/서비스/훅/queryKey

- `constants/api.ts`: `KNOWLEDGE_BASE_DOCUMENT_SUMMARY(kbId, docId)`, `KNOWLEDGE_BASE_SECTION_SUMMARIES(kbId, docId)`, `KNOWLEDGE_BASE_DOCUMENT_CHUNKS(kbId, docId)`, `KNOWLEDGE_BASE_SECTION_SUMMARY_STATUS(kbId, docId)`, `KNOWLEDGE_BASE_SECTION_SUMMARY_RETRY(kbId, docId)`
- `services/knowledgeBaseService.ts`: `getKbDocumentSummary(kbId, docId, { source })`, `getKbSectionSummaries(...)`, `getKbDocumentChunks(kbId, docId, { source, include_parent, q })`, `getSectionSummaryStatus(kbId, docId)`, `retrySectionSummary(kbId, docId)`
- `hooks/useKnowledgeBases.ts`: `useKbDocumentSummary`, `useKbSectionSummaries`, `useKbDocumentChunks` (`enabled: !!kbId && !!docId`), `useSectionSummaryStatus` — `refetchInterval: status가 running이면 5000, 아니면 false`(D9), `useRetrySectionSummary` mutation(성공 시 status·sectionSummaries 무효화)
- `lib/queryKeys.ts`: `queryKeys.knowledgeBases.documentSummary(kbId, docId, source)`, `.sectionSummaries(kbId, docId, source)`, `.chunks(kbId, docId, params)`, `.sectionSummaryStatus(kbId, docId)`

### 5.3 컴포넌트

```
pages/KnowledgeBaseDetailPage/index.tsx        (수정)
├── selectedDoc: KbDocumentInfo | null 상태 추가
├── KbDocumentTable  onRowClick={setSelectedDoc(재클릭 시 null)} selectedId 전달
└── {selectedDoc && <KbDocumentContentPanel kbId={kbId} document={selectedDoc} />}

components/knowledge-base/KbDocumentContentPanel.tsx   (신규 — 컨테이너)
├── 패널 헤더: 📄 filename + 닫기 버튼
├── 저장소 토글 [Qdrant | Elasticsearch]  → source 상태 (패널 레벨, 3탭 공유)
├── 탭 [문서 요약] [섹션 요약] [청크]
│   ├── 문서 요약 탭: useKbDocumentSummary — exists=false면 "요약 미생성" 안내,
│   │                  있으면 summary_text + keywords 칩 + 메타 토글
│   ├── 섹션 요약 탭: <KbSectionSummaryList/>
│   └── 청크 탭:     <KbChunkList/>
└── 공용: MetadataToggle(접힌 상태 기본, dict를 key:value 표로 표시)

components/knowledge-base/KbSectionSummaryList.tsx     (신규)
├── useSectionSummaryStatus: status !== completed면 진행률 바(done/total) + 재시도 버튼(failed>0 or is_stale)
└── useKbSectionSummaries: clause_title + summary_text 카드 목록(chunk_index순) + 메타 토글

components/knowledge-base/KbChunkList.tsx              (신규)
├── 검색 입력(debounce 400ms) → q 파라미터 / source=qdrant면 "단순 포함 검색" 힌트 배지(search_mode)
├── include_parent 체크박스(기본 on, parent_child 전략일 때만 표시)
├── parents 있으면 parent 카드 + children 들여쓰기, 없으면 flat 카드
│   (ChunkDetailPanel.tsx의 flatMap 패턴 준용, content 접기/펼치기 + 메타 토글)
└── 클라이언트 페이지네이션 (CARDS_PER_PAGE=6 선례 준용)

components/knowledge-base/KbDocumentTable.tsx          (수정)
└── props에 onRowClick?, selectedId? 추가 — 행 클릭/선택 하이라이트
```

---

## 6. 테스트 목록 (TDD — 테스트 먼저)

### 백엔드 (pytest)

| 파일 | 케이스 |
|------|--------|
| `tests/application/knowledge_base/test_kb_document_guard.py` | KB 미존재 ValueError / 권한없음 PermissionError / doc kb_id 불일치·NULL ValueError / 정상 시 collection_name 반환 |
| `tests/application/knowledge_base/test_get_kb_document_summary_use_case.py` | qdrant 소스(scroll 호출·필터 검증), es 소스(ESSearchQuery 검증), 요약 없음 exists=false, summary_text 정규화 |
| `tests/application/knowledge_base/test_list_kb_section_summaries_use_case.py` | 소스별 조회, chunk_index 정렬(str→int), 빈 목록 |
| `tests/application/knowledge_base/test_get_kb_document_chunks_use_case.py` | 요약 chunk_type 제외, q 필터(qdrant contains / es match 쿼리 구성), include_parent 계층, search_mode 값 |
| `tests/application/doc_browse/test_chunk_assembler.py` | 추출 헬퍼: 전략 감지·계층 조립 (기존 GetChunksUseCase 테스트 결과와 동등성) |
| `tests/api/test_knowledge_base_browse_router.py` | 3 엔드포인트 200/404/403, source 검증(잘못된 값 422) |

### 프론트엔드 (Vitest + RTL + MSW, per-file server 훅 + `--pool=threads`)

| 파일 | 케이스 |
|------|--------|
| `src/components/knowledge-base/KbDocumentContentPanel.test.tsx` | 탭 전환, 저장소 토글 시 source 파라미터 변경(양 탭 공유), 닫기, 로딩/에러 |
| `src/components/knowledge-base/KbChunkList.test.tsx` | flat/계층 렌더, 접기/펼치기, 검색 입력→q 요청 반영, search_mode 힌트, 메타 토글, 페이지네이션 |
| `src/components/knowledge-base/KbSectionSummaryList.test.tsx` | 목록 렌더, running 진행률+재시도 버튼, 재시도 클릭→mutation, completed면 진행률 미표시 |
| `src/components/knowledge-base/KbDocumentTable.test.tsx` | 행 클릭 콜백, 선택 하이라이트 (기존 테스트 확장) |
| MSW 핸들러 | 신규 엔드포인트 5종 (summary/section-summaries/chunks/status/retry) |

---

## 7. 구현 순서

| 순서 | 작업 |
|------|------|
| 1 | `chunk_assembler.py` 추출 + 동등성 테스트 (기존 GetChunksUseCase 회귀 확인) |
| 2 | `KbDocumentGuard` + 테스트 |
| 3 | UseCase 3종 + 테스트 (qdrant/es 분기) |
| 4 | 라우터 스키마·엔드포인트 + DI(main.py) + 라우터 테스트 |
| 5 | 프론트 타입/상수/서비스/훅/queryKeys + MSW 핸들러 |
| 6 | `KbChunkList` → `KbSectionSummaryList` → `KbDocumentContentPanel` + 테스트 |
| 7 | `KbDocumentTable` 행 클릭 + 페이지 통합 |
| 8 | dev 서버 브라우저 확인 (Qdrant/ES 기동 필요 — 불가 시 E2E pending 체크리스트 편입) |

---

## 8. 수용 기준 (Plan §10 매핑)

- [ ] 문서 행 클릭 → 패널 표시/재클릭 닫기 (Plan #1)
- [ ] 저장소 토글로 ES/Qdrant 각각 조회 — 3탭 모두 (사용자 결정 ①)
- [ ] 문서 요약 exists=false 안내 (Plan #2)
- [ ] 섹션 요약 목록 + 잡 진행률/재시도 (Plan #3)
- [ ] 청크 계층 + 접기/펼치기 (Plan #4)
- [ ] 키워드 검색이 선택 저장소에서 동작, search_mode 표기 (Plan #5, 사용자 결정 ②)
- [ ] payload/소스 메타 토글 표시 (Plan #6)
- [ ] 타 KB 문서 접근 404 (Plan #7)
- [ ] 신규 테스트 전부 통과, 기존 GetChunksUseCase 회귀 없음 (Plan #8)

---

## 9. 영향 범위 / 주의

- **기존 API 무변경**: `doc_browse_router`, 요약 파이프라인, Qdrant/ES 스키마 전부 읽기 전용 사용. `GetChunksUseCase`는 내부 구현만 헬퍼로 위임(시그니처·응답 동일) — 동등성 테스트로 보증
- **V047 이전 레거시 문서**: kb_id NULL → 가드에서 404. KB 업로드 문서만 대상 (kb-management-ui D4와 동일 정책)
- **ES/Qdrant 값 차이**: Qdrant payload는 전부 str 캐스팅됨(list는 repr) — 메타 표시는 원본 그대로 노출이 목적이므로 별도 복원 없음. `keywords`만 UI 칩 표시를 위해 정규화(`parse_keyword_list` 선례 참고)
- **Qdrant 검색은 단순 포함 검색**: 형태소 분석 없음 — UI에 search_mode 배지로 명시. 정밀 검색이 필요하면 ES 토글 안내
- **미기동 환경**: 로컬에 Qdrant/ES 없으면 브라우저 실측 불가 → `kb-pipeline-e2e-pending` 체크리스트에 항목 추가
