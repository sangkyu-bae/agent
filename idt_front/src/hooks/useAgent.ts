import { useQuery, useMutation } from '@tanstack/react-query';
import { agentService } from '@/services/agentService';
import { queryKeys } from '@/lib/queryKeys';
import type { RunAgentRequest, AgentStatus } from '@/types/agent';

/** 폴링을 중단하는 완료/에러 상태 목록 */
const TERMINAL_STATUSES: AgentStatus[] = ['idle', 'error'];

/** Agent 실행 상태 폴링 (runId 없으면 비활성) */
export const useAgentRunStatus = (runId: string | null) =>
  useQuery({
    queryKey: queryKeys.agent.run(runId ?? '_disabled'),
    queryFn: () => agentService.getRunStatus(runId as string).then((r) => r.data),
    enabled: !!runId,
    refetchInterval: (query) => {
      // ApiResponse<AgentRun>.data.status
      const status = query.state.data?.data?.status as AgentStatus | undefined;
      // 완료(idle 복귀) 또는 에러 상태면 폴링 중단
      if (!status || TERMINAL_STATUSES.includes(status)) return false;
      return 2000; // 2초마다 폴링
    },
  });

/** Agent 실행 시작 뮤테이션 */
export const useRunAgent = () =>
  useMutation({
    mutationFn: (payload: RunAgentRequest) =>
      agentService.run(payload).then((r) => r.data),
  });
