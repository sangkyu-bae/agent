// Design Ref: agent-create-entry §3.2 — 초안→폼 변환의 단일 구현.
// AgentBuilderPage.handleApplyDraft 본문을 그대로 이관한 것으로, Fix 탭(스튜디오 내부)과
// 진입 화면(/agent-builder/new)이 같은 함수를 쓴다. 두 곳에 따로 구현하면
// 도구 ID 매핑·빌트인 제외·RAG 부수효과가 조용히 어긋난다.
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import { DOCUMENT_EXTRACTOR_TOOL_ID } from '@/types/documentExtractor';
import { DOCUMENT_GENERATOR_TOOL_ID } from '@/types/documentGenerator';
import { mapDraftToolIdsToCatalog } from './draftToolMapping';
import { RAG_CATALOG_TOOL_ID } from './agentDetailMapping';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';
import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';

export interface DraftToFormDeps {
  catalogTools?: CatalogTool[];
  models?: LlmModel[];
}

/**
 * compose 초안을 폼 데이터로 변환한다 (순수 함수).
 *
 * 주의: catalogTools/models가 아직 로딩 중(undefined)이면 도구 매핑과 모델 역매핑이
 * 폴백으로 떨어진다. 호출부는 두 쿼리가 settled된 뒤에 부르는 것이 원칙이다
 * (Design §2.4 G5).
 */
export const composeDraftToForm = (
  draft: ComposeAgentDraftResponse,
  prev: AgentBuilderFormData,
  { catalogTools, models }: DraftToFormDeps,
): AgentBuilderFormData => {
  // builtin-tools D8: 초안이 빌트인을 포함해도 form.tools에 혼입하지 않는다
  // (표시·전송은 파생값 — 서버 주입과의 중복 칩 방지, excluded는 불변)
  const builtinIds = new Set(
    (catalogTools ?? []).filter((t) => t.is_builtin).map((t) => t.tool_id),
  );
  const newTools = mapDraftToolIdsToCatalog(draft.tool_ids, catalogTools).filter(
    (id) => !builtinIds.has(id),
  );

  // handleToolToggle과 동일한 부수효과 동기화 (RAG 설정 / 문서추출기 드래프트)
  const newConfigs = { ...prev.toolConfigs };
  if (newTools.includes(RAG_CATALOG_TOOL_ID)) {
    if (!newConfigs[RAG_CATALOG_TOOL_ID]) {
      newConfigs[RAG_CATALOG_TOOL_ID] = { ...DEFAULT_RAG_CONFIG };
    }
  } else {
    delete newConfigs[RAG_CATALOG_TOOL_ID];
  }

  // llm_model_id 역매핑 실패 시 모델 미변경 (카드에 안내 표시됨)
  const modelName = models?.find((m) => m.id === draft.llm_model_id)?.model_name;

  return {
    ...prev,
    name: draft.name_suggestion,
    systemPrompt: draft.system_prompt,
    tools: newTools,
    temperature: draft.temperature,
    model: modelName ?? prev.model,
    toolConfigs: newConfigs,
    documentExtractorDraft: newTools.includes(DOCUMENT_EXTRACTOR_TOOL_ID)
      ? prev.documentExtractorDraft
      : null,
    documentGeneratorDraft: newTools.includes(DOCUMENT_GENERATOR_TOOL_ID)
      ? prev.documentGeneratorDraft
      : null,
  };
};
