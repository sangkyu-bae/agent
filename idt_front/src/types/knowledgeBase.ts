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
  // kb-profile-selector: null = 기본 프로파일 따름 (late-binding)
  chunking_profile_id?: string | null;
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
  /** 서버가 KB 정책으로 계산한 삭제 가능 여부 (kb-document-management FR-08) */
  can_delete: boolean;
  // document-revision §4.2 #3 — 목록은 active 만, 버전 표시용.
  // 서버는 항상 내려주지만 이전 응답 형태와 호환되도록 선택 필드로 둔다(미존재 = v1·active).
  version_no?: number;
  version_label?: string | null;
  effective_date?: string | null;
  revision_status?: RevisionStatus;
  sync_state?: SyncState;
  lineage_id?: string | null;
  has_history?: boolean;
}

/** DELETE /knowledge-bases/{kbId}/documents/{docId} (kb-document-management §4.2) */
export interface KbDocumentDeleteResponse {
  kb_id: string;
  document_id: string;
  filename: string;
  deleted_qdrant_chunks: number;
  deleted_es_chunks: number;
  status: string;
  /** document-revision §4.2 #9 — 최신 버전 삭제로 다시 검색에 쓰이게 된 이전 버전 */
  restored_document_id?: string | null;
}

export interface KbDocumentListResponse {
  kb_id: string;
  kb_name: string;
  documents: KbDocumentInfo[];
  total: number;
  offset: number;
  limit: number;
  /** document-revision §4.2 #3 — 검색 제외 표식 반영 실패(재시도 대상) */
  pending_sync?: DocumentVersion[];
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
  /** document-revision §4.2 #2 — 개정 적용 결과 */
  revision?: RevisionApplyResult | null;
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

// ── 문서 개정 (document-revision Design §3.1·§4.2) ──────────────
// 백엔드 계약: src/interfaces/schemas/document_revision.py, kb_document_revision_router.py

export const REVISION_STATUS = { ACTIVE: 'active', SUPERSEDED: 'superseded' } as const;
export type RevisionStatus = (typeof REVISION_STATUS)[keyof typeof REVISION_STATUS];

export const SYNC_STATE = { SYNCED: 'synced', PENDING: 'pending' } as const;
export type SyncState = (typeof SYNC_STATE)[keyof typeof SYNC_STATE];

export const CHECK_VERDICT = {
  NEW: 'new',
  REVISION_CANDIDATE: 'revision_candidate',
  DUPLICATE: 'duplicate',
} as const;
export type CheckVerdict = (typeof CHECK_VERDICT)[keyof typeof CHECK_VERDICT];

export const LLM_VERDICT = {
  SAME: 'same_document_revision',
  DIFFERENT: 'different_document',
  UNCERTAIN: 'uncertain',
} as const;
export type LlmVerdict = (typeof LLM_VERDICT)[keyof typeof LLM_VERDICT];

export const LLM_STATUS = { OK: 'ok', FAILED: 'failed', SKIPPED: 'skipped' } as const;
export type LlmStatus = (typeof LLM_STATUS)[keyof typeof LLM_STATUS];

export const ROLLBACK_MODE = { DETACH: 'detach', DELETE: 'delete' } as const;
export type RollbackMode = (typeof ROLLBACK_MODE)[keyof typeof ROLLBACK_MODE];

/** 409 detail.code (Design §6.1) */
export const REVISION_ERROR_CODE = {
  DUPLICATE_DOCUMENT: 'DUPLICATE_DOCUMENT',
  REVISION_TARGET_INVALID: 'REVISION_TARGET_INVALID',
  ROLLBACK_NOT_ALLOWED: 'ROLLBACK_NOT_ALLOWED',
  REVISION_LINK_INVALID: 'REVISION_LINK_INVALID',
  REVISION_MODE_NOT_AVAILABLE: 'REVISION_MODE_NOT_AVAILABLE',
} as const;

export interface DocumentVersion {
  document_id: string;
  filename: string;
  lineage_id: string;
  version_no: number;
  version_label: string | null;
  effective_date: string | null;
  revision_status: RevisionStatus;
  sync_state: SyncState;
  superseded_by: string | null;
  superseded_at: string | null;
  revised_by: string | null;
  created_at: string | null;
}

export interface RevisionCandidate {
  document_id: string;
  filename: string;
  version_no: number;
  version_label: string | null;
  filename_score: number;
  content_score: number;
  combined_score: number;
  llm_verdict: LlmVerdict | null;
  llm_reason: string | null;
}

/** POST /knowledge-bases/{kbId}/documents/revision-check */
export interface RevisionCheckResponse {
  check_id: string;
  verdict: CheckVerdict;
  duplicate_of: DocumentVersion | null;
  suggested_document_id: string | null;
  candidates: RevisionCandidate[];
  llm_status: LlmStatus;
  elapsed_ms: number;
}

/** 업로드 요청의 개정 입력 (모두 선택) */
export interface RevisionUploadOptions {
  supersedesDocumentId?: string | null;
  versionLabel?: string | null;
  /** YYYY-MM-DD */
  effectiveDate?: string | null;
  revisionCheckId?: string | null;
}

export interface RevisionApplyResult {
  applied: boolean;
  lineage_id: string | null;
  version_no: number;
  superseded_document_id: string | null;
  sync_state: SyncState | null;
  /** ingest_incomplete 등 — 개정 요청이 없었으면 null */
  reason: string | null;
}

export interface DocumentVersionsResponse {
  lineage_id: string;
  versions: DocumentVersion[];
}

export interface RevisionRollbackResponse {
  restored_document_id: string;
  detached_document_id: string | null;
  deleted_document_id: string | null;
  sync_state: SyncState;
}

export interface RevisionLinkResponse {
  document: DocumentVersion;
  sync_state: SyncState;
}

export interface RevisionMetaRequest {
  version_label: string | null;
  effective_date: string | null;
}

export interface RevisionSyncResponse {
  document_id: string;
  revision_status: RevisionStatus;
  sync_state: SyncState;
}

export interface RevisionModeResponse {
  kb_id: string;
  revision_mode: string;
}

/** 409 응답 detail (Design §6.2) */
export interface RevisionErrorDetail {
  code: string;
  message: string;
  reason?: string;
  document?: DocumentVersion;
}
