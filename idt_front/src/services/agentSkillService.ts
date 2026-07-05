import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  AttachedSkill,
  ListAttachedSkillsResponse,
} from '@/types/agentSkill';

export const agentSkillService = {
  /** 에이전트에 부착된 Skill 목록 조회. */
  listAttached: async (
    agentId: string,
  ): Promise<ListAttachedSkillsResponse> => {
    const { data } = await authApiClient.get<ListAttachedSkillsResponse>(
      API_ENDPOINTS.AGENT_SKILLS(agentId),
    );
    return data;
  },

  /** Skill 부착 (instruction만 주입, script는 실행되지 않음). */
  attach: async (agentId: string, skillId: string): Promise<AttachedSkill> => {
    const { data } = await authApiClient.post<AttachedSkill>(
      API_ENDPOINTS.AGENT_SKILLS(agentId),
      { skill_id: skillId },
    );
    return data;
  },

  /** 부착 해제 (멱등). */
  detach: async (agentId: string, skillId: string): Promise<void> => {
    await authApiClient.delete(
      API_ENDPOINTS.AGENT_SKILL_DETACH(agentId, skillId),
    );
  },
};
