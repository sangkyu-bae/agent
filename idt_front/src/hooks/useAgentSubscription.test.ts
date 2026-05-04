import { renderHook, waitFor, act } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import {
  useMyAgents,
  useSubscribeAgent,
  useUnsubscribeAgent,
  useTogglePin,
  useForkAgent,
} from '@/hooks/useAgentSubscription';
import { toAgentSummary } from '@/services/agentSubscriptionService';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import type { MyAgent } from '@/types/agent';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const mockMyAgentsResponse = {
  agents: [
    {
      agent_id: 'agent-1',
      name: '사내 문서 RAG',
      description: '사내 문서 검색',
      source_type: 'owned',
      visibility: 'private',
      temperature: 0.7,
      owner_user_id: 'user-1',
      forked_from: null,
      is_pinned: false,
      created_at: '2026-05-01T00:00:00Z',
    },
    {
      agent_id: 'agent-2',
      name: '트레이딩 봇',
      description: '투자 분석',
      source_type: 'subscribed',
      visibility: 'public',
      temperature: 0.5,
      owner_user_id: 'user-2',
      forked_from: null,
      is_pinned: true,
      created_at: '2026-05-02T00:00:00Z',
    },
  ],
  total: 2,
  page: 1,
  size: 20,
};

describe('useMyAgents', () => {
  it('SUB-1: 정상 응답 시 agents 배열 반환', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.AGENT_MY}`, () =>
        HttpResponse.json(mockMyAgentsResponse),
      ),
    );

    const { result } = renderHook(() => useMyAgents(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.agents).toHaveLength(2);
    expect(result.current.data?.agents[0].agent_id).toBe('agent-1');
    expect(result.current.data?.agents[0].source_type).toBe('owned');
    expect(result.current.data?.agents[1].is_pinned).toBe(true);
  });

  it('SUB-2: 에러 시 isError: true', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.AGENT_MY}`, () =>
        HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useMyAgents(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useSubscribeAgent', () => {
  it('SUB-3: 구독 성공 후 응답 반환', async () => {
    const { result } = renderHook(() => useSubscribeAgent(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate('agent-1');
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.subscription_id).toBe('sub-1');
    expect(result.current.data?.agent_id).toBe('agent-1');
  });
});

describe('useUnsubscribeAgent', () => {
  it('SUB-4: 204 응답 정상 처리', async () => {
    const { result } = renderHook(() => useUnsubscribeAgent(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate('agent-1');
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useTogglePin', () => {
  it('SUB-5: is_pinned 토글 후 응답 반환', async () => {
    const { result } = renderHook(() => useTogglePin(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({ agentId: 'agent-1', is_pinned: true });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.is_pinned).toBe(true);
  });
});

describe('useForkAgent', () => {
  it('SUB-6: 포크 성공', async () => {
    const { result } = renderHook(() => useForkAgent(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({ agentId: 'agent-1' });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.forked_from).toBe('agent-1');
  });
});

describe('toAgentSummary', () => {
  it('SUB-7: MyAgent → AgentSummary 올바른 매핑', () => {
    const myAgent: MyAgent = {
      agent_id: 'agent-1',
      name: '사내 문서 RAG',
      description: '사내 문서 검색',
      source_type: 'owned',
      visibility: 'private',
      temperature: 0.7,
      owner_user_id: 'user-1',
      forked_from: null,
      is_pinned: false,
      created_at: '2026-05-01T00:00:00Z',
    };

    const summary = toAgentSummary(myAgent);

    expect(summary.id).toBe('agent-1');
    expect(summary.name).toBe('사내 문서 RAG');
    expect(summary.description).toBe('사내 문서 검색');
    expect(summary.category).toBe('owned');
    expect(summary.isDefault).toBe(false);
  });
});
