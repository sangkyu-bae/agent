// agent-memory: 사용자 메모리 TanStack Query 훅.
import { useMutation, useQuery } from '@tanstack/react-query';

import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { memoryService } from '@/services/memoryService';
import type {
  CreateMemoryRequest,
  CreateOrgMemoryRequest,
  UpdateMemoryRequest,
} from '@/types/memory';

const invalidateMemories = () =>
  queryClient.invalidateQueries({ queryKey: queryKeys.memories.all });

export const useMemories = (status?: 'active' | 'pending') =>
  useQuery({
    queryKey: queryKeys.memories.list(status),
    queryFn: () => memoryService.getMemories(status),
  });

// agent-memory-extraction: 추출 후보 승인/거부 — active·pending 동시 갱신
export const useApproveMemory = () =>
  useMutation({
    mutationFn: (id: number) => memoryService.approve(id),
    onSuccess: invalidateMemories,
  });

export const useRejectMemory = () =>
  useMutation({
    mutationFn: (id: number) => memoryService.reject(id),
    onSuccess: invalidateMemories,
  });

// agent-memory-org-scope: 부서 공유 메모리
export const useOrgMemories = () =>
  useQuery({
    queryKey: queryKeys.memories.org(),
    queryFn: () => memoryService.getOrgMemories(),
  });

export const useCreateOrgMemory = () =>
  useMutation({
    mutationFn: (data: CreateOrgMemoryRequest) => memoryService.createOrg(data),
    onSuccess: invalidateMemories,
  });

export const usePromoteMemory = () =>
  useMutation({
    mutationFn: ({ id, deptId }: { id: number; deptId: string }) =>
      memoryService.promote(id, deptId),
    onSuccess: invalidateMemories,
  });

export const useCreateMemory = () =>
  useMutation({
    mutationFn: (data: CreateMemoryRequest) => memoryService.create(data),
    onSuccess: invalidateMemories,
  });

export const useUpdateMemory = () =>
  useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateMemoryRequest }) =>
      memoryService.update(id, data),
    onSuccess: invalidateMemories,
  });

export const useDeleteMemory = () =>
  useMutation({
    mutationFn: (id: number) => memoryService.remove(id),
    onSuccess: invalidateMemories,
  });
