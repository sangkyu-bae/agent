import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { middlewareService } from '@/services/middlewareService';
import { queryKeys } from '@/lib/queryKeys';
import type {
  MiddlewareCatalogItem,
  SetMiddlewareFlagsRequest,
} from '@/types/middleware';

export const useMiddlewareCatalog = () =>
  useQuery<MiddlewareCatalogItem[]>({
    queryKey: queryKeys.middlewareCatalog.list(),
    queryFn: () =>
      middlewareService.getMiddlewareCatalog().then((r) => r.data.middlewares),
  });

// builtin-middleware D10: 관리자 토글/설정 편집 — 성공 시 카탈로그 캐시 무효화
export const useSetMiddlewareFlags = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      middlewareType,
      body,
    }: {
      middlewareType: string;
      body: SetMiddlewareFlagsRequest;
    }) =>
      middlewareService.setMiddlewareFlags(middlewareType, body).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.middlewareCatalog.all,
      });
    },
  });
};
