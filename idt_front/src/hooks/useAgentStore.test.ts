import { renderHook, waitFor, act } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import {
  useAgentList,
  useAgentDetail,
  useMyAgents,
  useSubscribeAgent,
  useUnsubscribeAgent,
  useForkAgent,
  usePublishAgent,
  useForkStats,
} from '@/hooks/useAgentStore';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useAgentList', () => {
  it('AS-1: 공개 에이전트 목록 조회 성공', async () => {
    const { result } = renderHook(
      () => useAgentList({ scope: 'public', page: 1, size: 20 }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.agents).toHaveLength(2);
    expect(result.current.data?.total).toBe(2);
  });

  it('AS-2: 검색 필터 적용', async () => {
    const { result } = renderHook(
      () => useAgentList({ scope: 'public', search: '코드', page: 1, size: 20 }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.agents).toHaveLength(1);
    expect(result.current.data?.agents[0].name).toBe('코드 리뷰어');
  });

  it('AS-3: 빈 목록 처리', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.AGENT_STORE_LIST}`, () =>
        HttpResponse.json({ agents: [], total: 0, page: 1, size: 20 }),
      ),
    );

    const { result } = renderHook(
      () => useAgentList({ scope: 'public', page: 1, size: 20 }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.agents).toHaveLength(0);
  });

  it('AS-4: 서버 에러 시 isError', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.AGENT_STORE_LIST}`, () =>
        HttpResponse.json({ detail: 'server error' }, { status: 500 }),
      ),
    );

    const { result } = renderHook(
      () => useAgentList({ scope: 'public', page: 1, size: 20 }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useAgentDetail', () => {
  it('AS-5: 상세 조회 성공', async () => {
    const { result } = renderHook(() => useAgentDetail('agent-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.agent_id).toBe('agent-1');
    expect(result.current.data?.name).toBe('문서 분석가');
    expect(result.current.data?.workers).toHaveLength(1);
  });

  it('AS-6: agentId가 null이면 enabled=false', async () => {
    const { result } = renderHook(() => useAgentDetail(null), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
  });

  it('AS-7: 404 에러 처리', async () => {
    server.use(
      http.get('*/api/v1/agents/:agentId', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 }),
      ),
    );

    const { result } = renderHook(() => useAgentDetail('unknown'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useMyAgents', () => {
  it('AS-8: 내 에이전트 목록 조회 성공', async () => {
    const { result } = renderHook(
      () => useMyAgents({ filter: 'all', page: 1, size: 20 }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.agents).toHaveLength(1);
    expect(result.current.data?.agents[0].source_type).toBe('owned');
  });
});

describe('useSubscribeAgent', () => {
  it('AS-9: 구독 성공', async () => {
    const { result } = renderHook(() => useSubscribeAgent(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate('agent-1');
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.agent_id).toBe('agent-1');
    expect(result.current.data?.subscription_id).toBe('sub-1');
  });

  it('AS-10: 409 이미 구독 중', async () => {
    server.use(
      http.post('*/api/v1/agents/:agentId/subscribe', () =>
        HttpResponse.json(
          { detail: '이미 구독 중인 에이전트입니다' },
          { status: 409 },
        ),
      ),
    );

    const { result } = renderHook(() => useSubscribeAgent(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate('agent-1');
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useUnsubscribeAgent', () => {
  it('AS-11: 구독 해제 성공', async () => {
    const { result } = renderHook(() => useUnsubscribeAgent(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate('agent-1');
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useForkAgent', () => {
  it('AS-12: 포크 성공', async () => {
    const { result } = renderHook(() => useForkAgent(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({ agentId: 'agent-1' });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.forked_from).toBe('agent-1');
    expect(result.current.data?.agent_id).toBe('forked-1');
  });

  it('AS-13: 포크 이름 지정', async () => {
    const { result } = renderHook(() => useForkAgent(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({ agentId: 'agent-1', name: '커스텀 이름' });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('usePublishAgent', () => {
  it('AS-14: 공개 등록 성공', async () => {
    server.use(
      http.patch('*/api/v1/agents/:agentId', () =>
        new HttpResponse(null, { status: 200 }),
      ),
    );

    const { result } = renderHook(() => usePublishAgent(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        agentId: 'my-1',
        body: { visibility: 'public' },
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useForkStats', () => {
  it('AS-15: 통계 조회 성공', async () => {
    const { result } = renderHook(() => useForkStats('agent-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.fork_count).toBe(5);
    expect(result.current.data?.subscriber_count).toBe(12);
  });

  it('AS-16: agentId가 null이면 enabled=false', async () => {
    const { result } = renderHook(() => useForkStats(null), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
  });
});
