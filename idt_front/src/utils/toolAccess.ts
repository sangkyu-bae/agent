// tool-access-control §0 F6·§4.2 — 도구 권한 표시 유틸.
import { ApiError } from '@/services/api/ApiError';
import {
  TOOL_ACCESS_DENIED_CODE,
  type ExcludedTool,
  type ToolAccessDeniedDetail,
  type ToolAccessInfo,
} from '@/types/toolAccess';

/**
 * 폼·저장 표기 → 카탈로그 표기 (백엔드 domain/tool_access/tool_ids.py 와 같은 규칙).
 * 레거시 서버 단위(`mcp_{srv}`)는 원문 그대로 — 백엔드 tool_access 키도 원문이다.
 */
export const toCatalogToolId = (id: string): string =>
  id.startsWith('mcp') || id.includes(':') ? id : `internal:${id}`;

/** 저장 403 TOOL_ACCESS_DENIED → 사용자 안내 문구. 다른 오류면 null. */
export const toolAccessDeniedMessage = (
  err: unknown,
  nameOf: (catalogToolId: string) => string,
): string | null => {
  if (!(err instanceof ApiError) || err.code !== TOOL_ACCESS_DENIED_CODE) return null;
  const ids = (err.detail as Partial<ToolAccessDeniedDetail> | undefined)?.tool_ids ?? [];
  if (!ids.length) return '권한이 없는 도구가 있어 저장할 수 없습니다.';
  return `권한이 없는 도구가 있어 저장할 수 없습니다: ${ids.map(nameOf).join(', ')}`;
};

export interface UnlistedAttachedTool {
  /** 폼에 들어 있는 원래 id — 제거 시 이 값으로 토글한다 */
  formId: string;
  name: string;
  permitted: boolean;
}

/**
 * 에이전트에 붙어 있지만 (필터된) 카탈로그에 없고, 서버가 '불허'라고 답한 도구 (FR-13).
 * 비활성화 등 다른 이유로 카탈로그에 없는 도구는 권한 문제가 아니므로 넣지 않는다
 * (tool_access 정보가 없거나 permitted=true) — 기존 화면 동작 유지.
 */
export const unlistedAttachedTools = (
  formToolIds: string[],
  catalogToolIds: string[],
  toolAccess: ToolAccessInfo[] | null | undefined,
): UnlistedAttachedTool[] => {
  const catalog = new Set(catalogToolIds);
  const byId = new Map((toolAccess ?? []).map((t) => [t.tool_id, t]));
  const out: UnlistedAttachedTool[] = [];
  for (const id of formToolIds) {
    if (catalog.has(id)) continue;
    const info = byId.get(toCatalogToolId(id));
    if (info && !info.permitted) out.push({ formId: id, name: info.name, permitted: false });
  }
  return out;
};

/** 포크 응답의 제외 도구 안내 (FR-08). 없으면 null — 기존 화면 그대로. */
export const forkExcludedNotice = (excluded: ExcludedTool[] | null | undefined): string | null =>
  excluded && excluded.length
    ? `복제본에서 권한이 없는 도구를 제외했습니다: ${excluded.map((t) => t.name).join(', ')}`
    : null;

/** 실행·포크 응답의 제외 도구 안내 문구. 없으면 null. */
export const excludedToolsNotice = (excluded: ExcludedTool[] | null | undefined): string | null =>
  excluded && excluded.length
    ? `권한이 없어 사용하지 않은 도구: ${excluded.map((t) => t.name).join(', ')}`
    : null;
