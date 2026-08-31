// multimodal-extractor Design §5.3 — 미리보기(저장 없음 → 뮤테이션으로 모델링)
import { useMutation } from '@tanstack/react-query';
import { multimodalService } from '@/services/multimodalService';

export const useMultimodalPreview = () =>
  useMutation({
    mutationFn: ({ file, debug }: { file: File; debug: boolean }) =>
      multimodalService.preview(file, debug),
  });
