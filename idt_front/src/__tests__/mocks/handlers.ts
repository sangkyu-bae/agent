import { http, HttpResponse } from 'msw';
import { API_ENDPOINTS } from '@/constants/api';

export const handlers = [
  http.post(`*${API_ENDPOINTS.GENERAL_CHAT}`, () =>
    HttpResponse.json({
      user_id: 'user-001',
      session_id: 'session-abc',
      answer: '테스트 답변입니다.',
      tools_used: ['hybrid_document_search'],
      sources: [
        { content: '청크 내용', source: 'doc.pdf', chunk_id: 'c-001', score: 0.92 },
      ],
      was_summarized: false,
      request_id: 'req-001',
    })
  ),

  // CHAT-HIST-001: 사용자 세션 목록
  http.get(`*${API_ENDPOINTS.CONVERSATION_SESSIONS}`, ({ request }) => {
    const url = new URL(request.url);
    const userId = url.searchParams.get('user_id');
    return HttpResponse.json({
      user_id: userId,
      sessions: [
        {
          session_id: 's1',
          message_count: 4,
          last_message: '안녕',
          last_message_at: '2026-04-17T10:00:00Z',
        },
        {
          session_id: 's2',
          message_count: 2,
          last_message: '이전 질문',
          last_message_at: '2026-04-16T12:00:00Z',
        },
      ],
    });
  }),

  // CHAT-HIST-001: 세션 메시지 조회
  http.get('*/api/v1/conversations/sessions/:sessionId/messages', ({ params, request }) => {
    const url = new URL(request.url);
    return HttpResponse.json({
      user_id: url.searchParams.get('user_id'),
      session_id: params.sessionId,
      messages: [
        {
          id: 1,
          role: 'user',
          content: '이전 질문입니다',
          turn_index: 1,
          created_at: '2026-04-17T10:00:00Z',
        },
        {
          id: 2,
          role: 'assistant',
          content: '이전 답변입니다',
          turn_index: 1,
          created_at: '2026-04-17T10:00:03Z',
        },
      ],
    });
  }),
];
