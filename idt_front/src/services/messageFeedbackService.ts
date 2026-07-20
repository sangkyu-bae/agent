// agent-eval-gate: 답변 평가 API 서비스. authApiClient(Bearer) 경유.
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  AgentEvalStat,
  MyFeedback,
  Rating,
  RecentNegativeItem,
} from '@/types/messageFeedback';

export const messageFeedbackService = {
  get: async (messageId: number): Promise<MyFeedback> => {
    const res = await authApiClient.get<MyFeedback>(
      API_ENDPOINTS.MESSAGE_FEEDBACK(messageId),
    );
    return res.data;
  },

  submit: async (
    messageId: number,
    rating: Rating,
    comment?: string,
  ): Promise<MyFeedback> => {
    const res = await authApiClient.post<MyFeedback>(
      API_ENDPOINTS.MESSAGE_FEEDBACK(messageId),
      { rating, comment: comment ?? null },
    );
    return res.data;
  },

  // admin
  getAgentStats: async (): Promise<AgentEvalStat[]> => {
    const res = await authApiClient.get<AgentEvalStat[]>(
      API_ENDPOINTS.ADMIN_EVAL_AGENTS,
    );
    return res.data;
  },

  getRecentNegative: async (): Promise<RecentNegativeItem[]> => {
    const res = await authApiClient.get<RecentNegativeItem[]>(
      API_ENDPOINTS.ADMIN_EVAL_RECENT_NEGATIVE,
    );
    return res.data;
  },
};
