import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { useComposeAgent } from './useAgentComposer';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useComposeAgent (fix-agent-composer F1/F2)', () => {
  it('compose 성공 시 초안 응답을 반환한다', async () => {
    const { result } = renderHook(() => useComposeAgent(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ user_request: '재무 에이전트 만들어줘' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.coverage).toBe('partial');
    expect(result.current.data?.tool_ids).toContain('tavily_search');
  });

  it('compose 실패(422) 시 에러 상태가 된다', async () => {
    server.use(
      http.post('*/api/v1/agents/compose', () =>
        HttpResponse.json(
          { detail: 'LLM 모델을 찾을 수 없습니다: ghost' },
          { status: 422 },
        ),
      ),
    );
    const { result } = renderHook(() => useComposeAgent(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ user_request: '요청', llm_model_id: 'ghost' });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
