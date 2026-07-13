export interface RagToolConfig {
  collection_name?: string;
  es_index?: string;
  metadata_filter: Record<string, string>;
  top_k: number;
  search_mode: 'hybrid' | 'vector_only' | 'bm25_only';
  rrf_k: number;
  tool_name: string;
  tool_description: string;
  /** LLM-WIKI-001 Step6: 승인 위키를 먼저 검색(WikiFirstSearch) 후 원본 폴백 */
  use_wiki_first?: boolean;
  /** rag-routed-integration: 3계층 요약 라우팅 검색 opt-in — 실패 시 위 검색 모드로 자동 전환 (교차검증용) */
  use_routed_search?: boolean;
  /** kb-rag-filter: 논리 지식베이스 필터 opt-in — 설정 시 컬렉션은 KB의 것으로 자동 고정 */
  kb_id?: string;
}

export type CollectionScope = 'PERSONAL' | 'DEPARTMENT' | 'PUBLIC';

/** kb-rag-filter: GET /api/v1/knowledge-bases 응답 항목
 *  (kb-management-ui D5: 관리 화면용 필드 additive 확장 — 기존 사용처 무영향) */
export interface KnowledgeBaseInfo {
  kb_id: string;
  name: string;
  description?: string | null;
  scope: CollectionScope;
  department_id?: string | null;
  collection_name: string;
  owner_id?: number;
  use_clause_chunking?: boolean;
  created_at?: string | null;
}

export interface CollectionInfo {
  name: string;
  display_name: string;
  vectors_count?: number;
  scope?: CollectionScope;
}

export interface MetadataKeyInfo {
  key: string;
  sample_values: string[];
  value_count: number;
}

/** 검색 모드 UI 라벨 (RagConfigPanel 라디오 + 도구함 요약 배지 공용) */
export const SEARCH_MODES = [
  { value: 'hybrid', label: '하이브리드' },
  { value: 'vector_only', label: '벡터' },
  { value: 'bm25_only', label: 'BM25' },
] as const;

export const DEFAULT_RAG_CONFIG: RagToolConfig = {
  metadata_filter: {},
  top_k: 5,
  search_mode: 'hybrid',
  rrf_k: 60,
  tool_name: '내부 문서 검색',
  tool_description:
    '내부 문서에서 관련 정보를 검색합니다. 질문에 대한 내부 문서 정보가 필요할 때 사용하세요.',
  use_wiki_first: false,
  use_routed_search: false,
};
