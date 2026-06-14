/**
 * useAgentRunStream — Agent 실행 실시간 진행률 구독 hook.
 *
 * Wraps the generic `useWebSocket` and:
 *   - Builds the WS URL via `wsUrl()` with access token (Design §5.3)
 *   - Sends the initial `subscribe` payload on open
 *   - Maps incoming `AgentRunMessage`s into a small UI-friendly state machine
 *
 * Design fe-websocket-integration-guide §5.3.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { WS_ENDPOINTS } from '@/constants/api';
import { useAuthStore } from '@/store/authStore';
import { useWebSocket, type WebSocketStatus } from '@/hooks/useWebSocket';
import type { AgentAttachmentRef } from '@/types/agentAttachment';
import type { ChartPayload } from '@/types/chart';
import type { AgentRunMessage } from '@/types/websocket';
import { wsUrl } from '@/utils/wsUrl';

export interface AgentRunStep {
  kind: 'node' | 'tool' | 'reasoning';
  name: string;
  durationMs?: number;
  // agent-chat-reasoning-display Design §3.3 — reasoning kind 전용 필드
  text?: string;
  nextWorker?: string;
}

export interface AgentRunStreamState {
  status: WebSocketStatus;
  steps: AgentRunStep[];
  tokens: string;
  answer: string | null;
  // supervisor-chart-builder-node: 답변 완료 시 함께 내려오는 Chart.js 페이로드.
  charts: ChartPayload[];
  error: { code: string; message: string } | null;
  isDone: boolean;
  // chatpage-rerequest-stale-state-fix Design §3.3
  streamId: string;
}

export interface UseAgentRunStreamOptions {
  // chatpage-rerequest-stale-state-fix Design §3.3 — 매 send 마다 신규 발급되는 stream lifecycle id
  streamId?: string;
  runId: string;
  agentId: string;
  query: string;
  sessionId?: string;
  // ws-agent-excel-attachment: 업로드된 엑셀 등 첨부 참조 (optional)
  attachments?: AgentAttachmentRef[];
  enabled?: boolean;
}

const INITIAL_STATE: Omit<AgentRunStreamState, 'streamId'> = {
  status: 'idle',
  steps: [],
  tokens: '',
  answer: null,
  charts: [],
  error: null,
  isDone: false,
};

export function useAgentRunStream(
  opts: UseAgentRunStreamOptions,
): AgentRunStreamState {
  const { streamId = '', runId, agentId, query, sessionId, attachments, enabled = true } = opts;
  const accessToken = useAuthStore((s) => s.accessToken);

  const [state, setState] = useState<AgentRunStreamState>({ ...INITIAL_STATE, streamId: '' });

  // chatpage-rerequest-stale-state-fix Design §3.3 — render 단계 동기 리셋
  if (enabled && streamId && streamId !== state.streamId) {
    setState({ ...INITIAL_STATE, streamId });
  }

  // Latest subscribe payload — refs so onOpen always uses current values.
  const subscribeRef = useRef({ agentId, query, sessionId, attachments });
  subscribeRef.current = { agentId, query, sessionId, attachments };

  const handleMessage = useCallback((raw: { type: string; data?: unknown }) => {
    const msg = raw as unknown as AgentRunMessage;
    switch (msg.type) {
      case 'agent_node_started':
        setState((s) => ({
          ...s,
          steps: [...s.steps, { kind: 'node', name: msg.data.node_name }],
        }));
        break;
      case 'agent_node_completed':
        setState((s) => ({
          ...s,
          steps: s.steps.map((st, i, arr) =>
            i === arr.length - 1 && st.kind === 'node' && st.name === msg.data.node_name
              ? { ...st, durationMs: msg.data.duration_ms }
              : st,
          ),
        }));
        break;
      case 'agent_step_reasoning':
        // agent-chat-reasoning-display Design §5.3
        setState((s) => ({
          ...s,
          steps: [
            ...s.steps,
            {
              kind: 'reasoning',
              name: msg.data.step_name,
              text: msg.data.reasoning,
              nextWorker: msg.data.next_worker,
            },
          ],
        }));
        break;
      case 'agent_tool_started':
        setState((s) => ({
          ...s,
          steps: [...s.steps, { kind: 'tool', name: msg.data.tool_name }],
        }));
        break;
      case 'agent_tool_completed':
        setState((s) => ({
          ...s,
          steps: s.steps.map((st, i, arr) =>
            i === arr.length - 1 && st.kind === 'tool' && st.name === msg.data.tool_name
              ? { ...st, durationMs: msg.data.duration_ms }
              : st,
          ),
        }));
        break;
      case 'agent_token': {
        // fix-chat-reasoning-object-render: chunk가 비정상(객체/배열)으로 와도
        // 문자열 결합으로 "[object Object]"가 새지 않도록 string 가드(2차 안전망).
        const chunk = typeof msg.data.chunk === 'string' ? msg.data.chunk : '';
        setState((s) => ({ ...s, tokens: s.tokens + chunk }));
        break;
      }
      case 'agent_answer_completed':
        setState((s) => ({
          ...s,
          answer: msg.data.answer,
          charts: msg.data.charts ?? [],
        }));
        break;
      case 'agent_run_completed':
        setState((s) => ({ ...s, isDone: true }));
        break;
      case 'agent_run_failed':
        setState((s) => ({ ...s, error: msg.data, isDone: true }));
        break;
      // agent_run_started, etc. — no UI state to set
      default:
        break;
    }
  }, []);

  const { connect, disconnect, send, status } = useWebSocket({
    reconnect: false,
    onMessage: handleMessage,
    onOpen: () => {
      const { agentId: a, query: q, sessionId: s, attachments: att } = subscribeRef.current;
      send({
        type: 'subscribe',
        agent_id: a,
        query: q,
        session_id: s,
        ...(att && att.length > 0 ? { attachments: att } : {}),
      });
    },
  });

  useEffect(() => {
    setState((s) => (s.status === status ? s : { ...s, status }));
  }, [status]);

  useEffect(() => {
    // chatpage-rerequest-stale-state-fix Design §3.3 — streamId deps 로 매 send 재연결.
    // 상태 리셋은 render 단계에서 이미 처리되었으므로 여기서는 connect 만 담당.
    if (!enabled || !accessToken || !runId || !streamId) return;
    const url = wsUrl(WS_ENDPOINTS.WS_AGENT_RUN(runId), { token: accessToken });
    connect(url);
    return () => {
      disconnect();
    };
    // connect/disconnect identity changes on every useWebSocket render but we
    // only want to (re)open on the inputs below — intentionally exclude.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, accessToken, runId, streamId]);

  return state;
}
