import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { mcpServerService } from '@/services/mcpServerService';
import { queryKeys } from '@/lib/queryKeys';
import type {
  RegisterMcpServerRequest,
  UpdateMcpServerRequest,
} from '@/types/mcpServer';

export const useMcpServers = () =>
  useQuery({
    queryKey: queryKeys.admin.mcpServers(),
    queryFn: mcpServerService.getServers,
  });

export const useCreateMcpServer = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RegisterMcpServerRequest) =>
      mcpServerService.createServer(data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.admin.mcpServers() }),
  });
};

export const useUpdateMcpServer = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateMcpServerRequest }) =>
      mcpServerService.updateServer(id, data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.admin.mcpServers() }),
  });
};

export const useDeleteMcpServer = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => mcpServerService.deleteServer(id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.admin.mcpServers() }),
  });
};

// 테스트 결과는 컴포넌트 로컬 상태로 표시 — 캐시 무효화 불필요
export const useTestMcpConnection = () =>
  useMutation({
    mutationFn: (id: string) => mcpServerService.testConnection(id),
  });
