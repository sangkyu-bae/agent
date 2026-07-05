import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  Skill,
  SkillListResponse,
  ListSkillsRequest,
  CreateSkillRequest,
  UpdateSkillRequest,
  ForkSkillRequest,
} from '@/types/skill';

export const skillService = {
  /** 접근 가능한 Skill 목록 (가시성/RBAC 기반). */
  getSkills: async (req: ListSkillsRequest = {}): Promise<SkillListResponse> => {
    const { data } = await authApiClient.post<SkillListResponse>(
      API_ENDPOINTS.SKILLS_LIST,
      { scope: 'all', page: 1, size: 50, ...req },
    );
    return data;
  },

  getSkill: async (id: string): Promise<Skill> => {
    const { data } = await authApiClient.get<Skill>(API_ENDPOINTS.SKILL_DETAIL(id));
    return data;
  },

  createSkill: async (req: CreateSkillRequest): Promise<Skill> => {
    const { data } = await authApiClient.post<Skill>(API_ENDPOINTS.SKILLS, req);
    return data;
  },

  // 백엔드 라우터는 PUT (전체/부분 수정)
  updateSkill: async (id: string, req: UpdateSkillRequest): Promise<Skill> => {
    const { data } = await authApiClient.put<Skill>(
      API_ENDPOINTS.SKILL_DETAIL(id),
      req,
    );
    return data;
  },

  deleteSkill: async (id: string): Promise<void> => {
    await authApiClient.delete(API_ENDPOINTS.SKILL_DETAIL(id));
  },

  forkSkill: async (id: string, req: ForkSkillRequest = {}): Promise<Skill> => {
    const { data } = await authApiClient.post<Skill>(
      API_ENDPOINTS.SKILL_FORK(id),
      req,
    );
    return data;
  },
};
