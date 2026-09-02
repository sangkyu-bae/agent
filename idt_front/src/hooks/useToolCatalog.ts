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

/**
 * mcp-tool-auto-sync FR-11: MCP 서버별 도구 재동기화.
 *
 * 등록/수정 시 자동 sync가 실패했을 때의 복구 경로다. 성공하면 도구 카탈로그
 * 캐시를 무효화해 도구 선택창에 즉시 반영시킨다.
 */
export const useSyncMcpTools = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mcpServerId: string) =>
      toolCatalogService.syncMcpTools(mcpServerId).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.toolCatalog.all });
    },
  });
};
