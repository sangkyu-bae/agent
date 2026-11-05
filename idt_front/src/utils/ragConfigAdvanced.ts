// agent-kb-quick-setup FR-10 — RAG 패널 "고급 설정" 접기 판정.
// 저장된 값이 기본값과 다르면 펼쳐서 기존 사용자가 자기 설정을 못 보는 일이 없게 한다.
import { DEFAULT_RAG_CONFIG, type RagToolConfig } from '@/types/ragToolConfig';

export const hasAdvancedRagConfig = (config: RagToolConfig): boolean =>
  (!!config.collection_name && !config.kb_id) ||
  Object.keys(config.metadata_filter ?? {}).length > 0 ||
  config.search_mode !== DEFAULT_RAG_CONFIG.search_mode ||
  config.top_k !== DEFAULT_RAG_CONFIG.top_k ||
  !!config.use_wiki_first ||
  !!config.use_routed_search ||
  config.tool_name !== DEFAULT_RAG_CONFIG.tool_name;
