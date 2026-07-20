/**
 * 지식베이스 관리 화면 전용 타입 (kb-management-ui Design §5.1)
 *
 * KnowledgeBaseInfo는 kb-rag-filter 산출물로 types/ragToolConfig.ts에
 * 그대로 두고(D5 — import 경로 무회귀), 여기서는 관리 화면 계약만 정의한다.
 * 백엔드 계약: src/api/routes/knowledge_base_router.py
 */
import type { CollectionScope } from '@/types/ragToolConfig';

// ── 커스텀 청킹 (kb-custom-chunking Design §4.1) ─────────────────
// 백엔드 계약: src/domain/knowledge_base/custom_chunking.py

export type ChunkingStrategy =
  | 'full_token'
  | 'parent_child'
  | 'semantic'
  | 'section_aware'
  | 'boundary_pattern';

export interface CustomBoundaryRule {
  pattern: string;
  priority: number;
  level: 'parent' | 'child';
}

export interface CustomChunkingConfig {
  version: 1;
  strategy: ChunkingStrategy;
  chunk_size: number;
  chunk_overlap: number;
  parent_chunk_size?: number | null;
  min_chunk_size?: number | null;
  boundary_rules?: CustomBoundaryRule[];
}

/** PATCH /knowledge-bases/{kbId}/chunking — 전체 교체 시맨틱 (D7) */
export interface UpdateKbChunkingRequest {
  use_clause_chunking: boolean;
  chunking_profile_id?: string | null;
  chunk_size?: number | null;
  chunk_overlap?: number | null;
  use_custom_chunking: boolean;
  custom_chunking_config?: CustomChunkingConfig | null;
}

export interface CreateKnowledgeBaseRequest {
  name: string;
  description?: string | null;
  scope: CollectionScope;
  department_id?: string | null;
  collection_name: string;
  use_clause_chunking?: boolean;
  // kb-custom-chunking (D1): 독립 opt-in — 조항 청킹과 상호배타
  use_custom_chunking?: boolean;
  custom_chunking_config?: CustomChunkingConfig | null;
}

export interface KbCreateResponse {
  kb_id: string;
  name: string;
  scope: string;
  collection_name: string;
  message: string;
}

export interface KbMessageResponse {
  kb_id: string;
  message: string;
}

export interface KbDocumentInfo {
  document_id: string;
  filename: string;
  chunk_count: number;
  chunking_strategy: string;
  created_at: string | null;
}

export interface KbDocumentListResponse {
  kb_id: string;
  kb_name: string;
  documents: KbDocumentInfo[];
  total: number;
  offset: number;
  limit: number;
}

export interface KbStoreResult {
  status: string;
  error?: string | null;
}

export interface KbSectionSummaryLaunch {
  job_id: string;
  status: string;
}

export interface KbUploadResponse {
  kb_id: string;
  kb_name: string;
  collection_name: string;
  document_id: string;
  filename: string;
  total_pages: number;
  chunk_count: number;
  chunking_strategy: string;
  qdrant: KbStoreResult;
  es: KbStoreResult;
  status: string;
  section_summary?: KbSectionSummaryLaunch | null;
}

// scope 배지 라벨/스타일은 컬렉션 화면과 동일한
// `SCOPE_LABELS`(@/types/collection)를 재사용한다 (Check Gap 1).

// ── KB 저장 내용 조회 (kb-content-browser Design §5.1) ──────────
// 백엔드 계약: knowledge_base_router.py Kb*Response

export type KbStoreSource = 'qdrant' | 'es';

export interface KbBrowseChunkDetail {
  chunk_id: string;
  chunk_index: number;
  chunk_type: string;
  content: string;
  metadata: Record<string, string>;
}

export interface KbBrowseParentGroup {
  chunk_id: string;
  chunk_index: number;
  chunk_type: string;
  content: string;
  children: KbBrowseChunkDetail[];
}

export interface KbDocumentSummaryResponse {
  exists: boolean;
  source: KbStoreSource;
  chunk_id?: string | null;
  summary_text?: string | null;
  keywords: string[];
  section_count?: number | null;
  filename?: string | null;
  metadata: Record<string, string>;
}

export interface KbSectionSummaryItem {
  chunk_id: string;
  section_ref: string;
  clause_title: string;
  chunk_index: number;
  summary_text: string;
  keywords: string[];
  metadata: Record<string, string>;
}

export interface KbSectionSummaryListResponse {
  source: KbStoreSource;
  document_id: string;
  total: number;
  items: KbSectionSummaryItem[];
}

export interface KbDocumentChunksResponse {
  source: KbStoreSource;
  search_mode: 'match' | 'contains' | null;
  document_id: string;
  filename: string;
  chunk_strategy: string;
  total_chunks: number;
  chunks: KbBrowseChunkDetail[];
  parents: KbBrowseParentGroup[] | null;
}

export interface KbDocumentChunksParams {
  source: KbStoreSource;
  include_parent?: boolean;
  q?: string;
}

// ── KB 리트리버 테스트 (kb-retrieval-test Design §3.2) ──────────
// 백엔드 계약: knowledge_base_router.py KbSearch*
// 결과/히스토리 항목은 컬렉션 검색과 동일 형태 — 타입 재사용

import type { SearchHistoryItem, SearchResultItem } from '@/types/collection';

export interface KbSearchRequest {
  query: string;
  top_k?: number;
  bm25_weight?: number;
  vector_weight?: number;
  bm25_top_k?: number;
  vector_top_k?: number;
  rrf_k?: number;
  /** D4: 문서 단위 검색 — KB 소속 아니면 404 */
  document_id?: string;
}

export interface KbSearchResponse {
  query: string;
  kb_id: string;
  kb_name: string;
  collection_name: string;
  results: SearchResultItem[];
  total_found: number;
  bm25_weight: number;
  vector_weight: number;
  request_id: string;
  document_id: string | null;
}

export interface KbSearchHistoryResponse {
  kb_id: string;
  histories: SearchHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

/** 섹션 요약 잡 상태 — 기존 백엔드 API의 첫 프론트 연동 (Design D9) */
export interface SectionSummaryStatusResponse {
  job_id: string;
  document_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | string;
  total_sections: number | null;
  done_sections: number;
  failed_sections: number;
  is_stale: boolean;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}
