import { renderHook, waitFor } from '@testing-library/react';
import { act } from 'react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import {
  useGeneralChat,
  useConversationSessions,
  useSessionMessages,
} from '@/hooks/useChat';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useGeneralChat', () => {
  it('성공 시 answer를 반환한다', async () => {
    const { result } = renderHook(() => useGeneralChat(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate({
        user_id: 'user-001',
        session_id: 'session-abc',
        message: '안녕하세요',
        top_k: 5,
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.answer).toBe('테스트 답변입니다.');
  });

  it('성공 시 sources 배열을 반환한다', async () => {
    const { result } = renderHook(() => useGeneralChat(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate({
        user_id: 'user-001',
        session_id: 'session-abc',
        message: '안녕하세요',
        top_k: 5,
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.sources).toHaveLength(1);
    expect(result.current.data?.sources[0].chunk_id).toBe('c-001');
  });

  it('성공 시 session_id를 반환한다', async () => {
    const { result } = renderHook(() => useGeneralChat(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate({
        user_id: 'user-001',
        session_id: 'session-abc',
        message: '안녕하세요',
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.session_id).toBe('session-abc');
  });
});

describe('useConversationSessions (CHAT-HIST-001)', () => {
  it('H1: userId 제공 시 세션 목록을 반환한다', async () => {
    const { result } = renderHook(() => useConversationSessions('user-001'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].id).toBe('s1');
    expect(result.current.data?.[0].title).toBe('안녕');
  });

  it('H2: userId 없으면 쿼리를 비활성화한다', () => {
    const { result } = renderHook(() => useConversationSessions(undefined), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(result.current.isLoading).toBe(false);
  });

  it('H3: 빈 배열 응답을 처리한다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.CONVERSATION_SESSIONS}`, () =>
        HttpResponse.json({ user_id: 'user-001', sessions: [] }),
      ),
    );

    const { result } = renderHook(() => useConversationSessions('user-001'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(0);
  });

  it('H4: 500 에러 시 isError true', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.CONVERSATION_SESSIONS}`, () =>
        HttpResponse.json({ detail: 'server error' }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useConversationSessions('user-001'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useSessionMessages (CHAT-HIST-001)', () => {
  it('M1: 정상 응답 시 메시지 배열을 반환한다', async () => {
    const { result } = renderHook(
      () => useSessionMessages('s1', 'user-001'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].id).toBe('1');
    expect(typeof result.current.data?.[0].id).toBe('string');
  });

  it('M2: sessionId null 이면 비활성화', () => {
    const { result } = renderHook(
      () => useSessionMessages(null, 'user-001'),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
  });

  it('M3: 같은 (sessionId, userId) 로 두 번 마운트해도 fetch 는 1회만 수행된다 (staleTime 캐시 재사용)', async () => {
    let callCount = 0;
    server.use(
      http.get('*/api/v1/conversations/sessions/:sessionId/messages', ({ params, request }) => {
        callCount += 1;
        const url = new URL(request.url);
        return HttpResponse.json({
          user_id: url.searchParams.get('user_id'),
          session_id: params.sessionId,
          messages: [
            { id: 1, role: 'user', content: '캐시 테스트', turn_index: 1, created_at: '2026-04-17T10:00:00Z' },
          ],
        });
      }),
    );

    const wrapper = createWrapper();

    const { result: r1 } = renderHook(
      () => useSessionMessages('s1', 'user-001'),
      { wrapper },
    );
    await waitFor(() => expect(r1.current.isSuccess).toBe(true));
    expect(callCount).toBe(1);

    // Second mount with same key shares the same QueryClient (same wrapper instance)
    const { result: r2 } = renderHook(
      () => useSessionMessages('s1', 'user-001'),
      { wrapper },
    );
    await waitFor(() => expect(r2.current.isSuccess).toBe(true));

    // staleTime 60_000 — cache still fresh, no second fetch
    expect(callCount).toBe(1);
  });

  it('M4: 빈 배열 응답을 처리한다', async () => {
    server.use(
      http.get(
        '*/api/v1/conversations/sessions/:sessionId/messages',
        ({ params, request }) => {
          const url = new URL(request.url);
          return HttpResponse.json({
            user_id: url.searchParams.get('user_id'),
            session_id: params.sessionId,
            messages: [],
          });
        },
      ),
    );

    const { result } = renderHook(
      () => useSessionMessages('s1', 'user-001'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(0);
  });
});
