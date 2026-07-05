// compose-tool-instructions FR-08 (Design D2/D3)
// compose 응답 tool_ids는 저장 형식({id}, mcp_{server_id})이고,
// 폼/도구함(form.tools, ToolPicker)은 카탈로그 형식(internal:{id}, mcp:{srv}:{tool})을
// 사용한다. 초안 [적용하기] 시 카탈로그 형식으로 변환해야 체크 표시가 동작한다.
import type { CatalogTool } from '@/types/toolCatalog';

/** 저장 형식 draft tool_ids → 카탈로그 형식 form.tools */
export function mapDraftToolIdsToCatalog(
  draftToolIds: string[],
  catalogTools: CatalogTool[] | undefined,
): string[] {
  const catalog = catalogTools ?? [];
  const result: string[] = [];
  for (const id of draftToolIds) {
    if (id.startsWith('mcp_')) {
      const serverId = id.slice('mcp_'.length);
      const serverTools = catalog.filter(
        (t) => t.source === 'mcp' && t.mcp_server_id === serverId,
      );
      // 카탈로그 미동기화(서버 단위 폴백) 시 원본 유지 — 저장은 가능
      result.push(...(serverTools.length ? serverTools.map((t) => t.tool_id) : [id]));
    } else {
      const catalogId = `internal:${id}`;
      result.push(
        catalog.some((t) => t.tool_id === catalogId) ? catalogId : id,
      );
    }
  }
  return [...new Set(result)];
}
