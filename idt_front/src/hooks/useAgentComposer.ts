import { useMutation } from '@tanstack/react-query';
import { agentComposerService } from '@/services/agentComposerService';
import type {
  ComposeAgentRequest,
  ComposeAgentDraftResponse,
} from '@/types/agentComposer';

// fix-agent-composer: compose는 무저장이라 캐시 무효화 없음 (mutation 단독)
export const useComposeAgent = () =>
  useMutation<ComposeAgentDraftResponse, Error, ComposeAgentRequest>({
    mutationFn: (data) =>
      agentComposerService.compose(data).then((r) => r.data),
  });
