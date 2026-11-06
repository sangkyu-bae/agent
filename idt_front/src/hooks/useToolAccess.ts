import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { toolAccessService } from '@/services/toolAccessService';

// tool-access-control §5 — 관리자 도구 권한 조회·전체 교체.

export const useDefaultToolAccess = () =>
  useQuery({
    queryKey: queryKeys.admin.toolAccessDefault(),
    queryFn: toolAccessService.getDefault,
  });

export const useDepartmentToolAccess = (deptId: string | null) =>
  useQuery({
    queryKey: queryKeys.admin.toolAccessDepartment(deptId ?? ''),
    queryFn: () => toolAccessService.getDepartment(deptId as string),
    enabled: !!deptId,
  });

export const useUserToolAccess = (userId: number | null) =>
  useQuery({
    queryKey: queryKeys.admin.toolAccessUser(userId ?? 0),
    queryFn: () => toolAccessService.getUser(userId as number),
    enabled: userId !== null,
  });

export type ToolAccessTarget =
  | { kind: 'default' }
  | { kind: 'department'; id: string }
  | { kind: 'user'; id: number };

/**
 * 대상 하나의 허용 도구를 전체 교체한다.
 * 기본 세트·부서 변경은 사용자 상속분에도 영향을 주므로 toolAccess 전체를 무효화한다.
 */
export const useReplaceToolAccess = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ target, toolIds }: { target: ToolAccessTarget; toolIds: string[] }) => {
      if (target.kind === 'department') return toolAccessService.replaceDepartment(target.id, toolIds);
      if (target.kind === 'user') return toolAccessService.replaceUser(target.id, toolIds);
      return toolAccessService.replaceDefault(toolIds);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.toolAccess() });
    },
  });
};
