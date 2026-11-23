// answer-citation-verification Design §4.1 — 근거 판정 모델 관리자 설정. 컴포넌트는 이 서비스만 경유한다.
import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  GroundingJudgeSettingRequest,
  GroundingJudgeSettingResponse,
} from '@/types/groundingJudge';

export const groundingJudgeService = {
  getSetting: async (): Promise<GroundingJudgeSettingResponse> => {
    const { data } = await authApiClient.get<GroundingJudgeSettingResponse>(
      API_ENDPOINTS.ADMIN_GROUNDING_JUDGE_SETTINGS
    );
    return data;
  },

  updateSetting: async (
    req: GroundingJudgeSettingRequest
  ): Promise<GroundingJudgeSettingResponse> => {
    const { data } = await authApiClient.put<GroundingJudgeSettingResponse>(
      API_ENDPOINTS.ADMIN_GROUNDING_JUDGE_SETTINGS,
      req
    );
    return data;
  },
};
