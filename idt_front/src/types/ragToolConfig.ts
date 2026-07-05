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
}

export type CollectionScope = 'PERSONAL' | 'DEPARTMENT' | 'PUBLIC';

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
};
