# Gap Analysis: hybrid-search-ui

> Design: `docs/02-design/features/hybrid-search-ui.design.md`
> Analysis Date: 2026-04-28

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 98% | PASS |
| Architecture Compliance | 100% | PASS |
| Convention Compliance | 100% | PASS |
| **Overall** | **99%** | **PASS** |

---

## Step-by-Step Analysis

### Step 1: `src/types/collection.ts` — Type Definitions
**MATCH** — All 9 items (types, interfaces, constants) are character-for-character identical.

### Step 2: `src/constants/api.ts` — Endpoint Constants
**MATCH** — `COLLECTION_SEARCH`, `COLLECTION_SEARCH_HISTORY` both present and correct.

### Step 3: `src/lib/queryKeys.ts` — Query Keys
**MATCH** — `searchHistory` key correctly placed in `collections` namespace.

### Step 4: `src/services/collectionService.ts` — Service Methods
**MATCH** — `searchCollection` (POST, authApiClient), `getSearchHistory` (GET, authApiClient) both correct.

### Step 5: `src/hooks/useCollections.ts` — Custom Hooks
**MATCH** — `useCollectionSearch` (useMutation + onSuccess invalidation), `useSearchHistory` (useQuery + enabled guard) both correct.

### Step 6: `src/components/collection/WeightSlider.tsx`
**MINOR GAP** — Optional `color?: string` prop from design is omitted. No functional impact (default `accent-violet-600` correctly hardcoded, prop unused by consumers).

### Step 7: `src/components/collection/SearchResultCard.tsx`
**MATCH** — All elements present: rank badge, source badge, RRF score, BM25/Vector rank details, expandable content, metadata display. Cosmetic difference: uses ternary `? : null` instead of `&&` for metadata rendering (functionally identical).

### Step 8: `src/components/collection/SearchResultList.tsx`
**MATCH** — All 4 states (loading, error, empty, results) correctly implemented with design-specified styling.

### Step 9: `src/components/collection/SearchHistoryPanel.tsx`
**MATCH** — Toggle button, total count badge, 6-column table, row click handler, `formatRelativeTime` utility all correct.

### Step 10: `src/components/collection/HybridSearchPanel.tsx`
**MATCH** — Top K selector (3/5/10/20), WeightSliders, preset buttons with active detection all correct.

### Step 11: `src/pages/CollectionDocumentsPage/index.tsx` — Page Integration
**MATCH** — All imports, state variables, handlers, and JSX structure match design spec.

---

## Gaps Found

| # | Item | Design | Implementation | Impact |
|---|------|--------|----------------|--------|
| 1 | `WeightSlider.color` prop | `color?: string` (optional) | Omitted | Low — optional, unused |

## Architecture Compliance

| Check | Status |
|-------|--------|
| Service layer uses `authApiClient` | PASS |
| Query keys in centralized factory | PASS |
| Endpoints in `constants/api.ts` | PASS |
| Types in `types/` directory | PASS |
| useMutation for search (design decision) | PASS |
| useQuery for history (design decision) | PASS |
| Search success auto-invalidates history | PASS |

## Convention Compliance

| Check | Status |
|-------|--------|
| Response types: `XxxResponse` suffix | PASS |
| Request types: `XxxRequest` suffix | PASS |
| Domain models: no suffix | PASS |
| Arrow function components | PASS |
| Props as `interface` at file top | PASS |
| `export default` at file bottom | PASS |
| Absolute imports (`@/...`) | PASS |

---

## Recommendation

Match Rate **99%** — exceeds 90% threshold. No action required.
The single missing optional prop (`color?: string`) can be added if color customization is needed in the future.

**Next Step**: `/pdca report hybrid-search-ui`
