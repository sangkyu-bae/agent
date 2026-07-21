// agent-eval-gate: 답변 평가 TanStack Query 훅.
import { useMutation, useQuery } from '@tanstack/react-query';

import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { messageFeedbackService } from '@/services/messageFeedbackService';
import type { Rating } from '@/types/messageFeedback';

export const useMessageFeedback = (messageId: number | null) =>
  useQuery({
    queryKey: queryKeys.eval.feedback(messageId ?? 0),
    queryFn: () => messageFeedbackService.get(messageId as number),
    enabled: !!messageId,
  });

export const useSubmitFeedback = (messageId: number) =>
  useMutation({
    mutationFn: ({ rating, comment }: { rating: Rating; comment?: string }) =>
      messageFeedbackService.submit(messageId, rating, comment),
    onSuccess: (data) => {
      // 서버가 취소/갱신 후 최신 값 반환 → 캐시 갱신
      queryClient.setQueryData(queryKeys.eval.feedback(messageId), data);
      queryClient.invalidateQueries({ queryKey: queryKeys.eval.agents() });
    },
  });

// admin
export const useAgentEvalStats = () =>
  useQuery({
    queryKey: queryKeys.eval.agents(),
    queryFn: () => messageFeedbackService.getAgentStats(),
  });

export const useRecentNegativeFeedback = () =>
  useQuery({
    queryKey: queryKeys.eval.recentNegative(),
    queryFn: () => messageFeedbackService.getRecentNegative(),
  });
