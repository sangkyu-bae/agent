/**
 * Agent-Skill 부착 타입 — 백엔드 `src/application/agent_skill/schemas.py` 매핑.
 *
 * skill-agent-integration Phase A: 에이전트에 Skill을 부착하면 실행 시
 * 해당 Skill의 instruction이 system_prompt에 주입된다. script는 실행되지 않는다.
 * 필드는 백엔드 스키마와 동일한 snake_case를 그대로 사용한다(skill.ts 관례).
 */

import type { SkillScriptType } from '@/types/skill';

/** 백엔드 AttachedSkillItem / AttachSkillResponse 매핑 */
export interface AttachedSkill {
  skill_id: string;
  name: string;
  description: string;
  script_type: SkillScriptType;
  sort_order: number;
  has_script: boolean;
}

/** 백엔드 ListAttachedSkillsResponse 매핑 */
export interface ListAttachedSkillsResponse {
  agent_id: string;
  skills: AttachedSkill[];
  total: number;
  max_attachable: number;
}

/** 백엔드 AttachSkillRequest 매핑 */
export interface AttachSkillRequest {
  skill_id: string;
}
