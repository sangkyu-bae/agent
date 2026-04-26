# collection-document-chunks Gap Analysis

> **Feature**: 컬렉션별 문서 목록 및 청크 상세 조회 UI
> **Date**: 2026-04-23
> **Design Doc**: `docs/02-design/features/collection-document-chunks.design.md`
> **Match Rate**: 97%

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 95% | PASS |
| Architecture Compliance | 100% | PASS |
| Convention Compliance | 98% | PASS |
| **Overall** | **97%** | **PASS** |

---

## Implementation Step Verification (13/13 Steps)

| # | Step | File | Status |
|---|------|------|:------:|
| 1 | Domain types (9 interfaces/types + 2 badge constants) | `src/types/collection.ts` | MATCH |
| 2 | API endpoint constants | `src/constants/api.ts` | MATCH |
| 3 | Query keys (documents, chunks) | `src/lib/queryKeys.ts` | MATCH |
| 4 | Service methods (getDocuments, getDocumentChunks) | `src/services/collectionService.ts` | MATCH |
| 5 | Hooks (useCollectionDocuments, useDocumentChunks) | `src/hooks/useCollections.ts` | MATCH |
| 6 | MSW handlers + hook tests (7 cases: D1-D7) | `handlers.ts`, `useCollections.test.ts` | MATCH |
| 7 | DocumentTable component | `src/components/collection/DocumentTable.tsx` | MATCH |
| 8 | ChunkDetailPanel component | `src/components/collection/ChunkDetailPanel.tsx` | MATCH |
| 9 | ParentChildTree component | `src/components/collection/ParentChildTree.tsx` | MATCH |
| 10 | CollectionDocumentsPage page | `src/pages/CollectionDocumentsPage/index.tsx` | MATCH |
| 11 | CollectionTable navigation (click → navigate) | `src/components/collection/CollectionTable.tsx` | MATCH |
| 12 | App.tsx routing + /documents redirect | `src/App.tsx` | MATCH |
| 13 | TopNav "문서 관리" 메뉴 제거 | `src/components/layout/TopNav.tsx` | MATCH |

---

## Gaps Found

### [RED] Functional Gaps

| # | Item | Design Section | Description | Impact |
|---|------|---------------|-------------|--------|
| G1 | Hierarchy toggle ↔ include_parent 미연결 | 2.2 step 4, 5.2 | ChunkDetailPanel의 `showHierarchy` 로컬 상태가 페이지 레벨 `includeParent`를 업데이트하지 않음. 토글 시 `include_parent=true`로 API 재요청이 발생하지 않아 `parents` 데이터가 null일 수 있음 | Medium |

### [YELLOW] Missing Tests

| # | Item | Design Section | Description | Impact |
|---|------|---------------|-------------|--------|
| G2 | DocumentTable 컴포넌트 테스트 | 8.1, 8.2 | RTL 단위 테스트 미작성 | Low |
| G3 | ChunkDetailPanel 컴포넌트 테스트 | 8.1, 8.2 | RTL 단위 테스트 미작성 | Low |
| G4 | ParentChildTree 컴포넌트 테스트 | 8.1, 8.2 | RTL 단위 테스트 미작성 | Low |
| G5 | CollectionDocumentsPage 통합 테스트 | 8.1 | 전체 흐름 통합 테스트 미작성 | Low |

### [BLUE] Minor Style Deviations

| # | Item | Design | Implementation |
|---|------|--------|----------------|
| S1 | Accordion header font | `text-[13.5px] text-zinc-800` | `text-[13px] text-zinc-700` |
| S2 | CollectionTable link extra style | `text-violet-600 hover:underline` | `+ hover:text-violet-800 transition-colors` |

---

## Recommended Fix Priority

1. **G1 (Medium)**: hierarchy toggle → include_parent API 재요청 연결
2. **G2-G5 (Low)**: 컴포넌트/통합 테스트 추가 (훅 테스트 7개는 완료)
3. **S1-S2 (Low)**: 스타일 미세 조정 (기능에 영향 없음)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-04-23 | Initial gap analysis — 97% match rate |
