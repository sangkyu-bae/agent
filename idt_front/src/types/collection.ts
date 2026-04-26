export const COLLECTION_SCOPES = ['PERSONAL', 'DEPARTMENT', 'PUBLIC'] as const;
export type CollectionScope = (typeof COLLECTION_SCOPES)[number];

export const SCOPE_LABELS: Record<CollectionScope, { label: string; color: string; bg: string }> = {
  PERSONAL: { label: '개인', color: 'text-violet-600', bg: 'bg-violet-50' },
  DEPARTMENT: { label: '부서', color: 'text-blue-600', bg: 'bg-blue-50' },
  PUBLIC: { label: '공개', color: 'text-emerald-600', bg: 'bg-emerald-50' },
};

export interface CollectionInfo {
  name: string;
  vectors_count: number;
  points_count: number;
  status: string;
  scope?: CollectionScope;
  owner_id?: number;
}

export interface CollectionConfig {
  vector_size: number;
  distance: string;
}

export interface CollectionDetail extends CollectionInfo {
  config: CollectionConfig;
}

export interface CollectionListResponse {
  collections: CollectionInfo[];
  total: number;
}

export interface CreateCollectionRequest {
  name: string;
  embedding_model?: string;
  vector_size?: number;
  distance: string;
  scope?: CollectionScope;
  department_id?: string;
}

export interface UpdateScopeRequest {
  scope: CollectionScope;
  department_id?: string;
}

export interface UpdateScopeResponse {
  name: string;
  message: string;
}

export interface RenameCollectionRequest {
  new_name: string;
}

export interface CollectionMessageResponse {
  name: string;
  message: string;
}

export interface RenameCollectionResponse {
  old_name: string;
  new_name: string;
  message: string;
}

export interface ActivityLog {
  id: number;
  collection_name: string;
  action: string;
  user_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface ActivityLogListResponse {
  logs: ActivityLog[];
  total: number;
  limit: number;
  offset: number;
}

export interface ActivityLogFilters {
  collection_name?: string;
  action?: string;
  user_id?: string;
  from_date?: string;
  to_date?: string;
  limit?: number;
  offset?: number;
}

// ── 문서/청크 관련 타입 ────────────────────────────
export type ChunkStrategy = 'parent_child' | 'full_token' | 'semantic';
export type ChunkType = 'parent' | 'child' | 'full' | 'semantic';

export interface CollectionDocumentsResponse {
  collection_name: string;
  documents: DocumentSummary[];
  total_documents: number;
  offset: number;
  limit: number;
}

export interface DocumentSummary {
  document_id: string;
  filename: string;
  category: string;
  chunk_count: number;
  chunk_types: string[];
  user_id: string;
}

export interface DocumentChunksResponse {
  document_id: string;
  filename: string;
  chunk_strategy: ChunkStrategy;
  total_chunks: number;
  chunks: ChunkDetail[];
  parents: ParentChunkGroup[] | null;
}

export interface ChunkDetail {
  chunk_id: string;
  chunk_index: number;
  chunk_type: ChunkType;
  content: string;
  metadata: Record<string, unknown>;
}

export interface ParentChunkGroup {
  chunk_id: string;
  chunk_index: number;
  chunk_type: 'parent';
  content: string;
  children: ChunkDetail[];
}

export interface CollectionDocumentsParams {
  offset?: number;
  limit?: number;
}

export interface DocumentChunksParams {
  include_parent?: boolean;
}

export const CHUNK_STRATEGY_BADGE: Record<ChunkStrategy, { label: string; color: string; bg: string }> = {
  parent_child: { label: 'Parent/Child', color: 'text-blue-600', bg: 'bg-blue-50' },
  full_token: { label: 'Full Token', color: 'text-emerald-600', bg: 'bg-emerald-50' },
  semantic: { label: 'Semantic', color: 'text-amber-600', bg: 'bg-amber-50' },
};

export const CHUNK_TYPE_BADGE: Record<ChunkType, { label: string; color: string; bg: string }> = {
  parent: { label: 'parent', color: 'text-violet-600', bg: 'bg-violet-50' },
  child: { label: 'child', color: 'text-sky-600', bg: 'bg-sky-50' },
  full: { label: 'full', color: 'text-emerald-600', bg: 'bg-emerald-50' },
  semantic: { label: 'semantic', color: 'text-amber-600', bg: 'bg-amber-50' },
};

export const PROTECTED_COLLECTIONS = ['documents'] as const;

export const DISTANCE_METRICS = ['Cosine', 'Euclid', 'Dot'] as const;
export type DistanceMetric = (typeof DISTANCE_METRICS)[number];

export const COLLECTION_STATUS_MAP = {
  green: { label: '정상', color: 'bg-emerald-400' },
  yellow: { label: '최적화 중', color: 'bg-yellow-400' },
  red: { label: '오류', color: 'bg-red-400' },
} as const;
