// LLM-WIKI-001: LLM Wiki(Self-Improving RAG) 프론트 타입 — 백엔드 wiki_router 스키마와 동기화.

export const WIKI_STATUSES = ['draft', 'approved', 'deprecated'] as const;
export type WikiStatus = (typeof WIKI_STATUSES)[number];

export const WIKI_SOURCE_TYPES = [
  'distilled',
  'conversation',
  'websearch',
  'human',
] as const;
export type WikiSourceType = (typeof WIKI_SOURCE_TYPES)[number];

export const WIKI_STATUS_LABELS: Record<
  WikiStatus,
  { label: string; color: string }
> = {
  draft: { label: '초안', color: 'text-zinc-600 bg-zinc-100' },
  approved: { label: '승인', color: 'text-emerald-600 bg-emerald-50' },
  deprecated: { label: '폐기', color: 'text-red-600 bg-red-50' },
};

export interface WikiArticle {
  id: string;
  agent_id: string;
  title: string;
  content: string;
  source_type: WikiSourceType;
  source_refs: string[];
  status: WikiStatus;
  confidence: number;
  valid_until: string | null;
  version: number;
  editor_id: string | null;
  reviewer_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  /** wiki-user-facing: 가상 폴더 경로. null=미분류 */
  path: string | null;
}

export interface WikiListResponse {
  items: WikiArticle[];
  total: number;
}

export interface DistillRequest {
  agent_id: string;
  collection_name: string;
  max_articles?: number;
}

export interface DistillResponse {
  agent_id: string;
  created_count: number;
  /** fix-wiki-distill-dedup: 이미 정제된 그룹 스킵 수 (additive) */
  skipped_count?: number;
  items: WikiArticle[];
}

export interface ReviewActionRequest {
  reviewer_id: string;
}

export interface UpdateWikiRequest {
  title: string;
  content: string;
  /** @deprecated 서버는 인증 사용자를 기록한다 — 하위호환 필드 */
  editor_id?: string;
  path?: string | null;
}

// ── wiki-user-facing: 소유자 직접 작성 + 지식 트리 ──────────────

export interface CreateWikiRequest {
  agent_id: string;
  title: string;
  content: string;
  path?: string | null;
  valid_until?: string | null;
}

export interface WikiTreeItem {
  id: string;
  title: string;
  status: WikiStatus;
  source_type: WikiSourceType;
  updated_at: string | null;
}

export interface WikiTreeGroup {
  /** null = 미분류 */
  path: string | null;
  items: WikiTreeItem[];
}

export interface WikiTreeResponse {
  agent_id: string;
  groups: WikiTreeGroup[];
  total: number;
}
