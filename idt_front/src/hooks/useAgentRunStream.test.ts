import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Hoist-safe holders for the mock to read.
const mockState: {
  options: any;
  status: string;
  sendCalls: unknown[];
} = { options: null, status: 'idle', sendCalls: [] };

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
    selector({ accessToken: 'test-token', user: null, refreshToken: null, isAuthenticated: true }),
}));

import { useAgentRunStream } from './useAgentRunStream';

beforeEach(() => {
  mockState.options = null;
  mockState.status = 'idle';
  mockState.sendCalls = [];
});

function emit(type: string, data: any) {
  // simulate inbound WS message
  mockState.options.onMessage({ type, data });
}

describe('useAgentRunStream', () => {
  it('initial state is idle and empty', () => {
    const { result } = renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q' }),
    );
    expect(result.current.steps).toEqual([]);
    expect(result.current.tokens).toBe('');
    expect(result.current.answer).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.isDone).toBe(false);
  });

  it('onOpen sends a subscribe payload', () => {
    renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'agent-x', query: 'hi', sessionId: 's1' }),
    );
    act(() => mockState.options.onOpen());
    expect(mockState.sendCalls).toEqual([
      { type: 'subscribe', agent_id: 'agent-x', query: 'hi', session_id: 's1' },
    ]);
  });

  // ws-agent-excel-attachment
  it('onOpen includes attachments when provided', () => {
    renderHook(() =>
      useAgentRunStream({
        runId: 'r1',
        agentId: 'a',
        query: 'analyze',
        attachments: [{ type: 'excel', file_id: 'f123' }],
      }),
    );
    act(() => mockState.options.onOpen());
    expect(mockState.sendCalls[0]).toEqual({
      type: 'subscribe',
      agent_id: 'a',
      query: 'analyze',
      session_id: undefined,
      attachments: [{ type: 'excel', file_id: 'f123' }],
    });
  });

  it('onOpen omits attachments key when empty (regression)', () => {
    renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q', attachments: [] }),
    );
    act(() => mockState.options.onOpen());
    expect(mockState.sendCalls[0]).not.toHaveProperty('attachments');
  });

  it('appends node step on agent_node_started and fills durationMs on completed', () => {
    const { result } = renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q' }),
    );
    act(() => emit('agent_node_started', { node_name: 'supervisor', node_type: 'SUPERVISOR' }));
    expect(result.current.steps).toEqual([{ kind: 'node', name: 'supervisor' }]);

    act(() => emit('agent_node_completed', { node_name: 'supervisor', duration_ms: 123 }));
    expect(result.current.steps).toEqual([
      { kind: 'node', name: 'supervisor', durationMs: 123 },
    ]);
  });

  it('appends tool step on agent_tool_started', () => {
    const { result } = renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q' }),
    );
    act(() =>
      emit('agent_tool_started', {
        tool_name: 'rag',
        tool_call_id: 'tc1',
        input_preview: '',
      }),
    );
    expect(result.current.steps).toEqual([{ kind: 'tool', name: 'rag' }]);
  });

  it('accumulates tokens on agent_token', () => {
    const { result } = renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q' }),
    );
    act(() => emit('agent_token', { chunk: '안', node_name: 'final_answer' }));
    act(() => emit('agent_token', { chunk: '녕', node_name: 'final_answer' }));
    expect(result.current.tokens).toBe('안녕');
  });

  // fix-chat-reasoning-object-render — chunk가 비정상(객체/배열)이어도 [object Object]가 새지 않음
  it('non-string chunk does not leak [object Object] into tokens', () => {
    const { result } = renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q' }),
    );
    act(() => emit('agent_token', { chunk: '안', node_name: 'final_answer' }));
    act(() => emit('agent_token', { chunk: [{ type: 'text', text: '녕' }], node_name: 'final_answer' }));
    act(() => emit('agent_token', { chunk: { foo: 'bar' }, node_name: 'final_answer' }));
    act(() => emit('agent_token', { chunk: '하세요', node_name: 'final_answer' }));
    expect(result.current.tokens).toBe('안하세요');
    expect(result.current.tokens).not.toContain('[object Object]');
  });

  it('captures answer on agent_answer_completed', () => {
    const { result } = renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q' }),
    );
    act(() =>
      emit('agent_answer_completed', { answer: '안녕하세요', tools_used: [] }),
    );
    expect(result.current.answer).toBe('안녕하세요');
  });

  it('captures charts on agent_answer_completed (supervisor-chart-builder-node)', () => {
    const { result } = renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q' }),
    );
    const chart = {
      type: 'bar',
      data: { labels: ['x'], datasets: [{ label: 's', data: [1] }] },
    };
    act(() =>
      emit('agent_answer_completed', {
        answer: '차트입니다',
        tools_used: [],
        charts: [chart],
      }),
    );
    expect(result.current.charts).toEqual([chart]);
  });

  it('defaults charts to empty array when absent', () => {
    const { result } = renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q' }),
    );
    act(() =>
      emit('agent_answer_completed', { answer: 'no chart', tools_used: [] }),
    );
    expect(result.current.charts).toEqual([]);
  });

  it('marks isDone on agent_run_completed', () => {
    const { result } = renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q' }),
    );
    act(() =>
      emit('agent_run_completed', { run_id: 'r1', langsmith_run_url: null }),
    );
    expect(result.current.isDone).toBe(true);
  });

  // agent-chat-reasoning-display Design §5.3
  it('appends reasoning step on agent_step_reasoning', () => {
    const { result } = renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q' }),
    );
    act(() =>
      emit('agent_step_reasoning', {
        step_name: 'supervisor',
        reasoning: 'X 정보가 필요해서 search_agent를 호출합니다.',
        next_worker: 'search_agent',
      }),
    );
    expect(result.current.steps).toEqual([
      {
        kind: 'reasoning',
        name: 'supervisor',
        text: 'X 정보가 필요해서 search_agent를 호출합니다.',
        nextWorker: 'search_agent',
      },
    ]);
  });

  it('captures error and isDone on agent_run_failed', () => {
    const { result } = renderHook(() =>
      useAgentRunStream({ runId: 'r1', agentId: 'a', query: 'q' }),
    );
    act(() =>
      emit('agent_run_failed', { code: 'GRAPH_EXEC_FAILED', message: 'boom' }),
    );
    expect(result.current.error).toEqual({ code: 'GRAPH_EXEC_FAILED', message: 'boom' });
    expect(result.current.isDone).toBe(true);
  });

  // chatpage-rerequest-stale-state-fix Design §4.2
  describe('streamId render-time reset', () => {
    it('streamId 가 바뀌면 같은 hook 인스턴스의 state 가 INITIAL 로 리셋된다', () => {
      const { result, rerender } = renderHook(
        ({ streamId, query, runId }) =>
          useAgentRunStream({ streamId, runId, agentId: 'a', query }),
        { initialProps: { streamId: 'stream-1', runId: 'r1', query: 'Q1' } },
      );

      act(() => emit('agent_token', { chunk: '안녕', node_name: 'answer' }));
      act(() =>
        emit('agent_answer_completed', { answer: 'A1', tools_used: [] }),
      );
      act(() =>
        emit('agent_run_completed', { run_id: 'r1', langsmith_run_url: null }),
      );
      expect(result.current.isDone).toBe(true);
      expect(result.current.answer).toBe('A1');
      expect(result.current.streamId).toBe('stream-1');

      rerender({ streamId: 'stream-2', runId: 'r2', query: 'Q2' });
      expect(result.current.isDone).toBe(false);
      expect(result.current.answer).toBeNull();
      expect(result.current.tokens).toBe('');
      expect(result.current.steps).toEqual([]);
      expect(result.current.streamId).toBe('stream-2');
    });

    it('동일 streamId 재호출은 state 를 보존한다', () => {
      const { result, rerender } = renderHook(
        (props) => useAgentRunStream(props),
        {
          initialProps: {
            streamId: 'sid-keep',
            runId: 'r1',
            agentId: 'a',
            query: 'q',
          },
        },
      );
      act(() => emit('agent_token', { chunk: 'x', node_name: 'n' }));
      rerender({ streamId: 'sid-keep', runId: 'r1', agentId: 'a', query: 'q' });
      expect(result.current.tokens).toBe('x');
      expect(result.current.streamId).toBe('sid-keep');
    });
  });
});
