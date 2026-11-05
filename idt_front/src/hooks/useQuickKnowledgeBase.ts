// agent-kb-quick-setup Design §5.3 — /quick 뮤테이션. 성공 시 KB 목록 캐시 무효화
// (빌더 KB 드롭다운·/knowledge-bases 목록이 자동 동기화, useCreateKnowledgeBase 와 동일 규칙).
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { kbQuickSetupService } from '@/services/kbQuickSetupService';
import type { QuickKbRequest, QuickKbResponse } from '@/types/kbQuickSetup';

export const useQuickKnowledgeBase = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: QuickKbRequest) => kbQuickSetupService.quickCreate(req),
    // 실패(타임아웃 등)여도 서버에는 KB 가 생겼을 수 있어 settled 에서 무효화한다
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBases.all });
    },
  });
};

/**
 * Check G1 — 전부 실패 후 재시도. /quick 을 다시 부르지 않고 이미 만들어진 KB 에
 * 파일만 다시 올린다(빈 KB 누적 방지). 결과 형태는 /quick 응답과 같다.
 */
export const useRetryKbUpload = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ kb, files }: { kb: QuickKbResponse; files: File[] }) =>
      kbQuickSetupService.retryUploadToKb(kb, files),
    onSettled: (_data, _err, vars) => {
      void qc.invalidateQueries({
        queryKey: queryKeys.knowledgeBases.documents(vars.kb.kb_id),
      });
    },
  });
};
