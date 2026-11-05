import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import { useUpdateBuilderAgent } from '@/hooks/useAgentBuilder';
import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { agentBuilderService } from '@/services/agentBuilderService';
import { createWrapper } from '@/__tests__/mocks/wrapper';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useUpdateBuilderAgent 무효화 (agent-edit-entry §2.4)', () => {
  it('U6: 저장 성공 시 채팅 사이드바가 쓰는 agent 키도 무효화한다', async () => {
    vi.spyOn(agentBuilderService, 'update').mockResolvedValue({
      data: { agent_id: 'agent-1' },
    } as Awaited<ReturnType<typeof agentBuilderService.update>>);
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useUpdateBuilderAgent(), {
      wrapper: createWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({ agentId: 'agent-1', data: { name: '새 이름' } });
    });

    const keys = invalidate.mock.calls.map(([filters]) => filters?.queryKey);
    expect(keys).toContainEqual(queryKeys.agent.all);
    expect(keys).toContainEqual(queryKeys.agentBuilder.all);
  });
});
