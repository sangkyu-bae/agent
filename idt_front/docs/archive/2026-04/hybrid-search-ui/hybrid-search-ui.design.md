# Design: hybrid-search-ui

> Plan 참조: `docs/01-plan/features/hybrid-search-ui.plan.md`
> API 문서: `docs/api/collection-scoped-search.md`

## 1. 구현 순서

```
Step 1. src/types/collection.ts                — 검색 관련 타입 추가
Step 2. src/constants/api.ts                   — 엔드포인트 상수 추가
Step 3. src/lib/queryKeys.ts                   — queryKey 추가
Step 4. src/services/collectionService.ts      — 검색/히스토리 메서드 추가
Step 5. src/hooks/useCollections.ts            — useCollectionSearch, useSearchHistory 추가
Step 6. src/components/collection/WeightSlider.tsx          — 가중치 슬라이더
Step 7. src/components/collection/SearchResultCard.tsx      — 검색 결과 카드
Step 8. src/components/collection/SearchResultList.tsx      — 결과 목록 래퍼
Step 9. src/components/collection/SearchHistoryPanel.tsx    — 히스토리 패널
Step 10. src/components/collection/HybridSearchPanel.tsx   — 검색 옵션 통합 패널
Step 11. src/pages/CollectionDocumentsPage/index.tsx        — 기존 섹션 교체
```

---

## 2. 타입 정의 (`src/types/collection.ts` 하단 추가)

```typescript
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

export interface WeightPreset {
  bm25_weight: number;
  vector_weight: number;
  label: string;
}

export const WEIGHT_PRESETS: Record<string, WeightPreset> = {
  balanced: { bm25_weight: 0.5, vector_weight: 0.5, label: '균형' },
  bm25_heavy: { bm25_weight: 0.8, vector_weight: 0.2, label: 'BM25 중심' },
  vector_heavy: { bm25_weight: 0.2, vector_weight: 0.8, label: '벡터 중심' },
  bm25_only: { bm25_weight: 1.0, vector_weight: 0.0, label: 'BM25만' },
  vector_only: { bm25_weight: 0.0, vector_weight: 1.0, label: '벡터만' },
};
```

**네이밍 규칙 준수**:
- API 응답: `CollectionSearchResponse`, `SearchHistoryResponse` (`XxxResponse`)
- API 요청: `CollectionSearchRequest` (`XxxRequest`)
- 도메인 모델: `SearchResultItem`, `SearchHistoryItem` (접미사 없음)

---

## 3. 엔드포인트 상수 (`src/constants/api.ts`)

기존 `API_ENDPOINTS` 객체, Collections 섹션 하단에 추가:

```typescript
// Collection Search (COLLECTION-SCOPED-SEARCH)
COLLECTION_SEARCH: (name: string) =>
  `/api/v1/collections/${name}/search`,
COLLECTION_SEARCH_HISTORY: (name: string) =>
  `/api/v1/collections/${name}/search-history`,
```

---

## 4. Query Keys (`src/lib/queryKeys.ts`)

기존 `collections` 키에 추가:

```typescript
searchHistory: (name: string, params?: { limit?: number; offset?: number }) =>
  [...queryKeys.collections.all, 'searchHistory', name, params] as const,
```

> 검색은 `useMutation`으로 처리하므로 queryKey 불필요.
> 히스토리 조회만 queryKey 필요.

---

## 5. 서비스 레이어 (`src/services/collectionService.ts`)

기존 `collectionService` 객체에 2개 메서드 추가:

```typescript
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

**설계 결정**:
- `authApiClient` 사용 (JWT 필수 API)
- 검색은 POST (body로 파라미터 전달)
- 히스토리는 GET (query params로 limit/offset)

---

## 6. 훅 (`src/hooks/useCollections.ts`)

기존 파일 하단에 2개 훅 추가:

```typescript
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
    queryKey: queryKeys.collections.searchHistory(collectionName, params),
    queryFn: () => collectionService.getSearchHistory(collectionName, params),
    enabled: !!collectionName,
  });
```

**설계 결정**:
- 검색은 `useMutation`: 동일 쿼리 반복 가능 + 결과 캐시 불필요 + side effect (히스토리 자동 저장)
- 검색 성공 시 히스토리 queryKey 자동 무효화 → 최신 히스토리 반영
- 히스토리는 `useQuery`: 컬렉션명 기반 자동 조회

---

## 7. WeightSlider 컴포넌트 (`src/components/collection/WeightSlider.tsx`)

### Props 인터페이스

```typescript
interface WeightSliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  color?: string;  // 슬라이더 accent 색상 (기본: violet)
}
```

### 렌더링 구조

```tsx
<div className="flex items-center gap-4">
  <label className="w-24 shrink-0 text-[13px] font-medium text-zinc-600">
    {label}
  </label>
  <input
    type="range"
    min={0}
    max={1}
    step={0.1}
    value={value}
    onChange={e => onChange(Number(e.target.value))}
    className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-zinc-200
      accent-violet-600"
  />
  <span className="w-10 text-right text-[13px] font-semibold tabular-nums text-zinc-800">
    {value.toFixed(1)}
  </span>
</div>
```

**설계 결정**:
- native `<input type="range">` 사용 → 외부 라이브러리 불필요
- `accent-violet-600`으로 Tailwind v4 accent-color 적용
- `tabular-nums`로 숫자 표시 고정폭 정렬
- 예상 줄 수: ~25줄

---

## 8. SearchResultCard 컴포넌트 (`src/components/collection/SearchResultCard.tsx`)

### Props 인터페이스

```typescript
interface SearchResultCardProps {
  item: SearchResultItem;
  rank: number;
}
```

### 렌더링 구조

```tsx
<div className="rounded-2xl border border-zinc-200 bg-white p-4 transition-all
  duration-200 hover:border-zinc-300 hover:shadow-sm">
  {/* 헤더: 순위 + source 뱃지 + RRF score */}
  <div className="mb-3 flex items-center justify-between">
    <div className="flex items-center gap-2">
      {/* 순위 뱃지 */}
      <span className="flex h-7 w-7 items-center justify-center rounded-lg
        bg-violet-100 text-[12px] font-bold text-violet-700">
        #{rank}
      </span>
      {/* source 뱃지 */}
      <span className={`rounded-md px-2 py-0.5 text-[11px] font-semibold
        ${SEARCH_SOURCE_BADGE[item.source].bg}
        ${SEARCH_SOURCE_BADGE[item.source].color}`}>
        {SEARCH_SOURCE_BADGE[item.source].label}
      </span>
    </div>
    {/* RRF Score */}
    <span className="text-[12px] font-medium text-zinc-500">
      Score: <span className="text-zinc-800">{item.score.toFixed(4)}</span>
    </span>
  </div>

  {/* 점수 상세 (BM25 / Vector) */}
  <div className="mb-3 flex gap-4 text-[12px] text-zinc-500">
    {item.bm25_rank !== null && (
      <span>
        BM25: rank #{item.bm25_rank}
        {item.bm25_score !== null && `, score ${item.bm25_score.toFixed(2)}`}
      </span>
    )}
    {item.vector_rank !== null && (
      <span>
        Vector: rank #{item.vector_rank}
        {item.vector_score !== null && `, score ${item.vector_score.toFixed(4)}`}
      </span>
    )}
  </div>

  {/* 구분선 */}
  <div className="mb-3 border-t border-zinc-100" />

  {/* 청크 내용 (접기/펼치기) */}
  <ContentPreview content={item.content} />

  {/* 메타데이터 (document_id) */}
  {item.metadata?.document_id && (
    <div className="mt-2 flex items-center gap-1.5 text-[11px] text-zinc-400">
      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={1.5}
        stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125
            1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25
            0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125
            1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
      </svg>
      <span className="font-mono">{String(item.metadata.document_id).slice(0, 12)}...</span>
    </div>
  )}
</div>
```

### ContentPreview (카드 내부에 인라인 구현)

```typescript
const [expanded, setExpanded] = useState(false);
const MAX_LINES = 3;
const shouldTruncate = item.content.split('\n').length > MAX_LINES
  || item.content.length > 200;
```

```tsx
<div>
  <p className={`whitespace-pre-wrap text-[13.5px] leading-relaxed text-zinc-700
    ${!expanded && shouldTruncate ? 'line-clamp-3' : ''}`}>
    {item.content}
  </p>
  {shouldTruncate && (
    <button
      onClick={() => setExpanded(!expanded)}
      className="mt-1 text-[12px] font-medium text-violet-500 hover:text-violet-700
        transition-colors"
    >
      {expanded ? '접기' : '더보기'}
    </button>
  )}
</div>
```

**설계 결정**:
- `line-clamp-3` Tailwind 유틸리티로 기본 3줄 표시
- BM25/Vector rank가 null이면 해당 줄 숨김 (source가 한쪽만인 경우)
- 예상 줄 수: ~100줄

---

## 9. SearchResultList 컴포넌트 (`src/components/collection/SearchResultList.tsx`)

### Props 인터페이스

```typescript
interface SearchResultListProps {
  results: SearchResultItem[] | undefined;
  isLoading: boolean;
  isError: boolean;
  totalFound: number;
  bm25Weight: number;
  vectorWeight: number;
}
```

### 렌더링 구조 (상태별)

```tsx
<div className="mt-6 space-y-4">
  {/* 로딩 */}
  {isLoading && (
    <div className="flex flex-col items-center py-12">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-zinc-200"
        style={{ borderTopColor: '#7c3aed' }} />
      <p className="mt-3 text-[13px] text-zinc-400">검색 중...</p>
    </div>
  )}

  {/* 에러 */}
  {isError && (
    <div className="rounded-2xl border border-red-200 bg-red-50/50 px-5 py-8 text-center">
      <p className="text-[14px] font-medium text-red-600">검색 중 오류가 발생했습니다</p>
      <p className="mt-1 text-[12px] text-red-400">잠시 후 다시 시도해주세요</p>
    </div>
  )}

  {/* 결과 0건 */}
  {!isLoading && !isError && results && results.length === 0 && (
    <div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-5 py-8 text-center">
      <p className="text-[14px] font-medium text-zinc-500">검색 결과가 없습니다</p>
      <p className="mt-1 text-[12px] text-zinc-400">다른 쿼리나 가중치를 시도해보세요</p>
    </div>
  )}

  {/* 결과 있음 */}
  {!isLoading && !isError && results && results.length > 0 && (
    <>
      {/* 결과 요약 */}
      <div className="flex items-center justify-between">
        <p className="text-[13px] text-zinc-500">
          총 <span className="font-semibold text-zinc-800">{totalFound}</span>건
        </p>
        <p className="text-[12px] text-zinc-400">
          BM25: {bm25Weight} / Vector: {vectorWeight}
        </p>
      </div>

      {/* 결과 카드 */}
      {results.map((item, idx) => (
        <SearchResultCard key={item.id} item={item} rank={idx + 1} />
      ))}
    </>
  )}
</div>
```

**설계 결정**:
- 초기 상태 (검색 전): 아무것도 표시하지 않음 (`results === undefined`)
- 결과 요약에 적용된 가중치 표시 → 어떤 설정의 결과인지 명확
- 예상 줄 수: ~60줄

---

## 10. SearchHistoryPanel 컴포넌트 (`src/components/collection/SearchHistoryPanel.tsx`)

### Props 인터페이스

```typescript
interface SearchHistoryPanelProps {
  collectionName: string;
  onApply: (params: {
    query: string;
    topK: number;
    bm25Weight: number;
    vectorWeight: number;
  }) => void;
}
```

### 내부 상태

```typescript
const [isOpen, setIsOpen] = useState(false);
const historyQuery = useSearchHistory(collectionName, { limit: 10 });
const histories = historyQuery.data?.histories ?? [];
```

### 렌더링 구조

```tsx
<div className="mt-4">
  {/* 토글 버튼 */}
  <button
    onClick={() => setIsOpen(!isOpen)}
    className="flex items-center gap-1.5 text-[13px] font-medium text-zinc-500
      hover:text-zinc-700 transition-colors"
  >
    <svg className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-90' : ''}`}
      fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
    </svg>
    검색 히스토리
    {historyQuery.data && (
      <span className="rounded-full bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-500">
        {historyQuery.data.total}
      </span>
    )}
  </button>

  {/* 히스토리 테이블 */}
  {isOpen && (
    <div className="mt-3 overflow-hidden rounded-xl border border-zinc-200">
      {historyQuery.isLoading && (
        <div className="px-4 py-6 text-center text-[13px] text-zinc-400">
          로딩 중...
        </div>
      )}

      {!historyQuery.isLoading && histories.length === 0 && (
        <div className="px-4 py-6 text-center text-[13px] text-zinc-400">
          검색 히스토리가 없습니다
        </div>
      )}

      {histories.length > 0 && (
        <table className="w-full text-[12.5px]">
          <thead>
            <tr className="border-b border-zinc-100 bg-zinc-50">
              <th className="px-3 py-2 text-left font-medium text-zinc-500">쿼리</th>
              <th className="px-3 py-2 text-center font-medium text-zinc-500">BM25</th>
              <th className="px-3 py-2 text-center font-medium text-zinc-500">Vector</th>
              <th className="px-3 py-2 text-center font-medium text-zinc-500">Top K</th>
              <th className="px-3 py-2 text-center font-medium text-zinc-500">결과</th>
              <th className="px-3 py-2 text-right font-medium text-zinc-500">시간</th>
            </tr>
          </thead>
          <tbody>
            {histories.map((h) => (
              <tr
                key={h.id}
                onClick={() => onApply({
                  query: h.query,
                  topK: h.top_k,
                  bm25Weight: h.bm25_weight,
                  vectorWeight: h.vector_weight,
                })}
                className="cursor-pointer border-b border-zinc-50 transition-colors
                  hover:bg-violet-50/50"
              >
                <td className="max-w-[200px] truncate px-3 py-2.5 text-zinc-700">
                  {h.query}
                </td>
                <td className="px-3 py-2.5 text-center text-zinc-500">
                  {h.bm25_weight}
                </td>
                <td className="px-3 py-2.5 text-center text-zinc-500">
                  {h.vector_weight}
                </td>
                <td className="px-3 py-2.5 text-center text-zinc-500">
                  {h.top_k}
                </td>
                <td className="px-3 py-2.5 text-center text-zinc-500">
                  {h.result_count}건
                </td>
                <td className="px-3 py-2.5 text-right text-zinc-400">
                  {formatRelativeTime(h.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )}
</div>
```

### formatRelativeTime 유틸 (컴포넌트 내부 인라인)

```typescript
const formatRelativeTime = (isoDate: string): string => {
  const diff = Date.now() - new Date(isoDate).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return '방금 전';
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  return `${days}일 전`;
};
```

**설계 결정**:
- 기본 숨김 → 토글 방식으로 UI 부담 최소화
- 행 클릭 시 `onApply` 호출 → 검색 설정 자동 채우기 (재검색 편의)
- limit=10 기본 (최근 10건만)
- 예상 줄 수: ~120줄

---

## 11. HybridSearchPanel 컴포넌트 (`src/components/collection/HybridSearchPanel.tsx`)

### Props 인터페이스

```typescript
interface HybridSearchPanelProps {
  bm25Weight: number;
  vectorWeight: number;
  topK: number;
  onBm25WeightChange: (value: number) => void;
  onVectorWeightChange: (value: number) => void;
  onTopKChange: (value: number) => void;
}
```

### 상수

```typescript
const TOP_K_OPTIONS = [3, 5, 10, 20] as const;
```

### 렌더링 구조

```tsx
<div className="space-y-4 rounded-xl border border-zinc-200 bg-zinc-50/50 p-4">
  {/* Top K 선택 */}
  <div className="flex items-center gap-4">
    <label className="w-24 shrink-0 text-[13px] font-medium text-zinc-600">
      결과 수
    </label>
    <div className="flex items-center gap-1">
      {TOP_K_OPTIONS.map((k) => (
        <button
          key={k}
          onClick={() => onTopKChange(k)}
          className={`rounded-lg px-3 py-1.5 text-[12.5px] font-medium transition-all ${
            topK === k
              ? 'bg-violet-600 text-white shadow-sm'
              : 'text-zinc-500 hover:bg-zinc-200 hover:text-zinc-700'
          }`}
        >
          Top {k}
        </button>
      ))}
    </div>
  </div>

  {/* BM25 가중치 슬라이더 */}
  <WeightSlider
    label="BM25 가중치"
    value={bm25Weight}
    onChange={onBm25WeightChange}
  />

  {/* 벡터 가중치 슬라이더 */}
  <WeightSlider
    label="벡터 가중치"
    value={vectorWeight}
    onChange={onVectorWeightChange}
  />

  {/* 프리셋 버튼 */}
  <div className="flex items-center gap-2">
    <span className="text-[12px] text-zinc-400">프리셋:</span>
    {Object.entries(WEIGHT_PRESETS).map(([key, preset]) => (
      <button
        key={key}
        onClick={() => {
          onBm25WeightChange(preset.bm25_weight);
          onVectorWeightChange(preset.vector_weight);
        }}
        className={`rounded-lg border px-2.5 py-1 text-[11.5px] font-medium transition-all ${
          bm25Weight === preset.bm25_weight && vectorWeight === preset.vector_weight
            ? 'border-violet-300 bg-violet-50 text-violet-600'
            : 'border-zinc-200 bg-white text-zinc-500 hover:border-zinc-300 hover:bg-zinc-50'
        }`}
      >
        {preset.label}
      </button>
    ))}
  </div>
</div>
```

**설계 결정**:
- 프리셋 버튼은 현재 가중치와 일치하면 활성 스타일 표시
- Top K 옵션 기존 3/5/10에 20 추가
- 예상 줄 수: ~80줄

---

## 12. 페이지 통합 (`CollectionDocumentsPage/index.tsx`)

### 변경 사항

#### 추가 import

```typescript
import { useCollectionSearch } from '@/hooks/useCollections';
import HybridSearchPanel from '@/components/collection/HybridSearchPanel';
import SearchResultList from '@/components/collection/SearchResultList';
import SearchHistoryPanel from '@/components/collection/SearchHistoryPanel';
import type { CollectionSearchResponse } from '@/types/collection';
```

#### 상태 변경

```typescript
// 기존 유지
const [searchQuery, setSearchQuery] = useState('');
const [topK, setTopK] = useState<number>(5);

// 신규 추가
const [bm25Weight, setBm25Weight] = useState(0.5);
const [vectorWeight, setVectorWeight] = useState(0.5);
const [searchResult, setSearchResult] = useState<CollectionSearchResponse | null>(null);

const searchMutation = useCollectionSearch();
```

#### 기존 상수 제거

```typescript
// 삭제: const TOP_K_OPTIONS = [3, 5, 10] as const;
// 삭제: const EXAMPLE_QUERIES = [...];
// EXAMPLE_QUERIES는 유지 (예시 쿼리 칩에 사용)
```

> `TOP_K_OPTIONS`는 `HybridSearchPanel` 내부로 이동.
> `EXAMPLE_QUERIES`는 페이지에서 계속 사용하므로 유지.

#### handleSearch 교체

```typescript
const handleSearch = () => {
  if (!searchQuery.trim() || !collectionName) return;
  searchMutation.mutate(
    {
      collectionName,
      data: {
        query: searchQuery.trim(),
        top_k: topK,
        bm25_weight: bm25Weight,
        vector_weight: vectorWeight,
      },
    },
    {
      onSuccess: (data) => setSearchResult(data),
    },
  );
};
```

#### handleHistoryApply 추가

```typescript
const handleHistoryApply = (params: {
  query: string;
  topK: number;
  bm25Weight: number;
  vectorWeight: number;
}) => {
  setSearchQuery(params.query);
  setTopK(params.topK);
  setBm25Weight(params.bm25Weight);
  setVectorWeight(params.vectorWeight);
};
```

#### JSX 변경 — "벡터 검색 테스트" 섹션 교체

기존 "벡터 검색 테스트" `<div>` 전체를 아래로 교체:

```tsx
{/* Hybrid Search Section */}
<div className="mt-8 rounded-2xl border border-zinc-200 bg-white p-6">
  {/* 섹션 헤더 */}
  <div className="mb-4 flex items-center gap-3">
    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-100">
      <svg className="h-5 w-5 text-violet-600" fill="none" viewBox="0 0 24 24"
        strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round"
          d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5
            7.5 0 0 0 10.607 10.607Z" />
      </svg>
    </div>
    <div>
      <h3 className="text-[15px] font-semibold text-zinc-900">하이브리드 검색</h3>
      <p className="text-[12px] text-zinc-400">
        BM25 + 벡터 검색을 조합하여 최적의 검색 결과를 확인합니다
      </p>
    </div>
  </div>

  {/* 검색 입력 + 버튼 */}
  <div className="flex gap-3">
    <div className="flex-1 overflow-hidden rounded-2xl border border-zinc-300 bg-white
      shadow-sm transition-all focus-within:border-violet-400
      focus-within:shadow-violet-100/60">
      <div className="flex items-center px-4">
        <svg className="h-4 w-4 shrink-0 text-zinc-400" fill="none"
          viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round"
            d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5
              7.5 0 0 0 10.607 10.607Z" />
        </svg>
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="검색 쿼리를 입력하세요 (예: 임베딩 벡터 검색 방법)"
          className="block w-full bg-transparent px-3 py-3 text-[14px] text-zinc-900
            placeholder-zinc-400 outline-none"
        />
      </div>
    </div>

    <button
      onClick={handleSearch}
      disabled={!searchQuery.trim() || searchMutation.isPending}
      className={`flex items-center gap-2 rounded-2xl px-5 text-[13.5px] font-medium
        shadow-sm transition-all active:scale-95 ${
        searchQuery.trim() && !searchMutation.isPending
          ? 'bg-violet-600 text-white hover:bg-violet-700'
          : 'cursor-not-allowed bg-zinc-200 text-zinc-400'
      }`}
    >
      {searchMutation.isPending ? (
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30
          border-t-white" />
      ) : (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2}
          stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round"
            d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5
              7.5 0 0 0 10.607 10.607Z" />
        </svg>
      )}
      검색
    </button>
  </div>

  {/* 예시 쿼리 */}
  <div className="mt-3 flex items-center gap-2">
    <span className="text-[12px] text-zinc-400">예시:</span>
    {EXAMPLE_QUERIES.map((q) => (
      <button
        key={q}
        onClick={() => setSearchQuery(q)}
        className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1 text-[12px]
          text-zinc-500 transition-all hover:border-zinc-300 hover:bg-zinc-100
          hover:text-zinc-700"
      >
        {q}
      </button>
    ))}
  </div>

  {/* 검색 옵션 패널 */}
  <div className="mt-4">
    <HybridSearchPanel
      bm25Weight={bm25Weight}
      vectorWeight={vectorWeight}
      topK={topK}
      onBm25WeightChange={setBm25Weight}
      onVectorWeightChange={setVectorWeight}
      onTopKChange={setTopK}
    />
  </div>

  {/* 검색 결과 */}
  {(searchResult || searchMutation.isPending || searchMutation.isError) && (
    <SearchResultList
      results={searchResult?.results}
      isLoading={searchMutation.isPending}
      isError={searchMutation.isError}
      totalFound={searchResult?.total_found ?? 0}
      bm25Weight={searchResult?.bm25_weight ?? bm25Weight}
      vectorWeight={searchResult?.vector_weight ?? vectorWeight}
    />
  )}

  {/* 검색 히스토리 */}
  <SearchHistoryPanel
    collectionName={collectionName}
    onApply={handleHistoryApply}
  />
</div>
```

---

## 13. 파일 의존성 그래프

```
src/types/collection.ts (수정: 검색 타입 추가)
  ← src/services/collectionService.ts (수정: searchCollection, getSearchHistory)
       ← src/hooks/useCollections.ts (수정: useCollectionSearch, useSearchHistory)
            ← src/pages/CollectionDocumentsPage/index.tsx (수정: 검색 섹션 교체)

src/constants/api.ts (수정: COLLECTION_SEARCH, COLLECTION_SEARCH_HISTORY)
  ← src/services/collectionService.ts

src/lib/queryKeys.ts (수정: searchHistory 키)
  ← src/hooks/useCollections.ts

src/components/collection/WeightSlider.tsx (신규)
  ← src/components/collection/HybridSearchPanel.tsx (신규)
       ← src/pages/CollectionDocumentsPage/index.tsx

src/components/collection/SearchResultCard.tsx (신규)
  ← src/components/collection/SearchResultList.tsx (신규)
       ← src/pages/CollectionDocumentsPage/index.tsx

src/components/collection/SearchHistoryPanel.tsx (신규)
  ← src/pages/CollectionDocumentsPage/index.tsx
```

---

## 14. 컴포넌트 규모 예상

| 파일 | 작업 | 예상 줄 수 | 비고 |
|------|------|-----------|------|
| `collection.ts` | 수정 | +55 | 타입/상수 추가 |
| `api.ts` | 수정 | +4 | 엔드포인트 2개 |
| `queryKeys.ts` | 수정 | +3 | searchHistory 키 |
| `collectionService.ts` | 수정 | +20 | 메서드 2개 |
| `useCollections.ts` | 수정 | +25 | 훅 2개 |
| `WeightSlider.tsx` | 신규 | ~25 | 단일 슬라이더 |
| `SearchResultCard.tsx` | 신규 | ~100 | 결과 카드 + 접기/펼치기 |
| `SearchResultList.tsx` | 신규 | ~60 | 상태별 분기 |
| `SearchHistoryPanel.tsx` | 신규 | ~120 | 테이블 + 토글 |
| `HybridSearchPanel.tsx` | 신규 | ~80 | 슬라이더 + 프리셋 + Top K |
| `CollectionDocumentsPage` | 수정 | ~±30 | 기존 검색 섹션 교체 |

> 모든 컴포넌트가 200줄 이하. 분리 필요 없음.
