import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { chunkingProfileService } from '@/services/chunkingProfileService';
import { ApiError } from '@/services/api/ApiError';
import type { ChunkingProfileRequest } from '@/types/chunkingProfile';

export const useChunkingProfiles = () => {
  return useQuery({
    queryKey: queryKeys.chunkingProfiles.list(),
    queryFn: () => chunkingProfileService.getChunkingProfiles(),
    staleTime: 5 * 60 * 1000,
    select: (data) => data.profiles,
  });
};

/** 404(타 관리자 선삭제 등) 실패 시 목록을 재동기화한다 (Design D9) */
const invalidateOn404 = (qc: QueryClient, err: unknown) => {
  if (err instanceof ApiError && err.status === 404) {
    qc.invalidateQueries({ queryKey: queryKeys.chunkingProfiles.all });
  }
};

export const useCreateChunkingProfile = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ChunkingProfileRequest) =>
      chunkingProfileService.createChunkingProfile(data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.chunkingProfiles.all }),
  });
};

export const useUpdateChunkingProfile = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ChunkingProfileRequest }) =>
      chunkingProfileService.updateChunkingProfile(id, data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.chunkingProfiles.all }),
    onError: (err) => invalidateOn404(qc, err),
  });
};

export const useSetDefaultChunkingProfile = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      chunkingProfileService.setDefaultChunkingProfile(id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.chunkingProfiles.all }),
    onError: (err) => invalidateOn404(qc, err),
  });
};

export const useDeleteChunkingProfile = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      chunkingProfileService.deleteChunkingProfile(id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.chunkingProfiles.all }),
    onError: (err) => invalidateOn404(qc, err),
  });
};
