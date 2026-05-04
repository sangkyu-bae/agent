import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentSubscriptionService } from '@/services/agentSubscriptionService';
import { queryKeys } from '@/lib/queryKeys';
import type { MyAgentsParams, ForkAgentRequest } from '@/types/agent';

export const useMyAgents = (params?: MyAgentsParams) =>
  useQuery({
    queryKey: queryKeys.agent.my(params),
    queryFn: () =>
      agentSubscriptionService.getMyAgents(params).then((r) => r.data),
  });

export const useSubscribeAgent = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) =>
      agentSubscriptionService.subscribe(agentId).then((r) => r.data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.all }),
  });
};

export const useUnsubscribeAgent = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) =>
      agentSubscriptionService.unsubscribe(agentId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.all }),
  });
};

export const useTogglePin = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      agentId,
      is_pinned,
    }: {
      agentId: string;
      is_pinned: boolean;
    }) =>
      agentSubscriptionService
        .updateSubscription(agentId, { is_pinned })
        .then((r) => r.data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.all }),
  });
};

export const useForkAgent = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      agentId,
      data,
    }: {
      agentId: string;
      data?: ForkAgentRequest;
    }) =>
      agentSubscriptionService.forkAgent(agentId, data).then((r) => r.data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.all }),
  });
};
