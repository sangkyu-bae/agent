// answer-citation-verification Design §5.3 — 근거 판정 모델 설정 조회/저장
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { groundingJudgeService } from '@/services/groundingJudgeService';
import type { GroundingJudgeSettingRequest } from '@/types/groundingJudge';

export const useGroundingJudgeSetting = () =>
  useQuery({
    queryKey: queryKeys.groundingJudge.settings(),
    queryFn: groundingJudgeService.getSetting,
  });

export const useUpdateGroundingJudgeSetting = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: GroundingJudgeSettingRequest) => groundingJudgeService.updateSetting(req),
    // PUT 응답이 실제 적용 모델까지 담은 최신 상태라 캐시에 바로 반영한다.
    onSuccess: (data) => qc.setQueryData(queryKeys.groundingJudge.settings(), data),
  });
};
