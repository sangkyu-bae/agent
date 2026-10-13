// excel-preview Design §5.3 — 모달이 열릴 때만 조회 (FR-10, enabled 제어)
import { useQuery } from '@tanstack/react-query';

import { queryKeys } from '@/lib/queryKeys';
import { excelPreviewService } from '@/services/excelPreviewService';
import { ApiError } from '@/services/api/ApiError';

/**
 * fileId가 null이면 조회하지 않는다 (모달 닫힘).
 * 4xx(만료·권한·미지원·손상)는 재시도해도 결과가 같으므로 재시도하지 않는다.
 * TTL 1시간 파일이라 캐시 재사용 없이 열 때마다 재조회한다 (staleTime 0, gcTime 0).
 */
export const useExcelPreview = (fileId: string | null) =>
  useQuery({
    queryKey: queryKeys.excelPreview.detail(fileId ?? ''),
    queryFn: () => excelPreviewService.getPreview(fileId as string),
    enabled: !!fileId,
    staleTime: 0,
    gcTime: 0,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
        return false;
      }
      return failureCount < 1;
    },
  });
