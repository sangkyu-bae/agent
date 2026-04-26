import { useQuery } from '@tanstack/react-query';
import { toolCatalogService } from '@/services/toolCatalogService';
import { queryKeys } from '@/lib/queryKeys';
import type { CatalogTool } from '@/types/toolCatalog';

export const useToolCatalog = () =>
  useQuery<CatalogTool[]>({
    queryKey: queryKeys.toolCatalog.list(),
    queryFn: () =>
      toolCatalogService.getToolCatalog().then((r) => r.data.tools),
  });
