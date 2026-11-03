// agent-run-source-citations §2.2 — 재진입 시 메시지 이력과 인증 근거 API 를 병합한다.
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';

import { createWrapper } from '@/__tests__/mocks/wrapper';
import { server } from '@/__tests__/mocks/server';
import { useAgentSessionMessages } from './useChat';

const SOURCES_URL = '*/api/v1/conversations/agents/:agentId/sessions/:sessionId/sources';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const render = (agentId: string) =>
  renderHook(() => useAgentSessionMessages(agentId, 's1', '7'), {
    wrapper: createWrapper(),
  });

describe('useAgentSessionMessages + 세션 근거', () => {
  it('assistant 메시지에 근거를 병합한다', async () => {
    let sourcesCalls = 0;
    server.use(
      http.get(SOURCES_URL, ({ params }) => {
        sourcesCalls += 1;
        return HttpResponse.json({
          session_id: params.sessionId,
          items: [{
            message_id: 2,
            sources: [{ kind: 'web', source: '금리', content: '발췌', chunk_id: 'https://a', url: 'https://a' }],
          }],
        });
      }),
    );

    const { result } = render('agent-1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [user, assistant] = result.current.data ?? [];
    expect(user.sources).toBeUndefined();
    expect(assistant.sources?.[0]).toMatchObject({ kind: 'web', url: 'https://a' });
    expect(sourcesCalls).toBe(1);
  });

  it('근거 API 가 실패해도 메시지는 그대로 표시한다', async () => {
    server.use(http.get(SOURCES_URL, () => new HttpResponse(null, { status: 500 })));

    const { result } = render('agent-1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.map((m) => m.content)).toEqual(['이전 질문입니다', '이전 답변입니다']);
    expect(result.current.data?.every((m) => m.sources === undefined)).toBe(true);
  });

  it('일반 채팅(super) 세션은 근거 API 를 부르지 않는다', async () => {
    let sourcesCalls = 0;
    server.use(
      http.get(SOURCES_URL, () => {
        sourcesCalls += 1;
        return HttpResponse.json({ session_id: 's1', items: [] });
      }),
    );

    const { result } = render('super');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(sourcesCalls).toBe(0);
  });
});
