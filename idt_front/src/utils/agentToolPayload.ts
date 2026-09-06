// agent-update-tool-editing D §5.1 — 저장 payload 의 tool_ids 구성 (순수 함수)
//
// 빌트인은 서버가 카탈로그 기준으로 재주입하며 도구 상한(MAX_TOOLS)에서도
// 제외된다(builtin-tools D6). edit 모드 폼은 저장된 빌트인을 일반 칩으로
// 보여주므로(LeftConfigPanel isEditMode 분기), form.tools 를 그대로 보내면
// 빌트인이 상한을 잡아먹는다 — 전송 시점에만 걸러낸다.
import type { CatalogTool } from '@/types/toolCatalog';

/** form.tools(카탈로그 표기) → 저장 요청 tool_ids. 빌트인 제외, 순서 보존. */
export function buildToolIdsForSave(
  tools: string[],
  catalogTools: CatalogTool[] | undefined,
): string[] {
  const builtinIds = new Set(
    (catalogTools ?? []).filter((t) => t.is_builtin).map((t) => t.tool_id),
  );
  return tools.filter((id) => !builtinIds.has(id));
}
