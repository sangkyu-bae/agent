/**
 * Skill Builder 타입 — 백엔드 `src/application/skill_builder/schemas.py` 매핑.
 *
 * Skill = 지시문(instruction) + 실행 스크립트(script_content, 저장 전용).
 * 필드는 백엔드 스키마와 동일한 snake_case를 그대로 사용한다(mcpServer.ts 관례).
 */

export type SkillVisibility = 'private' | 'department' | 'public';
export type SkillScriptType = 'none' | 'python' | 'shell';

/** 백엔드 SkillResponse 매핑 (단건 상세) */
export interface Skill {
  id: string;
  user_id: string;
  name: string;
  description: string;
  instruction: string;
  trigger: string | null;
  script_type: SkillScriptType;
  script_content: string | null;
  status: string;
  visibility: SkillVisibility;
  department_id: string | null;
  forked_from: string | null;
  forked_at: string | null;
  created_at: string;
  updated_at: string;
}

/** 백엔드 SkillSummary 매핑 (목록 행) */
export interface SkillSummary {
  id: string;
  name: string;
  description: string;
  script_type: SkillScriptType;
  visibility: SkillVisibility;
  owner_user_id: string;
  forked_from: string | null;
  can_edit: boolean;
  can_delete: boolean;
  created_at: string;
}

/** 백엔드 ListSkillsResponse 매핑 */
export interface SkillListResponse {
  skills: SkillSummary[];
  total: number;
  page: number;
  size: number;
}

/** 백엔드 ListSkillsRequest 매핑 */
export interface ListSkillsRequest {
  scope?: 'mine' | 'department' | 'public' | 'all';
  search?: string | null;
  page?: number;
  size?: number;
}

/** 백엔드 CreateSkillRequest 매핑 (user_id는 백엔드에서 토큰 기반 주입) */
export interface CreateSkillRequest {
  name: string;
  description: string;
  instruction: string;
  trigger?: string | null;
  script_type: SkillScriptType;
  script_content?: string | null;
  visibility: SkillVisibility;
  department_id?: string | null;
}

/** 백엔드 UpdateSkillRequest 매핑 (모든 필드 optional) */
export interface UpdateSkillRequest {
  name?: string;
  description?: string;
  instruction?: string;
  trigger?: string | null;
  script_type?: SkillScriptType;
  script_content?: string | null;
  visibility?: SkillVisibility;
  department_id?: string | null;
}

/** 백엔드 ForkSkillRequest 매핑 */
export interface ForkSkillRequest {
  name?: string | null;
}
