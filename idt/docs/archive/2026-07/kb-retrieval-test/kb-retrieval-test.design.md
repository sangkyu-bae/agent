# kb-retrieval-test Design Document

> **Summary**: KB 상세 페이지 상태 요약 카드 + 리트리버 테스트(하이브리드 검색·KB 전용 히스토리) — KB 단위 검색/히스토리 API 신설 설계
>
> **Plan**: `docs/01-plan/features/kb-retrieval-test.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-18
> **Status**: Draft

---

## 1. Overview

### 1.1 Design Goals

- `POST /knowledge-bases/{kb_id}/search`: kb_id 필터로 **해당 KB 문서만** 하이브리드 검색 (document_id 옵션으로 문서 단위 축소)
- `GET /knowledge-bases/{kb_id}/search-history`: KB 단위 본인 검색 히스토리 조회
- 프론트: KB 상세 페이지에 상태 카드 4종 + 검색 섹션 + 히스토리 패널 조립 (컬렉션 컴포넌트 최대 재사용)
- 기존 컬렉션 검색/히스토리 경로 **바이트 무변경** (additive)

### 1.2 Design Principles

- 검색 스택(임베딩 해석→HybridSearchUseCase→RRF)은 재구현하지 않고 재사용
- 권한은 **KB scope 기준**(`KnowledgeBasePolicy.can_read`) — 컬렉션 권한 검사를 타지 않는다
- domain 변경은 search_history 인터페이스의 additive 파라미터/메서드뿐

### 1.3 Plan 리스크 검증 결과 (2026-07-18 실코드 확인)

| Plan 리스크 | 검증 결과 | 근거 |
|------------|----------|------|
| KB 컬렉션에 activity_log CREATE 부재 → 임베딩 해석 실패 | **해소** — KB는 컬렉션을 새로 만들지 않고 기존 컬렉션을 배정만 받음(`UserSelectedCollectionAssigner.assign`은 존재+권한 검사만). KB 업로드(`UnifiedUploadUseCase`)도 동일한 activity_log 기반 `_resolve_embedding_model`로 이미 동작 중 → 검색도 동일 경로로 해석 가능 | `collection_assigner.py:22-36`, `unified_upload/use_case.py:80-82` |
| ES kb_id 필터 미지원 → 타 KB 문서 혼입 | **해소** — ES 매핑에 `kb_id: {"type": "keyword"}` 명시 존재, `HybridSearchUseCase._fetch_bm25`가 metadata_filter를 `{"term": {k: v}}` filter 절로 변환. Qdrant도 `SearchFilter(metadata=...)`로 동일 필터 적용 | `es_index_mappings.py:45`, `hybrid_search/use_case.py:100-108, 141-144` |

---

## 2. Design Decisions (D1–D10)

| # | Decision | 선택 | 근거 |
|---|----------|------|------|
| D1 | KB 검색 유스케이스 형태 | `KbSearchUseCase` 신설 (application/knowledge_base) — `CollectionSearchUseCase`를 **호출하지 않고** 내부 스택 재사용 | `CollectionSearchUseCase.execute`는 컬렉션 권한 검사가 인라인이라 재사용 시 KB 권한과 이중 검사·403 오동작. 임베딩 해석 로직은 공용 헬퍼로 추출(D2) |
| D2 | 임베딩 모델 해석 재사용 방식 | `_resolve_embedding_model`을 `application/collection_search/embedding_resolver.py`의 모듈 함수 `resolve_collection_embedding_model(...)`로 추출 — `CollectionSearchUseCase`와 `KbSearchUseCase` 양쪽이 호출 | 복붙 이중화 방지. 기존 유스케이스는 내부 메서드가 헬퍼를 호출하도록만 변경(시그니처·동작 불변) |
| D3 | KB 권한/존재 검증 | `KnowledgeBaseUseCase.get(kb_id, user, request_id)` 위임 — 미존재 ValueError→404, 무권한 PermissionError→403 | kb-content-browser의 `KbDocumentGuard`와 동일 선례. kb 엔티티에서 collection_name도 함께 획득 |
| D4 | 문서 단위 검색 API 형태 | 별도 path 없이 **요청 body의 `document_id` 옵션 필드** — 값 존재 시 `KbDocumentGuard.ensure()`로 KB 소속 검증(불일치 404) 후 metadata_filter에 추가 | 컬렉션은 별도 path지만 KB는 가드 검증이 필수라 body 통합이 라우터 중복을 줄임. 프론트도 스코프 전환 UI와 자연스럽게 대응 |
| D5 | 검색 필터 구성 | `metadata_filter = {"collection_name": kb.collection_name, "kb_id": kb_id}` (+ document_id 옵션) | collection_name 필터 유지로 컬렉션 격리 보장 + kb_id로 KB 격리. V047 이전 kb_id NULL 문서는 검색에서 제외(Plan 알려진 한계 수용) |
| D6 | 히스토리 저장 스키마 | `search_history`에 `kb_id VARCHAR(64) NULL` 컬럼 + `ix_sh_user_kb (user_id, kb_id)` 인덱스 — **V049** | additive nullable — 기존 행/컬렉션 경로 무영향. FK 없음(관례상 FK/COLLATE 명시 금지 이슈 자체가 발생 안 함) |
| D7 | 히스토리 저장/조회 인터페이스 | `save(..., kb_id: Optional[str] = None)` 기본값 additive + `find_by_user_and_kb(user_id, kb_id, limit, offset, request_id)` 신설 | 기존 호출부(컬렉션 검색) 무수정. 조회는 kb_id 기준 별도 메서드 — 화이트리스트 누락형 조용한 미저장 방지 위해 저장 검증 테스트 필수 |
| D8 | KB 히스토리 조회 유스케이스 | `SearchHistoryUseCase`에 메서드 추가 대신 `KbSearchHistoryUseCase` 신설(경량) — repo의 `find_by_user_and_kb` 호출 | 기존 유스케이스 시그니처 불변. 응답 스키마는 컬렉션 히스토리와 동일 필드 + kb_id |
| D9 | 프론트 히스토리 패널 | 기존 `SearchHistoryPanel`은 무변경. 테이블 UI를 `SearchHistoryTable`(presentational)로 추출하지 **않고**, KB용 `KbSearchHistoryPanel` 신설 — 마크업은 기존 패널과 동일 구조, 데이터 훅만 `useKbSearchHistory` | 기존 컴포넌트 리팩토링은 컬렉션 화면 회귀 리스크 — additive 원칙. 중복 ~80줄은 수용(후속 통합 후보로 명시) |
| D10 | 프론트 검색 상태 관리 | `CollectionDocumentsPage`와 동일 패턴: 페이지 로컬 state + `useKbSearch` mutation. 검색 스코프(KB 전체/선택 문서)는 `searchScopeDocId: string \| null` state로 표현, 문서 드릴다운 선택(`selectedDoc`)과 독립 | 드릴다운(콘텐츠 확인)과 검색 스코프(리트리버 테스트)는 다른 관심사 — 결합 시 행 클릭마다 검색 스코프가 바뀌는 혼란 |

---

## 3. Architecture

### 3.1 Data Flow (KB 검색)

```
POST /api/v1/knowledge-bases/{kb_id}/search  {query, top_k, weights..., document_id?}
  └─ knowledge_base_router.search_in_kb
       └─ KbSearchUseCase.execute(kb_id, request, user, request_id)
            ├─ KnowledgeBaseUseCase.get(kb_id)          # 존재 404 / KB 권한 403 (D3)
            ├─ [document_id 있으면] KbDocumentGuard.ensure()   # KB 소속 검증 404 (D4)
            ├─ resolve_collection_embedding_model(kb.collection_name)   # D2 공용 헬퍼
            ├─ HybridSearchUseCase.execute(
            │     metadata_filter={collection_name, kb_id[, document_id]})   # D5
            └─ SearchHistoryRepository.save(..., kb_id=kb_id)   # 실패해도 응답 무영향 (기존 정책)
```

### 3.2 API 계약

**`POST /api/v1/knowledge-bases/{kb_id}/search`** → `KbSearchResponse`

- Request: `KbSearchBody` = 컬렉션 `CollectionSearchAPIRequest`와 동일 필드(query/top_k/bm25_top_k/vector_top_k/rrf_k/bm25_weight/vector_weight) + `document_id: Optional[str]`
- Response: 컬렉션 `CollectionSearchAPIResponse`와 동일 형태에서 `collection_name` 대신 `kb_id`/`kb_name` 포함 (collection_name도 참고용 유지)
- 에러: 404(kb 미존재·문서 KB 소속 아님), 403(KB 읽기 권한 없음), 422(파라미터)

**`GET /api/v1/knowledge-bases/{kb_id}/search-history?limit&offset`** → `KbSearchHistoryResponse`

- 본인(user_id) + kb_id 기준. items 필드는 컬렉션 히스토리와 동일 + kb_id
- KB 존재/권한 검증은 검색과 동일하게 `KnowledgeBaseUseCase.get` 선행

### 3.3 신규/변경 파일

**백엔드 (idt/)**

| 구분 | 파일 | 내용 |
|------|------|------|
| 신규 | `db/migration/V049__alter_search_history_add_kb_id.sql` | `ALTER TABLE search_history ADD COLUMN kb_id VARCHAR(64) NULL, ADD INDEX ix_sh_user_kb (user_id, kb_id)` |
| 신규 | `src/application/collection_search/embedding_resolver.py` | D2 공용 임베딩 해석 함수 |
| 신규 | `src/application/knowledge_base/search_use_case.py` | `KbSearchUseCase` (D1) |
| 신규 | `src/application/knowledge_base/search_history_use_case.py` | `KbSearchHistoryUseCase` (D8) |
| 변경 | `src/domain/collection_search/search_history_interfaces.py` | `save`에 `kb_id=None` 파라미터, `find_by_user_and_kb` 추상 메서드 추가 (D7) |
| 변경 | `src/domain/collection_search/search_history_schemas.py` | `SearchHistoryEntry.kb_id: Optional[str] = None` |
| 변경 | `src/infrastructure/collection_search/models.py` | `kb_id = Column(String(64), nullable=True)` |
| 변경 | `src/infrastructure/collection_search/search_history_repository.py` | save에 kb_id 저장, `find_by_user_and_kb` 구현 |
| 변경 | `src/application/collection_search/use_case.py` | `_resolve_embedding_model` 본문을 D2 헬퍼 호출로 위임 (동작 불변) |
| 변경 | `src/api/routes/knowledge_base_router.py` | search/search-history 엔드포인트 + 스키마 + DI 스텁 2개 |
| 변경 | `src/api/main.py` | KB 검색/히스토리 팩토리 — `create_collection_search_factories` 패턴 준수(스택 재사용), dependency_overrides 등록 |

**프론트엔드 (idt_front/)**

| 구분 | 파일 | 내용 |
|------|------|------|
| 변경 | `src/constants/api.ts` | `KNOWLEDGE_BASE_SEARCH(kbId)`, `KNOWLEDGE_BASE_SEARCH_HISTORY(kbId)` |
| 변경 | `src/types/knowledgeBase.ts` | `KbSearchRequest`, `KbSearchResponse`, `KbSearchResultItem`, `KbSearchHistoryResponse` (컬렉션 타입 참조해 정의 — import 재사용 가능하면 alias) |
| 변경 | `src/services/knowledgeBaseService.ts` | `searchKb(kbId, data)`, `getKbSearchHistory(kbId, params)` |
| 변경 | `src/hooks/useKnowledgeBases.ts` | `useKbSearch()` (mutation), `useKbSearchHistory(kbId, params)` (query, staleTime 짧게) |
| 신규 | `src/components/knowledge-base/KbStatusCards.tsx` | 상태 카드 4종 — `documents: KbDocumentInfo[]`, `total: number` props. chunk_count>0=준비완료/0=처리중/오류 0 고정 |
| 신규 | `src/components/knowledge-base/KbSearchSection.tsx` | 검색 입력+버튼+스코프 표시 + `HybridSearchPanel`/`SearchResultList` 재사용 + `KbSearchHistoryPanel` 포함 |
| 신규 | `src/components/knowledge-base/KbSearchHistoryPanel.tsx` | D9 — KB 히스토리 테이블(onApply 재적용) |
| 변경 | `src/pages/KnowledgeBaseDetailPage/index.tsx` | 카드/검색 섹션 조립, `searchScopeDocId` state, 문서 행에 "이 문서에서 검색" 액션 (D10) |

### 3.4 검색 스코프 UX (FR-09)

- 기본: "KB 전체에서 검색" 배지
- `KbDocumentTable` 행 hover/선택 시 "이 문서에서 검색" 버튼 → `searchScopeDocId` 설정, 검색 섹션 배지가 `파일명에서 검색 ✕`로 변경(✕ 클릭 시 KB 전체로 복귀)
- 검색 실행 시 `document_id: searchScopeDocId ?? undefined` 전달

---

## 4. Error Handling

| 상황 | 백엔드 | 프론트 |
|------|--------|--------|
| kb 미존재 | `KnowledgeBaseUseCase.get` ValueError → `_raise_http` 404 | 페이지 기존 에러 표시 재사용 |
| KB 읽기 권한 없음 | PermissionError → 403 | 검색 섹션에 "권한이 없습니다" 표시 |
| document_id가 KB 소속 아님 | `KbDocumentGuard` ValueError → 404 | 스코프 초기화 + 에러 토스트 |
| 임베딩 모델 해석 실패 | ValueError → 422 (컬렉션 검색과 동일) | `SearchResultList` isError 상태 재사용 |
| ES/Qdrant 한쪽 실패 | HybridSearch 내부 폴백(빈 결과) — 기존 동작 유지 | 결과 0건 표시 |
| 히스토리 저장 실패 | warning 로그만, 검색 응답 정상 (기존 정책) | 영향 없음 |

---

## 5. Test Plan (TDD — 테스트 선행)

### 5.1 단위 (신규, 백엔드)

- `tests/application/knowledge_base/test_kb_search_use_case.py` (기존 `test_use_case.py`와 충돌 회피)
  - kb_id 필터가 metadata_filter에 포함되는지 (collection_name+kb_id)
  - document_id 지정 시 가드 호출 + 필터 포함 / 가드 거부 시 ValueError 전파
  - KB 무권한 PermissionError 전파, 미존재 ValueError 전파
  - 히스토리 save가 kb_id와 함께 호출, save 실패해도 응답 정상
- `tests/application/knowledge_base/test_kb_search_history_use_case.py` — kb_id 기준 조회 위임
- `tests/infrastructure/collection_search/test_search_history_repository.py` (기존 파일 확장)
  - save kb_id 저장 검증(**조용한 미저장 방지**), `find_by_user_and_kb` 필터·정렬·total
- `tests/application/collection_search/test_use_case.py` (기존) — D2 헬퍼 추출 후 회귀 통과 확인

### 5.2 통합 (백엔드 라우터)

- `tests/api/test_knowledge_base_search.py` — 200/403/404/422, document_id 소속 검증, 히스토리 조회 페이징

### 5.3 프론트 (Vitest + MSW, `--pool=threads`, 파일별 3종 훅)

- `KbStatusCards.test.tsx` — 카운트 판정(chunk_count 0/양수 혼합)
- `KbSearchSection.test.tsx` — 검색 실행→결과 렌더, 스코프 배지 전환, 히스토리 재적용
- `KnowledgeBaseDetailPage/index.test.tsx` (기존 확장) — 카드/검색 섹션 조립 스모크

### 5.4 수동 E2E (Qdrant/ES 기동 시 — 기존 KB E2E 체크리스트에 병합)

- 같은 컬렉션 공유 KB 2개 생성 → 각 KB에 문서 업로드 → KB A 검색에 KB B 문서 미출현 확인 (FR-01 격리)
- V047 이전(kb_id NULL) 문서 미출현 확인
- 문서 단위 스코프 검색 실측

---

## 6. Clean Architecture — Layer Assignment

| Layer | 산출물 | 비고 |
|-------|--------|------|
| domain | search_history 인터페이스/스키마 additive 확장만 | 외부 의존 없음 유지 |
| application | KbSearchUseCase, KbSearchHistoryUseCase, embedding_resolver | 비즈니스 규칙 없음 — 흐름 제어만. 한 유스케이스 내 단일 세션(main.py 팩토리에서 동일 session 주입) |
| infrastructure | SearchHistoryModel/Repository 확장 | commit/rollback 금지(기존 flush 패턴 유지) |
| interfaces | knowledge_base_router 엔드포인트 2개 | 위임만, 비즈니스 로직 금지 |

---

## 7. Implementation Order

1. **V049 마이그레이션** + `SearchHistoryModel`/repo/인터페이스 확장 (테스트 선행)
2. `embedding_resolver` 추출 + 기존 `CollectionSearchUseCase` 위임 전환 (기존 테스트 회귀 확인)
3. `KbSearchUseCase` / `KbSearchHistoryUseCase` (테스트 선행)
4. 라우터 엔드포인트 + 스키마 + main.py DI (통합 테스트 선행)
5. 프론트 계약 동기화: constants → types → service → hooks (MSW 테스트 선행)
6. `KbStatusCards` → `KbSearchSection`/`KbSearchHistoryPanel` → 페이지 조립
7. `/verify-architecture`, `/verify-logging`, `/verify-tdd` + 회귀 스위트

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-18 | Initial draft — Plan 리스크 2건 실코드 해소 확인, D1–D10 확정 | 배상규 |
