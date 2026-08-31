// multimodal-extractor Design §5.3 — 설정 조회/전체 교체/연결 테스트
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { multimodalService } from '@/services/multimodalService';
import type { MultimodalSettingsRequest } from '@/types/multimodal';

export const useMultimodalSettings = () =>
  useQuery({
    queryKey: queryKeys.multimodal.settings(),
    queryFn: multimodalService.getSettings,
  });

export const useUpdateMultimodalSettings = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: MultimodalSettingsRequest) => multimodalService.updateSettings(req),
    // PUT 응답이 최신 상태이므로 캐시에 직접 반영 (재조회 1회 절약)
    onSuccess: (data) => qc.setQueryData(queryKeys.multimodal.settings(), data),
  });
};

export const useTestMultimodalConnection = () =>
  useMutation({
    mutationFn: (image?: File | null) => multimodalService.testConnection(image),
  });
