// agent-kb-quick-setup Design §5.3 — 기본 임베딩 모델 조회(사용자/관리자)·교체
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { kbQuickSetupService } from '@/services/kbQuickSetupService';
import type { AdminKbDefaultsUpdateRequest } from '@/types/kbQuickSetup';

export const useKbDefaults = () =>
  useQuery({
    queryKey: queryKeys.kbDefaults.user(),
    queryFn: kbQuickSetupService.getKbDefaults,
    staleTime: 60 * 1000,
  });

export const useAdminKbDefaults = () =>
  useQuery({
    queryKey: queryKeys.kbDefaults.admin(),
    queryFn: kbQuickSetupService.getAdminKbDefaults,
  });

export const useUpdateAdminKbDefaults = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: AdminKbDefaultsUpdateRequest) =>
      kbQuickSetupService.updateAdminKbDefaults(req),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.kbDefaults.admin(), data);
      // 사용자 축약 응답은 형태가 달라 캐시 직접 반영 대신 무효화
      void qc.invalidateQueries({ queryKey: queryKeys.kbDefaults.user() });
    },
  });
};
