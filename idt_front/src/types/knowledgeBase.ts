/**
 * 지식베이스 관리 화면 전용 타입 (kb-management-ui Design §5.1)
 *
 * KnowledgeBaseInfo는 kb-rag-filter 산출물로 types/ragToolConfig.ts에
 * 그대로 두고(D5 — import 경로 무회귀), 여기서는 관리 화면 계약만 정의한다.
 * 백엔드 계약: src/api/routes/knowledge_base_router.py
 */
import type { CollectionScope } from '@/types/ragToolConfig';

export interface CreateKnowledgeBaseRequest {
  name: string;
  description?: string | null;
  scope: CollectionScope;
  department_id?: string | null;
  collection_name: string;
  use_clause_chunking?: boolean;
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
