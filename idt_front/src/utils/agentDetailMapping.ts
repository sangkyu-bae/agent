// agent-builder-edit-mapping (Design §2-1)
// 수정 모드 프라임: GetAgent 응답(저장 형식)을 폼 데이터(카탈로그 형식)로 변환한다.
// - 모델: llm_model_id(id) → model_name 역매핑 (초안 적용 경로와 동일 규칙)
// - 도구: 저장 형식 tool_ids → 카탈로그 형식 (mapDraftToolIdsToCatalog 재사용)
// - RAG 설정: RAG worker tool_config → form.toolConfigs 복원
import type { AgentDetail } from '@/types/agentStore';
import type { LlmModel } from '@/types/llmModel';
import type { CatalogTool } from '@/types/toolCatalog';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { RagToolConfig } from '@/types/ragToolConfig';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import { mapDraftToolIdsToCatalog } from './draftToolMapping';

/** RAG 도구의 저장 형식 tool_id (worker.tool_id) */
const RAG_WORKER_TOOL_ID = 'internal_document_search';

/** RAG 도구의 카탈로그 형식 tool_id (form.tools / 도구함 / ToolPicker) */
export const RAG_CATALOG_TOOL_ID = 'internal:internal_document_search';

/** 수정 모드 진입 시 서버 detail → 폼 데이터 매핑 (순수 함수). */
export function mapDetailToForm(
  detail: AgentDetail,
  models: LlmModel[] | undefined,
  catalogTools: CatalogTool[] | undefined,
): AgentBuilderFormData {
  // 역매핑 실패(레지스트리에서 삭제된 모델) 시 raw id 유지 → 라벨 폴백이 안내
  const modelName =
    models?.find((m) => m.id === detail.llm_model_id)?.model_name ??
    detail.llm_model_id;

  const ragWorker = detail.workers.find(
    (w) =>
      (w.worker_type ?? 'tool') === 'tool' &&
      w.tool_id === RAG_WORKER_TOOL_ID &&
      w.tool_config,
  );
  // DEFAULT 머지로 서버 저장분에 없는 신규 필드(use_wiki_first 등) 기본값 보장
  const toolConfigs: Record<string, RagToolConfig> = ragWorker
    ? {
        [RAG_CATALOG_TOOL_ID]: {
          ...DEFAULT_RAG_CONFIG,
          ...(ragWorker.tool_config as Partial<RagToolConfig>),
        },
      }
    : {};

  const subAgents = detail.workers
    .filter((w) => w.worker_type === 'sub_agent' && w.ref_agent_id)
    .map((w) => ({
      ref_agent_id: w.ref_agent_id as string,
      name: w.ref_agent_name ?? (w.ref_agent_id as string),
      description: w.description ?? '',
    }));

  return {
    name: detail.name,
    description: detail.description,
    model: modelName,
    systemPrompt: detail.system_prompt,
    tools: mapDraftToolIdsToCatalog(detail.tool_ids, catalogTools),
    temperature: detail.temperature,
    toolConfigs,
    subAgents,
    skills: detail.skill_ids ?? [],
    // edit 모드 스케줄은 SchedulePanel이 서버 직결 — staged 미사용
    schedules: [],
  };
}
