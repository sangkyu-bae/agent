// agent-run-tool-trace §2.2 — 재진입 시 메시지 이력과 세션 도구 실행 내역을 병합한다.
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';

import { createWrapper } from '@/__tests__/mocks/wrapper';
import { server } from '@/__tests__/mocks/server';
import { useAgentSessionMessages } from './useChat';

const TRACES_URL = '*/api/v1/conversations/agents/:agentId/sessions/:sessionId/tool-traces';
const SOURCES_URL = '*/api/v1/conversations/agents/:agentId/sessions/:sessionId/sources';
const TRACE = {
  omitted_count: 0,
  items: [{ seq: 1, kind: 'tool', label: 'list_inquiries', source: 'mcp', status: 'success' }],
};

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const render = (agentId: string) =>
  renderHook(() => useAgentSessionMessages(agentId, 's1', '7'), {
    wrapper: createWrapper(),
  });

describe('useAgentSessionMessages + 세션 도구 실행 내역', () => {
  it('assistant 메시지에 내역을 병합하고 세션당 1회만 부른다', async () => {
    let calls = 0;
    server.use(
      http.get(TRACES_URL, ({ params }) => {
        calls += 1;
        return HttpResponse.json({
          session_id: params.sessionId,
          items: [{ message_id: 2, tool_trace: TRACE }],
        });
      }),
    );

    const { result } = render('agent-1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [user, assistant] = result.current.data ?? [];
    expect(user.toolTrace).toBeUndefined();
    expect(assistant.toolTrace).toEqual(TRACE);
    expect(calls).toBe(1);
  });

  it('근거와 내역을 함께 병합한다', async () => {
    server.use(
      http.get(TRACES_URL, () =>
        HttpResponse.json({ session_id: 's1', items: [{ message_id: 2, tool_trace: TRACE }] }),
      ),
      http.get(SOURCES_URL, () =>
        HttpResponse.json({
          session_id: 's1',
          items: [{ message_id: 2, sources: [{ kind: 'mcp', source: '도구', content: '발췌', chunk_id: 'c' }] }],
        }),
      ),
    );

    const { result } = render('agent-1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const assistant = result.current.data?.[1];
    expect(assistant?.sources).toHaveLength(1);
    expect(assistant?.toolTrace).toEqual(TRACE);
  });

  it('내역 API 가 실패해도 메시지는 그대로 표시한다', async () => {
    server.use(http.get(TRACES_URL, () => new HttpResponse(null, { status: 500 })));

    const { result } = render('agent-1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.map((m) => m.content)).toEqual(['이전 질문입니다', '이전 답변입니다']);
    expect(result.current.data?.every((m) => m.toolTrace === undefined)).toBe(true);
  });

  it('일반 채팅(super) 세션은 내역 API 를 부르지 않는다', async () => {
    let calls = 0;
    server.use(
      http.get(TRACES_URL, () => {
        calls += 1;
        return HttpResponse.json({ session_id: 's1', items: [] });
      }),
    );

    const { result } = render('super');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls).toBe(0);
  });
});
