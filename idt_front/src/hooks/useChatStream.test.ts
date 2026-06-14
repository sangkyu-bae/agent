import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockState: { options: any; status: string; sendCalls: unknown[] } = {
  options: null,
  status: 'idle',
  sendCalls: [],
};

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: (opts: any) => {
    mockState.options = opts;
    return {
      status: mockState.status,
      isConnected: mockState.status === 'connected',
      connect: vi.fn(),
      disconnect: vi.fn(),
      send: vi.fn((msg: unknown) => {
        mockState.sendCalls.push(msg);
      }),
    };
  },
}));

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: any) =>
    selector({
      accessToken: 'test-token',
      user: null,
      refreshToken: null,
      isAuthenticated: true,
    }),
}));

import { useChatStream } from './useChatStream';

beforeEach(() => {
  mockState.options = null;
  mockState.status = 'idle';
  mockState.sendCalls = [];
});

function emit(type: string, data: any, metadata?: Record<string, unknown>) {
  mockState.options.onMessage({ type, data, metadata });
}

describe('useChatStream', () => {
  it('initial state is empty', () => {
    const { result } = renderHook(() =>
      useChatStream({ sessionId: 's1', message: 'hi' }),
    );
    expect(result.current.tokens).toBe('');
    expect(result.current.toolEvents).toEqual([]);
    expect(result.current.answer).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.isDone).toBe(false);
    expect(result.current.isReplayed).toBe(false);
  });

  it('onOpen sends subscribe payload with message and top_k', () => {
    renderHook(() =>
      useChatStream({ sessionId: 's1', message: '안녕', topK: 3 }),
    );
    act(() => mockState.options.onOpen());
    expect(mockState.sendCalls).toEqual([
      { type: 'subscribe', message: '안녕', top_k: 3 },
    ]);
  });

  it('accumulates tokens', () => {
    const { result } = renderHook(() =>
      useChatStream({ sessionId: 's1', message: 'hi' }),
    );
    act(() => emit('chat_token', { chunk: '안' }));
    act(() => emit('chat_token', { chunk: '녕' }));
    act(() => emit('chat_token', { chunk: '하세요' }));
    expect(result.current.tokens).toBe('안녕하세요');
  });

  // fix-chat-reasoning-object-render — chunk가 비정상(객체/배열)이어도 [object Object]가 새지 않음
  it('non-string chunk does not leak [object Object] into tokens', () => {
    const { result } = renderHook(() =>
      useChatStream({ sessionId: 's1', message: 'hi' }),
    );
    act(() => emit('chat_token', { chunk: '안' }));
    act(() => emit('chat_token', { chunk: [{ type: 'text', text: '녕' }] as unknown }));
    act(() => emit('chat_token', { chunk: { foo: 'bar' } as unknown }));
    act(() => emit('chat_token', { chunk: '하세요' }));
    expect(result.current.tokens).toBe('안하세요');
    expect(result.current.tokens).not.toContain('[object Object]');
  });

  it('records tool events on started/completed', () => {
    const { result } = renderHook(() =>
      useChatStream({ sessionId: 's1', message: 'q' }),
    );
    act(() =>
      emit('chat_tool_started', {
        tool_name: 'tavily_search',
        tool_call_id: 'tc1',
        input_preview: 'query',
      }),
    );
    act(() =>
      emit('chat_tool_completed', {
        tool_name: 'tavily_search',
        tool_call_id: 'tc1',
        output_preview: 'result',
        duration_ms: 1234,
      }),
    );
    expect(result.current.toolEvents).toEqual([
      { kind: 'started', toolName: 'tavily_search', preview: 'query' },
      {
        kind: 'completed',
        toolName: 'tavily_search',
        preview: 'result',
        durationMs: 1234,
      },
    ]);
  });

  it('captures answer/sources/wasSummarized on chat_answer_completed', () => {
    const { result } = renderHook(() =>
      useChatStream({ sessionId: 's1', message: 'q' }),
    );
    act(() =>
      emit('chat_answer_completed', {
        answer: '안녕하세요',
        tools_used: ['tavily_search'],
        sources: [{ content: 'c', source: 'd.pdf', chunk_id: '1', score: 0.9 }],
        was_summarized: true,
      }),
    );
    expect(result.current.answer).toBe('안녕하세요');
    expect(result.current.sources).toHaveLength(1);
    expect(result.current.wasSummarized).toBe(true);
  });

  it('marks isDone on chat_done', () => {
    const { result } = renderHook(() =>
      useChatStream({ sessionId: 's1', message: 'q' }),
    );
    act(() => emit('chat_done', { session_id: 's1' }));
    expect(result.current.isDone).toBe(true);
  });

  // agent-chat-reasoning-display Design §5.3
  it('appends reasoning to toolEvents on chat_step_reasoning', () => {
    const { result } = renderHook(() =>
      useChatStream({ sessionId: 's1', message: 'q' }),
    );
    act(() =>
      emit('chat_step_reasoning', {
        step_name: 'chat_agent',
        reasoning: 'RAG 검색이 필요해서 호출합니다.',
        tool_calls: ['rag_search'],
      }),
    );
    expect(result.current.toolEvents).toEqual([
      {
        kind: 'reasoning',
        toolName: 'chat_agent',
        text: 'RAG 검색이 필요해서 호출합니다.',
      },
    ]);
  });

  it('captures error and isDone on chat_failed', () => {
    const { result } = renderHook(() =>
      useChatStream({ sessionId: 's1', message: 'q' }),
    );
    act(() => emit('chat_failed', { code: 'CHAT_EXEC_FAILED', message: 'boom' }));
    expect(result.current.error).toEqual({
      code: 'CHAT_EXEC_FAILED',
      message: 'boom',
    });
    expect(result.current.isDone).toBe(true);
  });

  it('sets isReplayed=true when first chat_started arrives cached', () => {
    const { result } = renderHook(() =>
      useChatStream({ sessionId: 's1', message: 'q' }),
    );
    act(() =>
      emit('chat_started', { session_id: 's1' }, { cached: true, seq: 1, ts: '2026-05-25T12:00:00+00:00' }),
    );
    expect(result.current.isReplayed).toBe(true);
  });

  // chatpage-rerequest-stale-state-fix Design §4.1
  describe('streamId render-time reset', () => {
    it('streamId 가 바뀌면 같은 hook 인스턴스의 state 가 INITIAL 로 리셋된다', () => {
      const { result, rerender } = renderHook(
        ({ streamId, message }) =>
          useChatStream({ streamId, sessionId: 's1', message }),
        { initialProps: { streamId: 'stream-1', message: 'Q1' } },
      );

      // Q1 lifecycle 시뮬레이션 — tokens, answer, isDone 누적
      act(() => emit('chat_token', { chunk: '안녕' }));
      act(() =>
        emit('chat_answer_completed', {
          answer: 'A1',
          sources: [],
          was_summarized: false,
        }),
      );
      act(() => emit('chat_done', { session_id: 's1' }));
      expect(result.current.isDone).toBe(true);
      expect(result.current.answer).toBe('A1');
      expect(result.current.tokens).toBe('안녕');
      expect(result.current.streamId).toBe('stream-1');

      // 새 streamId 로 rerender — render 단계 동기 리셋이 INITIAL 을 즉시 반영해야 함
      rerender({ streamId: 'stream-2', message: 'Q2' });
      expect(result.current.isDone).toBe(false);
      expect(result.current.answer).toBeNull();
      expect(result.current.tokens).toBe('');
      expect(result.current.error).toBeNull();
      expect(result.current.streamId).toBe('stream-2');
    });

    it('동일 streamId 재호출은 state 를 리셋하지 않는다 (idempotent)', () => {
      const { result, rerender } = renderHook(
        (props) => useChatStream(props),
        {
          initialProps: {
            streamId: 'stream-x',
            sessionId: 's1',
            message: 'Q1',
          },
        },
      );
      act(() => emit('chat_token', { chunk: 'hello' }));
      expect(result.current.tokens).toBe('hello');

      rerender({ streamId: 'stream-x', sessionId: 's1', message: 'Q1' });
      // 같은 streamId 이므로 tokens 가 유지되어야 함
      expect(result.current.tokens).toBe('hello');
      expect(result.current.streamId).toBe('stream-x');
    });

    it('enabled=false 또는 streamId="" 인 경우 리셋이 발생하지 않는다', () => {
      const { result, rerender } = renderHook(
        (props) => useChatStream(props),
        {
          initialProps: {
            streamId: 'stream-1',
            sessionId: 's1',
            message: 'Q1',
            enabled: true,
          },
        },
      );
      act(() => emit('chat_token', { chunk: 'X' }));
      expect(result.current.tokens).toBe('X');
      expect(result.current.streamId).toBe('stream-1');

      // enabled=false 로 전환 — 리셋 안 됨, 상태 유지
      rerender({
        streamId: '',
        sessionId: '',
        message: '',
        enabled: false,
      });
      expect(result.current.tokens).toBe('X');
      expect(result.current.streamId).toBe('stream-1');
    });
  });
});
