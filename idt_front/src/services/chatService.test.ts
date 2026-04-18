/**
 * chatService adapter unit tests — Design §8.2.1
 *
 * C1: toChatSession — session_id → id, last_message_at → updatedAt/createdAt
 * C2: toChatSession — last_message 비었을 때 title = "새 대화"
 * C3: toChatSession — last_message 30자 초과 시 truncate
 * C4: toMessage — server role/content/created_at → client Message
 * C5: 서버 응답 배열 순서 유지 (reverse 금지)
 */
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { chatService } from '@/services/chatService';
import { API_ENDPOINTS } from '@/constants/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('toChatSession adapter (via getConversationSessions)', () => {
  it('C1: session_id → id, last_message_at → updatedAt 매핑', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.CONVERSATION_SESSIONS}`, () =>
        HttpResponse.json({
          user_id: 'user-001',
          sessions: [
            {
              session_id: 'session-xyz',
              message_count: 2,
              last_message: '안녕하세요',
              last_message_at: '2026-04-17T10:00:00Z',
            },
          ],
        }),
      ),
    );

    const result = await chatService.getConversationSessions('user-001');

    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('session-xyz');
    expect(result[0].updatedAt).toBe('2026-04-17T10:00:00Z');
    expect(result[0].createdAt).toBe('2026-04-17T10:00:00Z');
  });

  it('C2: last_message 비었을 때 title = "새 대화"', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.CONVERSATION_SESSIONS}`, () =>
        HttpResponse.json({
          user_id: 'user-001',
          sessions: [
            {
              session_id: 'session-empty',
              message_count: 0,
              last_message: '',
              last_message_at: '2026-04-17T10:00:00Z',
            },
          ],
        }),
      ),
    );

    const result = await chatService.getConversationSessions('user-001');

    expect(result[0].title).toBe('새 대화');
  });

  it('C3: last_message 30자 초과 시 30자로 truncate', async () => {
    const longMessage = '이것은 서른 글자를 훨씬 넘어가는 아주 긴 메시지입니다 여기에 더 긴 내용도 있습니다';

    server.use(
      http.get(`*${API_ENDPOINTS.CONVERSATION_SESSIONS}`, () =>
        HttpResponse.json({
          user_id: 'user-001',
          sessions: [
            {
              session_id: 'session-long',
              message_count: 1,
              last_message: longMessage,
              last_message_at: '2026-04-17T10:00:00Z',
            },
          ],
        }),
      ),
    );

    const result = await chatService.getConversationSessions('user-001');

    expect(result[0].title.length).toBeLessThanOrEqual(30);
    expect(result[0].title).toBe(longMessage.slice(0, 30));
  });
});

describe('toMessage adapter (via getSessionMessages)', () => {
  it('C4: server role/content/created_at → client Message 변환 (id: number → string)', async () => {
    server.use(
      http.get('*/api/v1/conversations/sessions/:sessionId/messages', ({ params, request }) => {
        const url = new URL(request.url);
        return HttpResponse.json({
          user_id: url.searchParams.get('user_id'),
          session_id: params.sessionId,
          messages: [
            {
              id: 1001,
              role: 'user',
              content: '테스트 질문',
              turn_index: 1,
              created_at: '2026-04-17T10:00:00Z',
            },
          ],
        });
      }),
    );

    const result = await chatService.getSessionMessages('session-xyz', 'user-001');

    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('1001');
    expect(typeof result[0].id).toBe('string');
    expect(result[0].role).toBe('user');
    expect(result[0].content).toBe('테스트 질문');
    expect(result[0].createdAt).toBe('2026-04-17T10:00:00Z');
  });

  it('C5: 서버 응답 배열 순서 유지 (reverse 금지)', async () => {
    server.use(
      http.get('*/api/v1/conversations/sessions/:sessionId/messages', ({ params, request }) => {
        const url = new URL(request.url);
        return HttpResponse.json({
          user_id: url.searchParams.get('user_id'),
          session_id: params.sessionId,
          messages: [
            { id: 1, role: 'user', content: '첫 번째', turn_index: 1, created_at: '2026-04-17T10:00:00Z' },
            { id: 2, role: 'assistant', content: '두 번째', turn_index: 1, created_at: '2026-04-17T10:00:03Z' },
            { id: 3, role: 'user', content: '세 번째', turn_index: 2, created_at: '2026-04-17T10:01:00Z' },
          ],
        });
      }),
    );

    const result = await chatService.getSessionMessages('session-xyz', 'user-001');

    expect(result).toHaveLength(3);
    expect(result[0].id).toBe('1');
    expect(result[1].id).toBe('2');
    expect(result[2].id).toBe('3');
    expect(result[0].content).toBe('첫 번째');
    expect(result[2].content).toBe('세 번째');
  });
});
