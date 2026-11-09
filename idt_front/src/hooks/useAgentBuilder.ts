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
  AvailableSubAgentsResponse,
} from '@/types/agentBuilder';
import type { AgentDocumentTemplateResponse } from '@/types/documentExtractor';

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

export const useAvailableSubAgents = (enabled: boolean) =>
  useQuery<AvailableSubAgentsResponse>({
    queryKey: ['agentBuilder', 'available-sub-agents'],
    queryFn: () =>
      agentBuilderService.listAvailableSubAgents().then((r) => r.data),
    enabled,
  });

/**
 * extractor-template-preview §5.3: 문서추출기 저장 양식. 404 는 서비스가 null 로 바꾼다.
 * enabled 는 호출부가 "저장 양식 있음 + 드래프트 없음"으로 계산한다.
 */
export const useAgentDocumentTemplate = (agentId: string | null, enabled: boolean) =>
  useQuery<AgentDocumentTemplateResponse | null>({
    queryKey: queryKeys.agentBuilder.documentTemplate(agentId ?? ''),
    queryFn: () => agentBuilderService.getDocumentTemplate(agentId!),
    enabled: !!agentId && enabled,
    retry: false,
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
      // agent-edit-entry §2.4: 채팅 사이드바·헤더(useMyAgents, agent.my)도 갱신
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.all });
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
