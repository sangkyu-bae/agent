// tool-access-control Design §4.2 — 관리자 도구 권한 API 계약 (백엔드 application/tool_access/schemas.py 와 1:1).
// tool_id 는 모두 카탈로그 표기 (internal:{id} / mcp:{server}:{tool}).

export interface ReplaceToolAccessRequest {
  tool_ids: string[];
}

export interface DefaultToolAccessResponse {
  tool_ids: string[];
}

export interface DepartmentToolAccessResponse {
  department_id: string;
  department_name: string;
  tool_ids: string[];
  default_tool_ids: string[];
}

export interface ToolGrantSource {
  kind: 'default' | 'department';
  department_id?: string | null;
  department_name?: string | null;
}

export interface InheritedToolAccess {
  tool_id: string;
  sources: ToolGrantSource[];
}

export interface UserToolAccessResponse {
  user_id: number;
  is_admin: boolean;
  tool_ids: string[];
  inherited: InheritedToolAccess[];
}

/** 권한이 없어 제외된 도구 — 실행·포크 응답 공용 (additive) */
export interface ExcludedTool {
  tool_id: string;
  name: string;
  reason: 'no_permission';
}

/** 에이전트 상세의 붙은 도구별 허용 여부 (additive) */
export interface ToolAccessInfo {
  tool_id: string;
  name: string;
  permitted: boolean;
}

/** 저장 403 detail — authClient 가 ApiError.detail 로 보존한다 */
export interface ToolAccessDeniedDetail {
  code: 'TOOL_ACCESS_DENIED';
  message: string;
  tool_ids: string[];
}

export const TOOL_ACCESS_DENIED_CODE = 'TOOL_ACCESS_DENIED' as const;

export const TOOL_ACCESS_TABS = ['default', 'department', 'user'] as const;
export type ToolAccessTab = (typeof TOOL_ACCESS_TABS)[number];

export const TOOL_ACCESS_TAB_LABELS: Record<ToolAccessTab, string> = {
  default: '기본 허용 도구',
  department: '부서별',
  user: '사용자별',
};

/** 체크리스트 행 상태 — 잠금 사유(기본 세트·부서 상속)는 체크된 채 편집 불가 */
export interface ToolAccessRowLock {
  label: string;
}
