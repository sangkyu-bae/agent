# RAG-001 — 문서(RAG) 기능

## 상태: 진행 중

## 완료된 작업

### UI 구현
- [x] `DocumentPage/index.tsx` — 문서 관리 페이지 (업로드, 목록, 통계, 청크 뷰어 연동)
- [x] `components/rag/DocumentList.tsx` — 문서 목록 (선택/삭제)
- [x] `components/rag/ChunkViewer.tsx` — 청킹 결과 그리드 뷰
  - [x] 청크 카드 클릭 시 메타데이터 모달 표시 (`ChunkMetaModal`)
  - [x] 시스템 정보 (Chunk ID, Document ID, Index, Token Count) 표시
  - [x] 추가 메타데이터 (`metadata?: Record<string, unknown>`) 동적 표시
  - [x] 내용 전문 스크롤 표시
- [x] `hooks/useDocuments.ts` — TanStack Query 훅 (목록/청크/업로드/삭제/벡터검색)

### 벡터 검색 테스트 패널 (Mock)
- [x] `components/rag/VectorSearchPanel.tsx` — 벡터 검색 테스트 UI
  - [x] `ScoreBadge` — 유사도 점수 색상 배지 (≥0.80 초록, ≥0.60 주황, 미만 빨강)
  - [x] `ResultCard` — 검색 결과 카드 (랭크, 문서명, 청크 인덱스, 내용 하이라이트, 유사도 바)
  - [x] `highlightQuery()` — 쿼리 키워드 `<mark>` 하이라이트
  - [x] TopK 선택기 — [3, 5, 10] 버튼 그룹
  - [x] 힌트 쿼리 칩 — '임베딩 벡터 생성', '청킹 전략', 'API 엔드포인트', '재랭킹'
  - [x] Mock 배지 표시
- [x] `hooks/useDocuments.ts` — `useVectorSearch()` useMutation 훅 추가
  - Mock: `getMockVectorSearch(query, topK)` (키워드 매칭 점수 시뮬레이션, 500~900ms 지연)
  - 실제: `ragService.retrieve({ query, topK, documentIds })` (VITE_USE_MOCK=false 시)
- [x] `mocks/documentMocks.ts` — `getMockVectorSearch()`, `simulateScore()` 추가
  - 점수 공식: base 0.5 + (키워드 히트 / 전체) × 0.45 + 랜덤 노이즈 ±0.03
- [x] `lib/queryKeys.ts` — `documents.vectorSearch(query, topK)` 키 추가
- [x] `DocumentPage/index.tsx` — `<VectorSearchPanel />` 청크 뷰어 아래 통합

### 타입
- [x] `types/rag.ts` — `DocumentChunk.metadata?: Record<string, unknown>` 추가

## 진행 예정 작업

### API 연동
- [ ] `components/rag/DocumentUploader.tsx` — 드래그앤드롭 파일 업로드 컴포넌트
- [ ] `components/rag/RetrievedChunks.tsx` — 검색된 청크 상세 보기 (RAG 검색 결과)
- [ ] 실제 백엔드 API 연동 (현재 Mock)
  - `VectorSearchPanel`: `VITE_USE_MOCK=false` 시 `ragService.retrieve()` 자동 호출
