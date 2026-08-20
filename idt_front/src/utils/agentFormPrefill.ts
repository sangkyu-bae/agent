/**
 * 스튜디오 폼 프리필의 도구 관련 공통 로직.
 *
 * Design Ref: agent-create-wizard FR-F12 — 변환 로직 단일화.
 *
 * compose 초안(Fix 탭·구 진입화면)과 위저드 결과는 출처가 다르지만
 * "도구 목록을 폼에 반영할 때 해야 하는 일"은 같다: 빌트인 제외, RAG 설정
 * 동기화, 문서 드래프트 정리. 두 벌로 구현하면 한쪽만 고쳐져 조용히 어긋난다.
 */
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import { DOCUMENT_EXTRACTOR_TOOL_ID } from '@/types/documentExtractor';
import { DOCUMENT_GENERATOR_TOOL_ID } from '@/types/documentGenerator';
import { RAG_CATALOG_TOOL_ID } from './agentDetailMapping';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { CatalogTool } from '@/types/toolCatalog';

/** 폼에서 도구에 영향받는 필드만 추린 조각. */
export type ToolPrefillSlice = Pick<
  AgentBuilderFormData,
  'tools' | 'toolConfigs' | 'documentExtractorDraft' | 'documentGeneratorDraft'
>;

/**
 * 카탈로그 도구 id 목록을 폼 조각으로 변환한다 (순수 함수).
 *
 * - **빌트인 제외** (builtin-tools D8): 빌트인은 서버가 주입하므로 form.tools 에
 *   넣으면 칩이 중복된다. `excludedBuiltinTools` 는 건드리지 않는다.
 * - **RAG 설정 동기화**: 내부 문서 검색이 들어오면 기본 설정을 만들고,
 *   빠지면 지운다 (handleToolToggle 과 동일한 부수효과).
 * - **문서 드래프트 정리**: 해당 도구가 빠지면 드래프트도 버린다.
 *
 * @param toolIds 이미 카탈로그 표기(`internal:x` / `mcp:...`)인 id 목록.
 *   compose 초안처럼 표기가 다른 입력은 호출부가 먼저 매핑해서 넘긴다.
 */
export const applyToolsToForm = (
  toolIds: string[],
  prev: AgentBuilderFormData,
  catalogTools?: CatalogTool[],
): ToolPrefillSlice => {
  const builtinIds = new Set(
    (catalogTools ?? []).filter((t) => t.is_builtin).map((t) => t.tool_id),
  );
  const tools = toolIds.filter((id) => !builtinIds.has(id));

  const toolConfigs = { ...prev.toolConfigs };
  if (tools.includes(RAG_CATALOG_TOOL_ID)) {
    if (!toolConfigs[RAG_CATALOG_TOOL_ID]) {
      toolConfigs[RAG_CATALOG_TOOL_ID] = { ...DEFAULT_RAG_CONFIG };
    }
  } else {
    delete toolConfigs[RAG_CATALOG_TOOL_ID];
  }

  return {
    tools,
    toolConfigs,
    documentExtractorDraft: tools.includes(DOCUMENT_EXTRACTOR_TOOL_ID)
      ? prev.documentExtractorDraft
      : null,
    documentGeneratorDraft: tools.includes(DOCUMENT_GENERATOR_TOOL_ID)
      ? prev.documentGeneratorDraft
      : null,
  };
};
