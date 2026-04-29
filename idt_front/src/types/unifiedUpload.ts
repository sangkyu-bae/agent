export interface UnifiedUploadParams {
  user_id: string;
  collection_name: string;
  child_chunk_size?: number;
  child_chunk_overlap?: number;
  top_keywords?: number;
}

export interface QdrantResult {
  collection_name: string;
  stored_ids: string[];
  embedding_model: string;
  status: 'success' | 'failed';
  error: string | null;
}

export interface EsResult {
  index_name: string;
  indexed_count: number;
  status: 'success' | 'failed';
  error: string | null;
}

export interface ChunkingConfig {
  strategy: string;
  parent_chunk_size: number;
  child_chunk_size: number;
  child_chunk_overlap: number;
}

export type UnifiedUploadStatus = 'completed' | 'partial' | 'failed';

export interface UnifiedUploadResponse {
  document_id: string;
  filename: string;
  total_pages: number;
  chunk_count: number;
  qdrant: QdrantResult;
  es: EsResult;
  chunking_config: ChunkingConfig;
  status: UnifiedUploadStatus;
}

export type UploadModalStatus = 'idle' | 'loading' | 'success' | 'partial' | 'error';

export interface ChunkingOptions {
  childChunkSize: number;
  childChunkOverlap: number;
  topKeywords: number;
}

export const DEFAULT_CHUNKING_OPTIONS: ChunkingOptions = {
  childChunkSize: 500,
  childChunkOverlap: 50,
  topKeywords: 10,
};
