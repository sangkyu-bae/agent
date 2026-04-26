import { useQuery } from '@tanstack/react-query';
import { embeddingModelService } from '@/services/embeddingModelService';
import { queryKeys } from '@/lib/queryKeys';

export const useEmbeddingModelList = () =>
  useQuery({
    queryKey: queryKeys.embeddingModels.list(),
    queryFn: embeddingModelService.getEmbeddingModels,
  });
