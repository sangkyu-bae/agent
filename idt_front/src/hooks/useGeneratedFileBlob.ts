// Design Ref: document-file-preview §5.3 — 산출 파일 blob 조회 (모달이 열릴 때만)
import { useQuery } from '@tanstack/react-query';

import { queryKeys } from '@/lib/queryKeys';
import { documentExtractorService } from '@/services/documentExtractorService';
import { ApiError } from '@/services/api/ApiError';

/** 엑셀(staleTime 0)과 달리 파일 전체를 받으므로, 같은 대화에서 다시 열 때 재다운로드를 피한다 (Plan FR-03). */
const BLOB_CACHE_MS = 5 * 60_000;

/**
 * fileId가 null이면 조회하지 않는다 (모달 닫힘).
 * 4xx(만료·권한)는 재시도해도 결과가 같으므로 재시도하지 않는다 (useExcelPreview와 동일).
 */
export const useGeneratedFileBlob = (fileId: string | null) =>
  useQuery({
    queryKey: queryKeys.generatedFile.blob(fileId ?? ''),
    queryFn: () => documentExtractorService.fetchGeneratedFileBlob(fileId as string),
    enabled: !!fileId,
    staleTime: BLOB_CACHE_MS,
    gcTime: BLOB_CACHE_MS,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
        return false;
      }
      return failureCount < 1;
    },
  });
