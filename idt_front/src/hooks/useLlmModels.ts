import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { llmModelService } from '@/services/llmModelService';
import { ApiError } from '@/services/api/ApiError';
import type {
  CreateLlmModelRequest,
  UpdateLlmModelPricingRequest,
  UpdateLlmModelRequest,
} from '@/types/llmModel';

export const useLlmModels = (includeInactive = false) => {
  return useQuery({
    queryKey: queryKeys.llmModels.list(includeInactive),
    queryFn: () => llmModelService.getLlmModels(includeInactive),
    staleTime: 5 * 60 * 1000,
    select: (data) => data.models,
    // includeInactive 토글 시 이전 목록을 유지해 테이블 깜빡임 방지 (Design §6)
    placeholderData: keepPreviousData,
  });
};

/** 404(타 관리자 선삭제 등) 실패 시 목록을 재동기화한다 (Design §4.3) */
const invalidateOn404 = (qc: QueryClient, err: unknown) => {
  if (err instanceof ApiError && err.status === 404) {
    qc.invalidateQueries({ queryKey: queryKeys.llmModels.all });
  }
};

// llm-register: 어드민 뮤테이션 — 성공 시 llmModels.all invalidate
// (어드민 목록 list(true)와 에이전트 빌더 list(false)를 함께 갱신)

export const useCreateLlmModel = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateLlmModelRequest) =>
      llmModelService.createLlmModel(data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.llmModels.all }),
  });
};

export const useUpdateLlmModel = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateLlmModelRequest }) =>
      llmModelService.updateLlmModel(id, data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.llmModels.all }),
    onError: (err) => invalidateOn404(qc, err),
  });
};

export const useUpdateLlmModelPricing = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: UpdateLlmModelPricingRequest;
    }) => llmModelService.updateLlmModelPricing(id, data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.llmModels.all }),
    onError: (err) => invalidateOn404(qc, err),
  });
};

export const useDeactivateLlmModel = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => llmModelService.deactivateLlmModel(id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.llmModels.all }),
    onError: (err) => invalidateOn404(qc, err),
  });
};
