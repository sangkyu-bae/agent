import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toolCatalogService } from '@/services/toolCatalogService';
import { queryKeys } from '@/lib/queryKeys';
import type { CatalogTool } from '@/types/toolCatalog';

export const useToolCatalog = () =>
  useQuery<CatalogTool[]>({
    queryKey: queryKeys.toolCatalog.list(),
    queryFn: () =>
      toolCatalogService.getToolCatalog().then((r) => r.data.tools),
  });

// builtin-tools D9: 관리자 빌트인 토글 — 성공 시 카탈로그 캐시 무효화
export const useSetToolBuiltin = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ toolId, isBuiltin }: { toolId: string; isBuiltin: boolean }) =>
      toolCatalogService.setBuiltin(toolId, isBuiltin).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.toolCatalog.all });
    },
  });
};
