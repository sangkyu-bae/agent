import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import ragToolService from '@/services/ragToolService';

export const useCollections = () =>
  useQuery({
    queryKey: queryKeys.ragTools.collections(),
    queryFn: ragToolService.getCollections,
    staleTime: 5 * 60 * 1000,
  });

export const useMetadataKeys = (collectionName?: string) =>
  useQuery({
    queryKey: queryKeys.ragTools.metadataKeys(collectionName),
    queryFn: () => ragToolService.getMetadataKeys(collectionName),
    enabled: !!collectionName,
    staleTime: 3 * 60 * 1000,
  });
