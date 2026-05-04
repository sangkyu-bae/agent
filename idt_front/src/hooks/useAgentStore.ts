import { useQuery, useMutation } from '@tanstack/react-query';
import { agentStoreService } from '@/services/agentStoreService';
import { queryKeys } from '@/lib/queryKeys';
import { queryClient } from '@/lib/queryClient';
import type {
  AgentListParams,
  AgentListResponse,
  AgentDetail,
  SubscribeResponse,
  ForkAgentResponse,
  MyAgentListParams,
  MyAgentListResponse,
  ForkStatsResponse,
  PublishAgentRequest,
} from '@/types/agentStore';

export const useAgentList = (params: AgentListParams) =>
  useQuery<AgentListResponse>({
    queryKey: queryKeys.agentStore.list(params),
    queryFn: () => agentStoreService.getAgents(params).then((r) => r.data),
  });

export const useAgentDetail = (agentId: string | null) =>
  useQuery<AgentDetail>({
    queryKey: queryKeys.agentStore.detail(agentId ?? ''),
    queryFn: () => agentStoreService.getAgent(agentId!).then((r) => r.data),
    enabled: !!agentId,
  });

export const useMyAgents = (params: MyAgentListParams) =>
  useQuery<MyAgentListResponse>({
    queryKey: queryKeys.agentStore.my(params),
    queryFn: () => agentStoreService.getMyAgents(params).then((r) => r.data),
  });

export const useSubscribeAgent = () =>
  useMutation<SubscribeResponse, Error, string>({
    mutationFn: (agentId) =>
      agentStoreService.subscribe(agentId).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

export const useUnsubscribeAgent = () =>
  useMutation<void, Error, string>({
    mutationFn: (agentId) =>
      agentStoreService.unsubscribe(agentId).then(() => undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

export const useUpdateSubscription = () =>
  useMutation<SubscribeResponse, Error, { agentId: string; isPinned: boolean }>({
    mutationFn: ({ agentId, isPinned }) =>
      agentStoreService
        .updateSubscription(agentId, { is_pinned: isPinned })
        .then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

export const useForkAgent = () =>
  useMutation<ForkAgentResponse, Error, { agentId: string; name?: string }>({
    mutationFn: ({ agentId, name }) =>
      agentStoreService
        .fork(agentId, name ? { name } : undefined)
        .then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

export const usePublishAgent = () =>
  useMutation<void, Error, { agentId: string; body: PublishAgentRequest }>({
    mutationFn: ({ agentId, body }) =>
      agentStoreService.publishAgent(agentId, body).then(() => undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

export const useForkStats = (agentId: string | null) =>
  useQuery<ForkStatsResponse>({
    queryKey: queryKeys.agentStore.forkStats(agentId ?? ''),
    queryFn: () => agentStoreService.getForkStats(agentId!).then((r) => r.data),
    enabled: !!agentId,
  });
