# hybrid-search-ui Plan Document

> **Feature**: 컬렉션 범위 하이브리드 검색 UI (BM25/벡터 가중치 조정 + 검색 히스토리)
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규
> **Date**: 2026-04-28
> **Status**: Draft
> **API Doc Ref**: `docs/api/collection-scoped-search.md`

---

## 1. 개요

### 1.1 목표

`/collections/{collectionName}/documents` 페이지의 "벡터 검색 테스트" 섹션을 **하이브리드 검색 UI**로 개선한다.

- 기존 Top K(3/5/10) 선택 외에 **BM25 가중치 / 벡터 가중치** 슬라이더 추가
- 검색 결과에 **BM25 rank, vector rank, source(bm25/vector/both), RRF score** 상세 표시
- **검색 히스토리** 조회 기능 추가
- 현재 Mock/TODO 상태인 `handleSearch`를 **실제 API 연동**으로 교체

### 1.2 비목표 (Scope Out)

- 문서 스코프 검색 UI (`/{collection_name}/documents/{document_id}/search`) — 향후 별도 구현
- `bm25_top_k`, `vector_top_k`, `rrf_k` 고급 파라미터 조정 UI — 기본값 사용, 향후 "고급 옵션" 토글로 확장 가능
- 검색 히스토리 삭제 기능 — API 미지원

---

## 2. 백엔드 API 계약

> 백엔드 구현 완료 상태. API 문서: `docs/api/collection-scoped-search.md`

| Method | Endpoint | 설명 | 인증 |
|--------|----------|------|------|
| POST | `/api/v1/collections/{collection_name}/search` | 컬렉션 범위 하이브리드 검색 | JWT 필수 |
| GET | `/api/v1/collections/{collection_name}/search-history` | 검색 히스토리 조회 | JWT 필수 |

### 2.1 검색 요청 스키마

```typescript
interface CollectionSearchRequest {
  query: string;             // 필수, min_length=1
  top_k?: number;            // 기본 10, 1~50
  bm25_weight?: number;      // 기본 0.5, 0.0~1.0
  vector_weight?: number;    // 기본 0.5, 0.0~1.0
  bm25_top_k?: number;       // 기본 20, 1~100
  vector_top_k?: number;     // 기본 20, 1~100
  rrf_k?: number;            // 기본 60, >= 1
}
```

### 2.2 검색 응답 스키마

```typescript
interface CollectionSearchResponse {
  query: string;
  collection_name: string;
  results: SearchResultItem[];
  total_found: number;
  bm25_weight: number;
  vector_weight: number;
  request_id: string;
  document_id: string | null;
}

interface SearchResultItem {
  id: string;
  content: string;
  score: number;             // Weighted RRF 점수
  bm25_rank: number | null;
  bm25_score: number | null;
  vector_rank: number | null;
  vector_score: number | null;
  source: 'bm25' | 'vector' | 'both';
  metadata: Record<string, unknown>;
}
```

### 2.3 검색 히스토리 응답 스키마

```typescript
interface SearchHistoryResponse {
  collection_name: string;
  histories: SearchHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

interface SearchHistoryItem {
  id: number;
  query: string;
  document_id: string | null;
  bm25_weight: number;
  vector_weight: number;
  top_k: number;
  result_count: number;
  created_at: string;        // ISO 8601
}
```

### 2.4 에러 코드

| HTTP Code | 설명 | UI 처리 |
|-----------|------|---------|
| 401 | JWT 만료 | authClient 인터셉터가 자동 갱신 |
| 403 | 컬렉션 읽기 권한 없음 | toast 에러 |
| 404 | 컬렉션 없음 | toast 에러 |
| 422 | 파라미터 유효성 실패 | toast 에러 (가중치 범위, 빈 쿼리 등) |

---

## 3. 화면 설계

### 3.1 기존 UI → 변경 사항

```
기존 "벡터 검색 테스트" 섹션:
├── 검색 입력창
├── Top K 선택 (3 / 5 / 10)
├── 검색 버튼
├── 예시 쿼리 칩
└── (결과 없음 — TODO)

변경 후 "하이브리드 검색" 섹션:
├── 섹션 헤더: "하이브리드 검색" + "Mock" 뱃지 제거
├── 검색 입력창 (기존 유지)
├── 검색 옵션 패널 (신규)
│   ├── Top K 선택 (3 / 5 / 10 / 20)
│   ├── BM25 가중치 슬라이더 (0.0 ~ 1.0, step 0.1, 기본 0.5)
│   ├── 벡터 가중치 슬라이더 (0.0 ~ 1.0, step 0.1, 기본 0.5)
│   └── 프리셋 버튼 (균형 / BM25 중심 / 벡터 중심)
├── 검색 버튼
├── 예시 쿼리 칩 (기존 유지)
├── 검색 결과 카드 목록 (신규)
│   └── SearchResultCard
│       ├── 순위 뱃지 (#1, #2, ...)
│       ├── source 뱃지 (BM25 / Vector / Both)
│       ├── RRF Score
│       ├── BM25 Rank / Score (있으면 표시)
│       ├── Vector Rank / Score (있으면 표시)
│       ├── 청크 내용 (접기/펼치기)
│       └── 메타데이터 (document_id 등)
└── 검색 히스토리 패널 (신규, 토글)
    ├── 최근 검색 목록
    │   └── 쿼리 | 가중치 | top_k | 결과 수 | 시간
    └── 클릭 시 해당 설정으로 자동 채우기
```

### 3.2 UI 컴포넌트 목록

| Component | 위치 | 역할 |
|-----------|------|------|
| `HybridSearchPanel` | `components/collection/HybridSearchPanel.tsx` | 검색 옵션 + 실행 통합 패널 |
| `WeightSlider` | `components/collection/WeightSlider.tsx` | BM25/벡터 가중치 슬라이더 |
| `SearchResultCard` | `components/collection/SearchResultCard.tsx` | 개별 검색 결과 카드 |
| `SearchResultList` | `components/collection/SearchResultList.tsx` | 결과 목록 + 빈 상태 + 로딩 |
| `SearchHistoryPanel` | `components/collection/SearchHistoryPanel.tsx` | 히스토리 목록 + 재검색 |

---

## 4. 파일 구조 및 구현 순서

### Phase 1: 기반 (타입, 상수, 서비스)

| # | 파일 | 작업 | 설명 |
|---|------|------|------|
| 1 | `src/types/collection.ts` | 수정 | 검색 관련 타입 추가 (SearchRequest, SearchResponse, HistoryResponse) |
| 2 | `src/constants/api.ts` | 수정 | `COLLECTION_SEARCH`, `COLLECTION_SEARCH_HISTORY` 엔드포인트 추가 |
| 3 | `src/lib/queryKeys.ts` | 수정 | `collections.search`, `collections.searchHistory` 키 추가 |
| 4 | `src/services/collectionService.ts` | 수정 | `searchCollection`, `getSearchHistory` 메서드 추가 |

### Phase 2: 훅

| # | 파일 | 작업 | 설명 |
|---|------|------|------|
| 5 | `src/hooks/useCollections.ts` | 수정 | `useCollectionSearch` (mutation), `useSearchHistory` (query) 추가 |

### Phase 3: 컴포넌트

| # | 파일 | 작업 | 설명 |
|---|------|------|------|
| 6 | `src/components/collection/WeightSlider.tsx` | 신규 | 가중치 슬라이더 (레이블 + range input + 수치 표시) |
| 7 | `src/components/collection/SearchResultCard.tsx` | 신규 | 개별 검색 결과 카드 (순위, 점수, source 뱃지, 내용) |
| 8 | `src/components/collection/SearchResultList.tsx` | 신규 | 결과 목록 래퍼 (로딩/빈 상태/에러 처리) |
| 9 | `src/components/collection/SearchHistoryPanel.tsx` | 신규 | 히스토리 목록 + 클릭 시 설정 자동 채우기 |
| 10 | `src/components/collection/HybridSearchPanel.tsx` | 신규 | 검색 옵션 통합 패널 (가중치 + 프리셋 + Top K) |

### Phase 4: 페이지 통합

| # | 파일 | 작업 | 설명 |
|---|------|------|------|
| 11 | `src/pages/CollectionDocumentsPage/index.tsx` | 수정 | 기존 "벡터 검색 테스트" 섹션을 새 컴포넌트로 교체, API 연동 |

### Phase 5: 테스트

| # | 파일 | 작업 | 설명 |
|---|------|------|------|
| 12 | `src/hooks/useCollections.test.ts` | 수정 | `useCollectionSearch`, `useSearchHistory` 훅 테스트 추가 |
| 13 | `src/__tests__/mocks/handlers.ts` | 수정 | 검색/히스토리 MSW 핸들러 추가 |

---

## 5. TypeScript 타입 상세

```typescript
// src/types/collection.ts 에 추가

// ── 하이브리드 검색 관련 타입 ────────────────────────────

export type SearchSource = 'bm25' | 'vector' | 'both';

export interface CollectionSearchRequest {
  query: string;
  top_k?: number;
  bm25_weight?: number;
  vector_weight?: number;
  bm25_top_k?: number;
  vector_top_k?: number;
  rrf_k?: number;
}

export interface SearchResultItem {
  id: string;
  content: string;
  score: number;
  bm25_rank: number | null;
  bm25_score: number | null;
  vector_rank: number | null;
  vector_score: number | null;
  source: SearchSource;
  metadata: Record<string, unknown>;
}

export interface CollectionSearchResponse {
  query: string;
  collection_name: string;
  results: SearchResultItem[];
  total_found: number;
  bm25_weight: number;
  vector_weight: number;
  request_id: string;
  document_id: string | null;
}

export interface SearchHistoryItem {
  id: number;
  query: string;
  document_id: string | null;
  bm25_weight: number;
  vector_weight: number;
  top_k: number;
  result_count: number;
  created_at: string;
}

export interface SearchHistoryResponse {
  collection_name: string;
  histories: SearchHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export const SEARCH_SOURCE_BADGE: Record<SearchSource, { label: string; color: string; bg: string }> = {
  bm25: { label: 'BM25', color: 'text-orange-600', bg: 'bg-orange-50' },
  vector: { label: 'Vector', color: 'text-blue-600', bg: 'bg-blue-50' },
  both: { label: 'Both', color: 'text-emerald-600', bg: 'bg-emerald-50' },
};

export const WEIGHT_PRESETS = {
  balanced: { bm25_weight: 0.5, vector_weight: 0.5, label: '균형' },
  bm25_heavy: { bm25_weight: 0.8, vector_weight: 0.2, label: 'BM25 중심' },
  vector_heavy: { bm25_weight: 0.2, vector_weight: 0.8, label: '벡터 중심' },
  bm25_only: { bm25_weight: 1.0, vector_weight: 0.0, label: 'BM25만' },
  vector_only: { bm25_weight: 0.0, vector_weight: 1.0, label: '벡터만' },
} as const;
```

---

## 6. API 상수 및 Query Keys

### 6.1 API Endpoints 추가

```typescript
// src/constants/api.ts — API_ENDPOINTS에 추가
COLLECTION_SEARCH: (name: string) =>
  `/api/v1/collections/${name}/search`,
COLLECTION_SEARCH_HISTORY: (name: string) =>
  `/api/v1/collections/${name}/search-history`,
```

### 6.2 Query Keys 추가

```typescript
// src/lib/queryKeys.ts — collections 키에 추가
search: (name: string, params?: CollectionSearchRequest) =>
  [...queryKeys.collections.all, 'search', name, params] as const,
searchHistory: (name: string, limit?: number, offset?: number) =>
  [...queryKeys.collections.all, 'searchHistory', name, { limit, offset }] as const,
```

---

## 7. 서비스 레이어

```typescript
// src/services/collectionService.ts 에 추가

searchCollection: async (
  collectionName: string,
  data: CollectionSearchRequest,
): Promise<CollectionSearchResponse> => {
  const res = await authApiClient.post<CollectionSearchResponse>(
    API_ENDPOINTS.COLLECTION_SEARCH(collectionName),
    data,
  );
  return res.data;
},

getSearchHistory: async (
  collectionName: string,
  params?: { limit?: number; offset?: number },
): Promise<SearchHistoryResponse> => {
  const res = await authApiClient.get<SearchHistoryResponse>(
    API_ENDPOINTS.COLLECTION_SEARCH_HISTORY(collectionName),
    { params },
  );
  return res.data;
},
```

---

## 8. TanStack Query 훅

```typescript
// src/hooks/useCollections.ts 에 추가

export const useCollectionSearch = () =>
  useMutation({
    mutationFn: ({ collectionName, data }: {
      collectionName: string;
      data: CollectionSearchRequest;
    }) => collectionService.searchCollection(collectionName, data),
    onSuccess: (_, { collectionName }) =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.collections.searchHistory(collectionName),
      }),
  });

export const useSearchHistory = (
  collectionName: string,
  params?: { limit?: number; offset?: number },
) =>
  useQuery({
    queryKey: queryKeys.collections.searchHistory(
      collectionName, params?.limit, params?.offset,
    ),
    queryFn: () => collectionService.getSearchHistory(collectionName, params),
    enabled: !!collectionName,
  });
```

> 검색은 `useMutation` 사용 — 동일 쿼리를 반복 실행할 수 있고, 결과를 캐시할 필요 없음.
> 검색 성공 시 히스토리 쿼리를 자동 무효화하여 최신 히스토리 반영.

---

## 9. UX 상세

### 9.1 가중치 슬라이더 디자인

```
BM25 가중치:  ●━━━━━━━━━━━━━━━○  0.5
벡터 가중치:  ●━━━━━━━━━━━━━━━○  0.5

[균형] [BM25 중심] [벡터 중심]
```

- range input + 우측에 수치 표시 (소수 1자리)
- 프리셋 버튼 클릭 시 두 슬라이더 동시 업데이트
- 디자인 시스템 색상: 슬라이더 트랙 `bg-zinc-200`, 활성 `bg-violet-500`

### 9.2 검색 결과 카드

```
┌─────────────────────────────────────────────┐
│ #1  [Both]  Score: 0.032                    │
│ BM25: rank #1, score 12.5                   │
│ Vector: rank #3, score 0.85                 │
│ ─────────────────────────────────────────── │
│ 문서 내용이 여기에 표시됩니다...             │
│ ...                                          │
│                          [더보기 / 접기]      │
│ 📄 doc-uuid                                 │
└─────────────────────────────────────────────┘
```

- source 뱃지 색상: BM25=주황, Vector=파랑, Both=초록
- 내용 기본 3줄, 클릭 시 전체 표시
- score 소수 4자리까지 표시

### 9.3 검색 히스토리

- 기본 숨김, "검색 히스토리" 토글 버튼으로 표시/숨김
- 테이블 형태: 쿼리 | BM25 wt | Vector wt | Top K | 결과 수 | 시간
- 행 클릭 시: `searchQuery`, `bm25Weight`, `vectorWeight`, `topK` 상태를 해당 값으로 자동 채우기 (재검색 편의)
- 최근 10건 기본 표시, "더보기"로 확장

### 9.4 Top K 옵션 확장

```typescript
const TOP_K_OPTIONS = [3, 5, 10, 20] as const;
```

- 기존 [3, 5, 10]에 20 추가 (API 최대 50이지만 UI에서는 실용적 범위)

### 9.5 에러 처리 UX

| 상황 | UI 피드백 |
|------|----------|
| 빈 쿼리 전송 시도 | 검색 버튼 disabled + placeholder 안내 |
| 검색 중 | 버튼 로딩 스피너 + 결과 영역 스켈레톤 |
| 검색 성공 | 결과 카드 렌더링 + total_found 표시 |
| 결과 0건 | "검색 결과가 없습니다" 안내 메시지 |
| API 에러 | toast 에러 메시지 |

---

## 10. 기술 규칙 (idt_front/CLAUDE.md 준수)

- **Tailwind CSS v4** 스타일링, 디자인 시스템 색상 토큰 사용
- **Arrow function** 컴포넌트, Props는 `interface`로 정의
- **서비스 레이어** 통해 API 호출 (컴포넌트에서 직접 axios 금지)
- **queryKeys 팩토리** 사용 (직접 문자열 배열 금지)
- **authApiClient** 사용 (JWT 토큰 자동 주입)
- 컴포넌트 200줄 초과 시 분리

---

## 11. 의존성

- 추가 패키지 없음
- 백엔드 API 구현 완료 (`collection-scoped-search`)
- 기존 `collectionService`, `useCollections` 훅에 메서드/훅 추가

---

## 12. 예상 소요

| Phase | 파일 수 | 규모 |
|-------|---------|------|
| Phase 1: 기반 (타입, 상수, 서비스) | 4 (수정) | 작음 |
| Phase 2: 훅 | 1 (수정) | 작음 |
| Phase 3: 컴포넌트 | 5 (신규) | 중간 |
| Phase 4: 페이지 통합 | 1 (수정) | 중간 |
| Phase 5: 테스트 | 2 (수정) | 작음 |
| **합계** | **13** | **중간** |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-28 | Initial draft — collection-scoped-search API 기반 | 배상규 |
