import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import {
  useAgentSkills,
  useAttachSkill,
  useDetachSkill,
} from './useAgentSkills';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useAgentSkills hooks', () => {
  it('useAgentSkills: agentId가 null이면 호출하지 않는다', () => {
    const { result } = renderHook(() => useAgentSkills(null), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('useAgentSkills: 부착 목록을 불러온다', async () => {
    const { result } = renderHook(() => useAgentSkills('agent-1'), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total).toBe(1);
    expect(result.current.data?.max_attachable).toBe(3);
    expect(result.current.data?.skills[0].skill_id).toBe('skill-1');
  });

  it('useAttachSkill: 부착 성공', async () => {
    const { result } = renderHook(() => useAttachSkill('agent-1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate('skill-9');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.skill_id).toBe('skill-9');
    expect(result.current.data?.has_script).toBe(false);
  });

  it('useDetachSkill: 해제 성공', async () => {
    let detached = false;
    server.use(
      http.delete('*/api/v1/agents/:agentId/skills/:skillId', () => {
        detached = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { result } = renderHook(() => useDetachSkill('agent-1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate('skill-1');
    await waitFor(() => expect(detached).toBe(true));
  });
});
