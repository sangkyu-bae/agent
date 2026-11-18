// graph-rag-foundation Design §4·§5 — 백엔드 interfaces/schemas/graph_rag.py 와 1:1.
// 런타임 상수(탭·라벨·범위)는 프론트 규칙에 따라 이 파일에 as const 로 둔다.

export const GRAPH_RAG_STAGES = ['off', 'admin_only', 'general'] as const;
export type GraphRagStage = (typeof GRAPH_RAG_STAGES)[number];

export const GRAPH_RAG_STAGE_LABELS: Record<GraphRagStage, string> = {
  off: '꺼짐',
  admin_only: '관리자 테스트',
  general: '전체 공개',
};

export const GRAPH_RAG_TABS = [
  { key: 'settings', label: '설정' },
  { key: 'extraction', label: '추출' },
  { key: 'entities', label: '엔티티·관계' },
  { key: 'topics', label: '주제' },
  { key: 'search', label: '검색 테스트' },
  { key: 'review', label: '검토 큐' },
] as const;
export type GraphRagTabKey = (typeof GRAPH_RAG_TABS)[number]['key'];

/** 도메인 VO GraphRagSettings 검증 범위와 같다(백엔드가 최종 검증). */
export const GRAPH_RAG_LIMITS = {
  concurrency: { min: 1, max: 8 },
  max_llm_calls_per_doc: { min: 1, max: 2000 },
  candidate_top_k: { min: 1, max: 8 },
  max_hops: { min: 1, max: 3 },
  graph_rrf_weight: { min: 0, max: 1 },
  retrieval_timeout_ms: { min: 100, max: 5000 },
  max_types: 30,
  max_type_len: 32,
} as const;

/** 엔티티·관계 타입 목록에서 지울 수 없는 기본 타입 */
export const GRAPH_RAG_OTHER_TYPE = '기타';

export const GRAPH_JOB_STATUS_LABELS: Record<string, string> = {
  pending: '대기',
  processing: '진행 중',
  completed: '완료',
  partial: '일부 완료',
  failed: '실패',
};

export const GRAPH_LINK_VIA_LABELS: Record<string, string> = {
  exact: '정확 일치',
  alias: '별칭',
  vector: '유사도',
};

export const GRAPH_TOPIC_STATUS_LABELS: Record<string, string> = {
  active: '사용',
  pending: '검토 대기',
  retired: '사용 안 함',
};

/** 검색 범위가 정해지지 않은 이유(백엔드 QueryScope.reason) */
export const GRAPH_SCOPE_REASON_LABELS: Record<string, string> = {
  no_topics: '등록된 주제 없음',
  no_matching_topic: '맞는 주제 없음',
  llm_unsure: 'LLM 확신 낮음',
  llm_error: 'LLM 오류',
  route_timeout: '주제 판정 시간 초과',
  route_error: '주제 판정 오류',
  no_entity_in_scope: '주제 안에 연결된 엔티티 없음 → 범위 없이 검색',
  no_chunk_in_scope: '주제 안에 근거 없음 → 범위 없이 검색',
};

// ── 설정·단계·상태 ───────────────────────────────────────────────────────

export interface GraphRagSettingsRequest {
  extraction_enabled: boolean;
  jev_enabled: boolean;
  link_threshold: number;
  new_threshold: number;
  extraction_llm_model_id: string | null;
  rejudge_llm_model_id: string | null;
  concurrency: number;
  max_llm_calls_per_doc: number;
  candidate_top_k: number;
  max_hops: number;
  graph_rrf_weight: number;
  retrieval_timeout_ms: number;
  entity_types: string[];
  relation_types: string[];
}

export interface GraphRagSettingsResponse extends GraphRagSettingsRequest {
  rollout_stage: GraphRagStage;
  updated_at: string | null;
}

export interface StageChangeRequest {
  to_stage: GraphRagStage;
  eval_baseline_run_id?: string | null;
  eval_graph_run_id?: string | null;
  force_reason?: string | null;
}

export interface GraphHealthResponse {
  backend: string;
  connected: boolean;
  external: boolean;
  node_count: number | null;
  relationship_count: number | null;
  node_limit: number | null;
  relationship_limit: number | null;
  error: string | null;
}

export interface GraphRagCapabilities {
  visible: boolean;
  stage?: GraphRagStage;
}

// ── 추출 ─────────────────────────────────────────────────────────────────

export type ExtractMode = 'resume' | 'rebuild';

export interface ExtractionJob {
  id: string;
  document_id: string;
  kb_id: string | null;
  collection_name: string;
  status: string;
  mode: string;
  trigger_source: string;
  extractor_version: string;
  total_chunks: number;
  processed_chunks: number;
  failed_chunks: number;
  llm_calls: number;
  judge_calls: number;
  entities_created: number;
  entities_linked: number;
  relations_created: number;
  error_message: string | null;
  requested_by: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
}

export interface KbDocumentJobItem {
  document_id: string;
  filename: string;
  chunk_count: number;
  job: ExtractionJob | null;
}

export interface KbDocumentJobsResponse {
  items: KbDocumentJobItem[];
  total: number;
}

export interface ExtractAcceptedResponse {
  job_id: string;
  status: string;
}

// ── 검토 큐 ──────────────────────────────────────────────────────────────

export interface ReviewCandidate {
  label?: string;
  entity_id?: string;
  name?: string;
  type?: string;
  match?: string;
  similarity?: number;
}

export interface ReviewItem {
  id: string;
  job_id: string;
  document_id: string;
  chunk_id: string;
  mention_text: string;
  mention_type: string;
  candidates: ReviewCandidate[];
  probabilities: Record<string, number> | null;
  chosen_label: string;
  entity_id: string;
  created_new: boolean;
  decided_by: string;
  band: string;
  probability: number | null;
  llm_confidence: string | null;
  llm_reason: string | null;
  review_status: string;
  created_at: string | null;
  /** module-4b: topic 이면 entity_id 가 주제 id */
  kind: 'entity' | 'topic';
}

export interface ReviewListResponse {
  items: ReviewItem[];
  total: number;
}

export interface ReviewRejectRequest {
  target_entity_id: string | null;
  note?: string | null;
}

// ── 주제 ─────────────────────────────────────────────────────────────────

export interface TopicItem {
  id: string;
  name: string;
  level: 1 | 2;
  parent_id: string | null;
  description: string;
  status: string;
  origin: string;
  created_by: string | null;
  document_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface TopicListResponse {
  items: TopicItem[];
}

export interface TopicCreateRequest {
  name: string;
  level: 1 | 2;
  parent_id?: string | null;
  description?: string | null;
}

export interface TopicUpdateRequest {
  name?: string;
  description?: string;
  status?: 'active' | 'retired';
}

// ── 엔티티 ───────────────────────────────────────────────────────────────

export interface EntityItem {
  id: string;
  name: string;
  type: string;
  description: string;
  mention_count: number;
  relation_count: number;
}

export interface EntityListResponse {
  items: EntityItem[];
  total: number;
  page: number;
  size: number;
}

export interface EntityRelationItem {
  id: string;
  direction: 'out' | 'in';
  kind: string;
  type: string;
  other_id: string;
  other_name: string;
  evidence_chunk_id: string;
  evidence_text: string;
  document_id: string;
}

export interface EntityMentionItem {
  chunk_id: string;
  document_id: string;
  decision_id: string;
  preview: string;
}

export interface EntityDetailResponse {
  entity: EntityItem;
  aliases: string[];
  relations: EntityRelationItem[];
  mentions: EntityMentionItem[];
}

export interface EntityListParams {
  q?: string;
  type?: string;
  page?: number;
  size?: number;
}

// ── 검색 테스트 ──────────────────────────────────────────────────────────

export interface SearchTestRequest {
  query: string;
  kb_id?: string | null;
  collection_name?: string | null;
  top_k: number;
  max_hops?: number | null;
}

export interface SearchHitItem {
  chunk_id: string;
  document_id: string;
  filename: string;
  score: number;
  source: string;
  content_preview: string;
}

export interface SearchTestResponse {
  scope: {
    topic_ids: string[] | null;
    topic_names: string[];
    decided_by: string;
    reason: string | null;
  };
  linked_entities: { id: string; name: string; type: string; via: string; score: number }[];
  paths: { hops: number; path: string[]; evidence_chunk_ids: string[] }[];
  graph_hits: SearchHitItem[];
  hybrid_hits: SearchHitItem[];
  fused_hits: SearchHitItem[];
  timings_ms: Record<string, number>;
  filtered_out: number;
  skip_reason: string | null;
  hybrid_error: string | null;
}

export interface IntegrityResponse {
  checked: number;
  missing: number;
  missing_chunk_ids: string[];
  missing_document_ids: string[];
}
