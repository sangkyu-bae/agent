import { useQuery, useMutation } from '@tanstack/react-query';
import { agentBuilderService } from '@/services/agentBuilderService';
import { queryKeys } from '@/lib/queryKeys';
import { queryClient } from '@/lib/queryClient';
import type { AgentListResponse, AgentDetail } from '@/types/agentStore';
import type {
  CreateBuilderAgentRequest,
  CreateBuilderAgentResponse,
  UpdateBuilderAgentRequest,
  UpdateBuilderAgentResponse,
} from '@/types/agentBuilder';

interface ListParams {
  search?: string;
  page?: number;
  size?: number;
}

export const useMyBuilderAgents = (params?: ListParams) =>
  useQuery<AgentListResponse>({
    queryKey: queryKeys.agentBuilder.list(params),
    queryFn: () => agentBuilderService.listMine(params).then((r) => r.data),
  });

export const useBuilderAgentDetail = (agentId: string | null) =>
  useQuery<AgentDetail>({
    queryKey: queryKeys.agentBuilder.detail(agentId ?? ''),
    queryFn: () => agentBuilderService.getDetail(agentId!).then((r) => r.data),
    enabled: !!agentId,
  });

export const useCreateBuilderAgent = () =>
  useMutation<CreateBuilderAgentResponse, Error, CreateBuilderAgentRequest>({
    mutationFn: (data) =>
      agentBuilderService.create(data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentBuilder.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

interface UpdateVars {
  agentId: string;
  data: UpdateBuilderAgentRequest;
}

export const useUpdateBuilderAgent = () =>
  useMutation<UpdateBuilderAgentResponse, Error, UpdateVars>({
    mutationFn: ({ agentId, data }) =>
      agentBuilderService.update(agentId, data).then((r) => r.data),
    onSuccess: (_data, { agentId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentBuilder.all });
      queryClient.invalidateQueries({
        queryKey: queryKeys.agentStore.detail(agentId),
      });
    },
  });

export const useDeleteBuilderAgent = () =>
  useMutation<void, Error, string>({
    mutationFn: (agentId) =>
      agentBuilderService.delete(agentId).then(() => undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentBuilder.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });
