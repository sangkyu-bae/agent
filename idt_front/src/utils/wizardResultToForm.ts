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
): AgentBuilderFormData => ({
  ...prev,
  ...applyToolsToForm(result.toolIds, prev, catalogTools),
  name: result.suggestedName,
  systemPrompt: result.systemPrompt,
});
