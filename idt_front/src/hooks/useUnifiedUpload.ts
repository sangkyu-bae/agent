import { useMutation } from '@tanstack/react-query';
import unifiedUploadService from '@/services/unifiedUploadService';
import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import type { UnifiedUploadParams, UnifiedUploadResponse } from '@/types/unifiedUpload';

interface UseUnifiedUploadOptions {
  onSuccess?: (data: UnifiedUploadResponse) => void;
  onError?: (error: Error) => void;
}

export const useUnifiedUpload = (
  collectionName: string,
  options?: UseUnifiedUploadOptions,
) =>
  useMutation({
    mutationFn: ({ file, params }: { file: File; params: UnifiedUploadParams }) =>
      unifiedUploadService.uploadDocument(file, params),
    onSuccess: (data) => {
      if (data.status !== 'failed') {
        queryClient.invalidateQueries({
          queryKey: queryKeys.collections.documents(collectionName),
        });
      }
      options?.onSuccess?.(data);
    },
    onError: (error: Error) => {
      options?.onError?.(error);
    },
  });
