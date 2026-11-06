/**
 * 위저드 결과를 스튜디오 폼 데이터로 변환한다 (순수 함수).
 *
 * Design Ref: agent-create-wizard §2.2 / FR-F12.
 *
 * `composeDraftToForm` 과 달리 도구 id 매핑이 없다: 위저드의 도구는 카탈로그에서
 * 직접 고른 것(추천은 `CatalogCandidateReader` 산출, 추가는 `ToolPickerModal`)이라
 * 이미 카탈로그 표기다. 빌트인 제외·RAG 동기화는 공유 헬퍼가 담당한다.
 *
 * 모델·온도를 건드리지 않는 이유(사용자 결정): 위저드는 이름 후보만 제안하고
 * 모델/온도는 스튜디오 기본값을 쓴다 — 위저드 단계를 늘리지 않기 위해서다.
 */
import { applyToolsToForm } from './agentFormPrefill';
import { attachKbToForm } from './kbQuickSetup';
import { DOCUMENT_EXTRACTOR_TOOL_ID } from '@/types/documentExtractor';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { WizardResult } from '@/store/agentDraftStore';
import type { CatalogTool } from '@/types/toolCatalog';

export interface WizardToFormDeps {
  catalogTools?: CatalogTool[];
}

export const wizardResultToForm = (
  result: WizardResult,
  prev: AgentBuilderFormData,
  { catalogTools }: WizardToFormDeps,
): AgentBuilderFormData => {
  const form: AgentBuilderFormData = {
    ...prev,
    ...applyToolsToForm(result.toolIds, prev, catalogTools),
    name: result.suggestedName,
    systemPrompt: result.systemPrompt,
  };
  // wizard-template-request FR-12 (D2): 양식 카드가 확정한 드래프트를 그대로 꽂는다.
  // 추출기 도구가 확정 목록에 없으면 applyToolsToForm 이 이미 드래프트를 비웠으므로
  // 여기서는 도구 포함 여부를 한 번 더 확인해 고아 드래프트를 만들지 않는다.
  const withTemplate: AgentBuilderFormData =
    result.documentExtractorDraft?.confirmed &&
    form.tools.includes(DOCUMENT_EXTRACTOR_TOOL_ID)
      ? { ...form, documentExtractorDraft: result.documentExtractorDraft }
      : form;
  // agent-kb-quick-setup FR-13: 문서 단계의 KB 를 RAG 도구 + kb_id 로 프리필
  return result.kbId ? attachKbToForm(withTemplate, result.kbId) : withTemplate;
};
