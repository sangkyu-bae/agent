// Design Ref: agent-create-entry §3.2 — 초안→폼 변환의 단일 구현.
// AgentBuilderPage.handleApplyDraft 본문을 그대로 이관한 것으로, Fix 탭(스튜디오 내부)과
// 진입 화면(/agent-builder/new)이 같은 함수를 쓴다. 두 곳에 따로 구현하면
// 도구 ID 매핑·빌트인 제외·RAG 부수효과가 조용히 어긋난다.
import { mapDraftToolIdsToCatalog } from './draftToolMapping';
import { applyToolsToForm } from './agentFormPrefill';
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
  // 초안 표기(순수 id 등)를 카탈로그 표기로 먼저 맞춘 뒤, 빌트인 제외·RAG
  // 동기화·문서 드래프트 정리는 위저드와 **공유**한다 (agent-create-wizard FR-F12).
  const toolSlice = applyToolsToForm(
    mapDraftToolIdsToCatalog(draft.tool_ids, catalogTools),
    prev,
    catalogTools,
  );

  // llm_model_id 역매핑 실패 시 모델 미변경 (카드에 안내 표시됨)
  const modelName = models?.find((m) => m.id === draft.llm_model_id)?.model_name;

  return {
    ...prev,
    ...toolSlice,
    name: draft.name_suggestion,
    systemPrompt: draft.system_prompt,
    temperature: draft.temperature,
    model: modelName ?? prev.model,
  };
};
