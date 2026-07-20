/**
 * 운영 대시보드 타입 (admin-dashboard Design §3.2).
 * 백엔드 src/interfaces/schemas/admin_dashboard_response.py 계약 동기화.
 */

export interface KbStats {
  total: number;
  active: number;
  by_scope: Record<string, number>;
}

export interface DocumentStats {
  total: number;
  with_kb: number;
  without_kb: number;
}

export interface ChunkStats {
  total: number;
}

export interface UserStats {
  total: number;
  approved: number;
  pending: number;
  admins: number;
}

export interface DashboardStats {
  kb: KbStats;
  documents: DocumentStats;
  chunks: ChunkStats;
  users: UserStats;
}

export interface KbBreakdownRow {
  kb_id: string;
  name: string;
  scope: string;
  status: string;
  document_count: number;
  chunk_count: number;
  last_uploaded_at: string | null;
}

export interface KbBreakdownResponse {
  rows: KbBreakdownRow[];
}

export interface RecentDocumentRow {
  document_id: string;
  filename: string;
  kb_id: string | null;
  kb_name: string | null;
  collection_name: string;
  chunk_count: number;
  chunk_strategy: string;
  created_at: string;
}

export interface RecentDocumentsResponse {
  rows: RecentDocumentRow[];
}

export type HealthStatus = 'ok' | 'fail';

export interface HealthComponent {
  name: string;
  status: HealthStatus;
  latency_ms: number | null;
  error: string | null;
}

export interface StorageHealthResponse {
  components: HealthComponent[];
}
