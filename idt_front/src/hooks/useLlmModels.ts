import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { llmModelService } from '@/services/llmModelService';

export const useLlmModels = (includeInactive = false) => {
  return useQuery({
    queryKey: queryKeys.llmModels.list(includeInactive),
    queryFn: () => llmModelService.getLlmModels(includeInactive),
    staleTime: 5 * 60 * 1000,
    select: (data) => data.models,
  });
};
